"""Integração: servidor real em porta efêmera, requisições HTTP de verdade."""
import http.client
import json
import threading
import unittest
from datetime import timedelta

from rota.http_api import ServidorComPool
from rota.nucleo import Nucleo
from rota.relogio import Relogio
from tests.apoio import notif, novo_nucleo


class _ComServidor(unittest.TestCase):
    """Sobe um servidor de verdade por classe. Cada classe tem o SEU núcleo: um teste que mexe no
    relógio simulado não pode alterar o que os outros testes enxergam."""

    @classmethod
    def setUpClass(cls):
        cls.nucleo = novo_nucleo()
        cls.srv = ServidorComPool(("127.0.0.1", 0), cls.nucleo, workers=16)
        cls.porta = cls.srv.server_port
        cls.t = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.t.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.nucleo.parar()

    def req(self, metodo, caminho, corpo=None, headers=None, bruto=None):
        c = http.client.HTTPConnection("127.0.0.1", self.porta, timeout=10)
        h = {"Content-Type": "application/json"}
        h.update(headers or {})
        dados = bruto if bruto is not None else (json.dumps(corpo).encode() if corpo is not None else None)
        c.request(metodo, caminho, body=dados, headers=h)
        r = c.getresponse()
        bruto = r.read()
        c.close()
        if not bruto:
            return r.status, None, r
        if "application/json" in (r.getheader("Content-Type") or ""):
            return r.status, json.loads(bruto.decode()), r
        return r.status, bruto.decode(errors="replace"), r


class TestHttp(_ComServidor):
    def criar_pedido(self, i, descricao=None):
        s, p, _ = self.req("POST", "/api/v1/notificacoes", notif(i, descricao=descricao))
        self.assertEqual(s, 202)
        self.assertTrue(self.nucleo.aguardar_ocioso())
        return self.req("GET", f"/api/v1/notificacoes/{p['notificacao_id']}")[1]["pedido_id"]

    def test_fluxo_completo(self):
        self.assertEqual(self.req("GET", "/health")[0], 200)
        pid = self.criar_pedido(0)
        s, p, _ = self.req("GET", f"/api/v1/pedidos/{pid}")
        self.assertEqual((s, p["status"]), (200, "NO_PRAZO"))
        s, dup, _ = self.req("POST", "/api/v1/notificacoes", notif(0))
        self.assertEqual((s, dup["duplicatas_recebidas"]), (200, 1))
        responsavel = p["entregador_responsavel_id"]
        outro = "ent-caio" if responsavel != "ent-caio" else "ent-duda"
        s, p, _ = self.req("POST", f"/api/v1/pedidos/{pid}/redespacho", {"entregador_destino": outro})
        self.assertEqual((s, p["entregador_responsavel_id"]), (200, outro))
        s, p, _ = self.req("POST", f"/api/v1/pedidos/{pid}/entrega",
                           {"entregador_id": outro, "codigo_confirmacao": "F-1"})
        self.assertEqual((s, p["status"]), (200, "ENTREGUE"))
        s, a, _ = self.req("GET", "/api/v1/auditoria")
        self.assertTrue(a["ok"], a)

    def test_transito_e_alertas(self):
        pid = self.criar_pedido(1)
        s, r, _ = self.req("POST", "/api/v1/transito/janelas",
                           {"inicio": "2026-09-21T11:00:00-03:00", "fim": "2026-09-21T11:30:00-03:00",
                            "tipo": "PICO", "motivo": "teste"})
        self.assertEqual(s, 202)
        self.assertTrue(self.nucleo.aguardar_ocioso())
        self.assertEqual(self.req("GET", f"/api/v1/pedidos/{pid}")[1]["transito_versao"], r["versao"])
        s, al, _ = self.req("GET", "/api/v1/alertas?apos=0")
        self.assertIn("TRANSITO_ATUALIZADO", [x["tipo"] for x in al["alertas"]])
        self.assertEqual(self.req("GET", "/api/v1/transito")[1]["versao"], r["versao"])

    def test_erros(self):
        casos = [
            (("POST", "/api/v1/notificacoes", None, None, b"{nao-json"), 400, "REQUISICAO_INVALIDA"),
            (("POST", "/api/v1/notificacoes", {"x": 1}, {"Content-Type": "text/plain"}), 415, "TIPO_NAO_SUPORTADO"),
            (("POST", "/api/v1/notificacoes", None, None, b"[1,2]"), 400, "REQUISICAO_INVALIDA"),
            (("GET", "/api/v1/nada"), 404, "ROTA_NAO_ENCONTRADA"),
            (("POST", "/api/v1/pedidos"), 405, "METODO_NAO_PERMITIDO"),
            (("PUT", "/api/v1/pedidos"), 405, "METODO_NAO_PERMITIDO"),
            (("DELETE", "/api/v1/pedidos/ped_x"), 405, "METODO_NAO_PERMITIDO"),
            (("PATCH", "/api/v1/notificacoes", {"a": 1}), 405, "METODO_NAO_PERMITIDO"),
            (("PUT", "/api/v1/nada", {"a": 1}), 404, "ROTA_NAO_ENCONTRADA"),
            (("GET", "/api/v1/pedidos/ped_inexistente"), 404, "NAO_ENCONTRADO"),
            (("GET", "/api/v1/pedidos?limite=abc"), 400, "REQUISICAO_INVALIDA"),
            (("GET", "/api/v1/pedidos?status=XPTO"), 400, "REQUISICAO_INVALIDA"),
            (("POST", "/api/v1/notificacoes", None, None, b"x" * 300000), 413, "CORPO_MUITO_GRANDE"),
        ]
        for args, status, codigo in casos:
            s, corpo, r = self.req(*args)
            self.assertEqual((s, corpo["erro"]["codigo"]), (status, codigo), args[:2])
            self.assertTrue(r.getheader("X-Request-Id"))

    def test_conflito_apos_entregue(self):
        pid = self.criar_pedido(2)
        responsavel = self.req("GET", f"/api/v1/pedidos/{pid}")[1]["entregador_responsavel_id"]
        self.req("POST", f"/api/v1/pedidos/{pid}/entrega", {"entregador_id": responsavel, "codigo_confirmacao": "X"})
        s, e, _ = self.req("POST", f"/api/v1/pedidos/{pid}/redespacho", {"entregador_destino": "ent-duda"})
        self.assertEqual((s, e["erro"]["codigo"]), (409, "CONFLITO"))

    def test_dashboard_estatico(self):
        s, _, r = self.req("GET", "/")
        self.assertEqual(s, 200)
        self.assertIn("text/html", r.getheader("Content-Type"))
        s, _, r = self.req("GET", "/static/dashboard.css")
        self.assertEqual(s, 200)
        self.assertIn("text/css", r.getheader("Content-Type"))
        s, _, r = self.req("GET", "/static/dashboard.js")
        self.assertEqual(s, 200)
        self.assertIn("text/javascript", r.getheader("Content-Type"))
        self.assertEqual(self.req("GET", "/static/nao-existe.txt")[0], 404)

    def test_rajada_de_requisicoes_concorrentes(self):
        erros, lk = [], threading.Lock()
        barreira = threading.Barrier(40)

        def cliente(i):
            barreira.wait()
            try:
                s, _, _ = self.req("POST", "/api/v1/notificacoes",
                                   notif(3, descricao="rajada. Tempo estimado de preparo: 12 minutos."))
                if s not in (200, 202):
                    raise AssertionError(s)
            except Exception as e:
                with lk:
                    erros.append(repr(e))

        ts = [threading.Thread(target=cliente, args=(i,)) for i in range(40)]
        [t.start() for t in ts]
        [t.join(30) for t in ts]
        self.assertEqual(erros, [])
        self.assertTrue(self.nucleo.aguardar_ocioso())
        pedidos = [p for p in self.nucleo.listar_pedidos(limite=1000) if p["numero_pedido"] == "IFOOD-000003"]
        self.assertEqual(len(pedidos), 1)


class TestHttpRelogio(_ComServidor):
    def test_relogio_simulado(self):
        s, r, _ = self.req("POST", "/api/v1/admin/relogio", {"minutos": 0})
        self.assertEqual(s, 400)
        antes = self.nucleo.relogio.agora()
        s, r, _ = self.req("POST", "/api/v1/admin/relogio", {"minutos": 5})
        self.assertEqual(s, 200)
        self.assertEqual(r["agora"], (antes + timedelta(minutes=5)).isoformat(timespec="seconds"))

    def test_relogio_real_recusa_avancar(self):
        real = Nucleo(Relogio())
        srv = ServidorComPool(("127.0.0.1", 0), real, workers=2)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            c = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
            c.request("POST", "/api/v1/admin/relogio", body=json.dumps({"minutos": 5}),
                      headers={"Content-Type": "application/json"})
            r = c.getresponse()
            corpo = json.loads(r.read())
            c.close()
            self.assertEqual((r.status, corpo["erro"]["codigo"]), (409, "RELOGIO_REAL"))
        finally:
            srv.shutdown()
            srv.server_close()


if __name__ == "__main__":
    unittest.main()
