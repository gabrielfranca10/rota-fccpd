"""Testes de estresse: muitas threads disparando ao mesmo tempo (Barrier) contra o núcleo.
Ao final, a auditoria confere as invariantes e compara com um recálculo sequencial."""
import random
import sys
import threading
import time
import unittest

from rota.dominio import Conflito
from rota.rwlock import RWLock
from tests.apoio import notif, novo_nucleo


def disparar(n_threads, alvo):
    """Solta todas as threads no mesmo instante e devolve exceções não esperadas."""
    barreira = threading.Barrier(n_threads)
    erros = []

    def corpo(i):
        barreira.wait()
        try:
            alvo(i)
        except Exception as e:  # pragma: no cover - só aparece se houver bug
            erros.append(repr(e))

    ts = [threading.Thread(target=corpo, args=(i,), daemon=True) for i in range(n_threads)]
    for t in ts:
        t.start()
    limite = time.monotonic() + 20
    for t in ts:
        t.join(max(0.0, limite - time.monotonic()))
    presas = sum(t.is_alive() for t in ts)
    if presas:
        erros.append(f"{presas} threads presas após 20 s (provável deadlock)")
    return erros


class TestConcorrencia(unittest.TestCase):
    def setUp(self):
        self.n = novo_nucleo(workers=8, fila=20000, restaurantes=20)

    def tearDown(self):
        self.n.parar()

    def test_mesma_notificacao_100_threads_gera_um_pedido(self):
        ids, novas = [], []
        lock = threading.Lock()

        def alvo(i):
            v, nova = self.n.receber_notificacao(notif(0, descricao="Pedido disputado. Tempo estimado "
                                                        "de preparo: 12 minutos.", numero_pedido="IFOOD-777777"))
            with lock:
                ids.append(v["notificacao_id"])
                novas.append(nova)

        self.assertEqual(disparar(100, alvo), [])
        self.assertEqual(len(set(ids)), 1)
        self.assertEqual(novas.count(True), 1)
        self.assertTrue(self.n.aguardar_ocioso())
        self.assertEqual(len(self.n.listar_pedidos(limite=1000)), 1)
        self.assertTrue(self.n.auditoria()["ok"])

    def test_ingestao_em_massa_com_duplicatas(self):
        def alvo(i):
            rnd = random.Random(i)
            for k in range(200):
                j = rnd.randrange(400)            # só 400 notificações distintas: muitas duplicatas
                self.n.receber_notificacao(notif(j, restaurante=j % 20,
                                                 descricao=f"pedido {j}. Tempo estimado de preparo: "
                                                 f"{5 + j % 60} minutos.", numero_pedido=f"IFOOD-{j:06d}"))

        self.assertEqual(disparar(20, alvo), [])
        self.assertTrue(self.n.aguardar_ocioso())
        a = self.n.auditoria()
        self.assertTrue(a["ok"], a)
        self.assertTrue(a["oraculo_executado"])
        self.assertEqual(a["pedidos"], 400)

    def test_redespacho_cruzado_sem_deadlock(self):
        n = novo_nucleo(restaurantes=8, workers=4, iniciar=False)
        n._entregadores.clear(); n._lock_entregador.clear(); n._agenda.clear()
        n.iniciar()
        n.cadastrar_entregador({"entregador_id": "ent-a", "nome": "A", "veiculo": "moto", "capacidade": 10})
        n.cadastrar_entregador({"entregador_id": "ent-b", "nome": "B", "veiculo": "moto", "capacidade": 10})
        # <= a capacidade de UM entregador: mesmo que o embaralhamento concentre tudo de um
        # lado, nunca esbarra em 409 por capacidade — este teste é só sobre deadlock.
        # Espalhados em restaurantes DIFERENTES de propósito: cada um tem seu próprio lock L2,
        # então vários redespachos entram na seção crítica L3 ao mesmo tempo — é isso que expõe
        # a corrida entre as duas ordens de lock (com um restaurante só, o L2 já serializaria
        # tudo e o bug de ordenação nunca apareceria).
        pedidos = []
        for i in range(8):
            v, _ = n.receber_notificacao(notif(i, restaurante=i, numero_pedido=f"IFOOD-{i:06d}"))
            pedidos.append(v)
        self.assertTrue(n.aguardar_ocioso())
        pids = [n.obter_notificacao(v["notificacao_id"])["pedido_id"] for v in pedidos]

        def alvo(i):
            rnd = random.Random(i)
            for _ in range(2000):
                pid = rnd.choice(pids)
                n.redespachar_pedido(pid, {"entregador_destino": rnd.choice(["ent-a", "ent-b"])})

        # troca de thread a cada ~1 µs (padrão: 5 ms): aumenta muito a chance de uma thread
        # ser interrompida entre o 1º e o 2º lock — sem isso o deadlock quase nunca aparece
        antes = sys.getswitchinterval()
        sys.setswitchinterval(1e-6)
        try:
            erros = disparar(16, alvo)   # com deadlock, as threads ficam presas e o teste falha
        finally:
            sys.setswitchinterval(antes)
        self.assertEqual(erros, [])
        self.assertTrue(n.auditoria()["ok"])
        self.assertEqual(len(n._agenda["ent-a"]) + len(n._agenda["ent-b"]), 8)
        n.parar()

    def test_confirmar_e_redespachar_ao_mesmo_tempo(self):
        v, _ = self.n.receber_notificacao(notif(0, descricao="disputa. Tempo estimado de preparo: 12 minutos."))
        self.assertTrue(self.n.aguardar_ocioso())
        pid = self.n.obter_notificacao(v["notificacao_id"])["pedido_id"]
        responsavel = self.n.obter_pedido(pid)["entregador_responsavel_id"]
        resultados = []
        lk = threading.Lock()

        def alvo(i):
            try:
                if i % 2:
                    self.n.redespachar_pedido(pid, {"entregador_destino": "ent-duda"})
                    r = "redespachou"
                else:
                    self.n.confirmar_entrega(pid, {"entregador_id": responsavel, "codigo_confirmacao": "P"})
                    r = "confirmou"
            except Conflito:
                r = "conflito"
            with lk:
                resultados.append(r)

        self.assertEqual(disparar(20, alvo), [])
        self.assertTrue(self.n.auditoria()["ok"])
        estado = self.n.obter_pedido(pid)
        if estado["status"] == "ENTREGUE":
            self.assertEqual(estado["entregador_responsavel_id"], responsavel)
        else:
            self.assertEqual(estado["entregador_responsavel_id"], "ent-duda")

    def test_transito_muda_durante_ingestao(self):
        """Corrida clássica: worker calcula com o trânsito antigo enquanto ele é trocado.
        O RWLock + versão + recálculo garantem que, no fim, TODOS os pedidos batem com a
        versão final (verificado pelo oráculo sequencial da auditoria)."""
        def alvo(i):
            if i == 0:
                for k in range(10):
                    self.n.declarar_janela({"inicio": f"2026-09-21T{11 + k % 10:02d}:00:00-03:00",
                                            "fim": f"2026-09-21T{11 + k % 10:02d}:30:00-03:00",
                                            "tipo": "PICO" if k % 2 else "BLOQUEIO", "motivo": f"evento {k}"})
            else:
                for k in range(150):
                    j = (i + k) % 400
                    self.n.receber_notificacao(notif(j, restaurante=j % 20,
                                                     descricao=f"cal {i} {k}. Tempo estimado de preparo: "
                                                     f"{5 + k % 60} minutos.", numero_pedido=f"IFOOD-{j:06d}"))

        self.assertEqual(disparar(12, alvo), [])
        self.assertTrue(self.n.aguardar_ocioso())
        a = self.n.auditoria()
        self.assertTrue(a["ok"], a)
        self.assertTrue(a["oraculo_executado"])
        self.assertEqual(a["transito_versao"], 11)

    def test_tudo_junto_com_monitor(self):
        pedidos = []
        plk = threading.Lock()

        def alvo(i):
            rnd = random.Random(100 + i)
            for k in range(120):
                papel = i % 4
                try:
                    if papel == 0:
                        j = rnd.randrange(400)
                        self.n.receber_notificacao(notif(j, restaurante=j % 20,
                                                         descricao=f"x{i}-{k}. Tempo estimado de preparo: "
                                                         f"{5 + k % 60} minutos.", numero_pedido=f"IFOOD-{j:06d}"))
                    elif papel == 1 and pedidos:
                        with plk:
                            pid = rnd.choice(pedidos)
                        destino = rnd.choice(["ent-joao", "ent-marcia", "ent-caio", "ent-duda"])
                        self.n.redespachar_pedido(pid, {"entregador_destino": destino})
                    elif papel == 2 and pedidos:
                        with plk:
                            pid = rnd.choice(pedidos)
                        dono = self.n.obter_pedido(pid)["entregador_responsavel_id"]
                        if dono:
                            self.n.confirmar_entrega(pid, {"entregador_id": dono, "codigo_confirmacao": f"p{i}{k}"})
                    elif papel == 3:
                        self.n.executar_monitor()
                        if k % 40 == 0:
                            self.n.relogio.avancar(minutes=5)
                        with plk:
                            pedidos.extend(p["pedido_id"] for p in self.n.listar_pedidos(limite=50))
                except Conflito:
                    pass   # disputas legítimas (ex.: outro entregador ficou responsável antes)

        self.assertEqual(disparar(16, alvo), [])
        self.assertTrue(self.n.aguardar_ocioso())
        a = self.n.auditoria()
        self.assertTrue(a["ok"], a)


class TestRWLock(unittest.TestCase):
    def test_escritor_exclusivo_e_leitores_simultaneos(self):
        rw, estado = RWLock(), {"leitores": 0, "max_leitores": 0, "violacao": False}
        lk = threading.Lock()

        def leitor(_):
            for _ in range(200):
                with rw.leitura():
                    with lk:
                        estado["leitores"] += 1
                        estado["max_leitores"] = max(estado["max_leitores"], estado["leitores"])
                    with lk:
                        estado["leitores"] -= 1

        def escritor(_):
            for _ in range(50):
                with rw.escrita():
                    with lk:
                        if estado["leitores"]:
                            estado["violacao"] = True

        def alvo(i):
            (escritor if i < 2 else leitor)(i)

        self.assertEqual(disparar(12, alvo), [])
        self.assertFalse(estado["violacao"])


if __name__ == "__main__":
    unittest.main()
