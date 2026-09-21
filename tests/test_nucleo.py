import unittest

from rota.dominio import ATRASADO, EM_RISCO, ENTREGUE, NAO_VINCULADA, NO_PRAZO, PROCESSADA, SEM_PEDIDO
from rota.dominio import Conflito, ErroValidacao, NaoEncontrado, Sobrecarga
from tests.apoio import notif, novo_nucleo


class TestNucleo(unittest.TestCase):
    def setUp(self):
        self.n = novo_nucleo()

    def tearDown(self):
        self.n.parar()

    def processar(self, dados):
        view, nova = self.n.receber_notificacao(dados)
        self.assertTrue(self.n.aguardar_ocioso())
        return self.n.obter_notificacao(view["notificacao_id"])

    def test_pedido_criado_e_despachado(self):
        nf = self.processar(notif(0))
        self.assertEqual(nf["status"], PROCESSADA)
        pedido = self.n.obter_pedido(nf["pedido_id"])
        self.assertEqual(pedido["status"], NO_PRAZO)
        self.assertIsNotNone(pedido["entregador_responsavel_id"])
        self.assertIsNotNone(pedido["hora_limite_entrega"])

    def test_duplicata_retorna_a_mesma_notificacao(self):
        a, nova_a = self.n.receber_notificacao(notif(1, descricao="Preparo:   18 MIN"))
        b, nova_b = self.n.receber_notificacao(notif(1, descricao="preparo: 18 min"))
        self.assertTrue(nova_a)
        self.assertFalse(nova_b)
        self.assertEqual(a["notificacao_id"], b["notificacao_id"])

    def test_extrai_preparo_da_descricao_e_sem_pedido(self):
        d = notif(2, descricao="Tempo estimado de preparo: 12 minutos.")
        self.assertEqual(self.n.obter_pedido(self.processar(d)["pedido_id"])["tempo_preparo_min"], 12)
        d = notif(2, descricao="Cliente cancelou o pedido antes do preparo.")
        self.assertEqual(self.processar(d)["status"], SEM_PEDIDO)

    def test_restaurante_desconhecido_vai_para_triagem(self):
        nf = self.processar(notif(0, restaurante_id="rest-9999"))
        self.assertEqual(nf["status"], NAO_VINCULADA)

    def test_validacoes(self):
        casos = [notif(0, restaurante_id="../etc"), notif(0, numero_pedido="xyz"),
                 notif(0, plataforma="MERCADO_LIVRE"), notif(0, hora_notificacao="21/09/2026"),
                 notif(0, distancia_km=0), notif(0, distancia_km=100), notif(0, descricao=""),
                 notif(0, prioridade="URGENTISSIMA"), notif(0, tempo_preparo_min=0),
                 notif(0, tempo_preparo_min=True)]
        for ruim in casos:
            with self.assertRaises(ErroValidacao):
                self.n.receber_notificacao(ruim)

    def test_status_derivado_do_relogio(self):
        pid = self.processar(notif(3, preparo=10, distancia=1.0))["pedido_id"]
        pedido = self.n.obter_pedido(pid)
        self.assertEqual(pedido["status"], NO_PRAZO)
        self.n.relogio.avancar(minutes=8)          # preparo 10 + trajeto ~3 min = limite aos 13 min
        self.assertEqual(self.n.obter_pedido(pid)["status"], EM_RISCO)
        self.n.relogio.avancar(minutes=10)
        self.assertEqual(self.n.obter_pedido(pid)["status"], ATRASADO)

    def test_confirmacao_de_entrega(self):
        pid = self.processar(notif(0))["pedido_id"]
        outro = "ent-marcia" if self.n.obter_pedido(pid)["entregador_responsavel_id"] != "ent-marcia" \
            else "ent-caio"
        with self.assertRaises(Conflito):                  # não é o responsável
            self.n.confirmar_entrega(pid, {"entregador_id": outro, "codigo_confirmacao": "C1"})
        responsavel = self.n.obter_pedido(pid)["entregador_responsavel_id"]
        v = self.n.confirmar_entrega(pid, {"entregador_id": responsavel, "codigo_confirmacao": "C1"})
        self.assertEqual(v["status"], ENTREGUE)
        self.assertFalse(v["entregue_atrasado"])
        self.assertEqual(self.n.confirmar_entrega(pid, {"entregador_id": responsavel,
                                                        "codigo_confirmacao": "C1"})["status"],
                         ENTREGUE)                          # idempotente
        with self.assertRaises(Conflito):
            self.n.confirmar_entrega(pid, {"entregador_id": responsavel, "codigo_confirmacao": "C2"})
        with self.assertRaises(Conflito):
            self.n.redespachar_pedido(pid, {"entregador_destino": "ent-duda"})
        self.assertTrue(self.n.auditoria()["ok"])

    def test_confirmacao_apos_atraso_marca_entregue_atrasado(self):
        pid = self.processar(notif(0, preparo=10, distancia=1.0))["pedido_id"]
        self.n.relogio.avancar(minutes=30)
        responsavel = self.n.obter_pedido(pid)["entregador_responsavel_id"]
        v = self.n.confirmar_entrega(pid, {"entregador_id": responsavel, "codigo_confirmacao": "C1"})
        self.assertEqual(v["status"], ENTREGUE)
        self.assertTrue(v["entregue_atrasado"])            # entrega atrasada ainda é registrada
        self.assertTrue(self.n.auditoria()["ok"])

    def test_redespacho(self):
        pid = self.processar(notif(0))["pedido_id"]
        origem = self.n.obter_pedido(pid)["entregador_responsavel_id"]
        destino = next(e for e in ("ent-joao", "ent-marcia", "ent-caio", "ent-duda") if e != origem)
        v = self.n.redespachar_pedido(pid, {"entregador_destino": destino})
        self.assertEqual(v["entregador_responsavel_id"], destino)
        with self.assertRaises(ErroValidacao):
            self.n.redespachar_pedido(pid, {"entregador_destino": "ninguem"})
        with self.assertRaises(NaoEncontrado):
            self.n.redespachar_pedido("ped_x", {"entregador_destino": destino})

    def test_capacidade_limita_atribuicao_e_fila_de_espera(self):
        n = novo_nucleo(restaurantes=1, iniciar=False)
        n._entregadores.clear(); n._lock_entregador.clear(); n._agenda.clear()  # começa sem entregadores
        n.iniciar()
        n.cadastrar_entregador({"entregador_id": "ent-solo", "nome": "Solo", "veiculo": "moto", "capacidade": 1})
        v1, _ = n.receber_notificacao(notif(1))
        v2, _ = n.receber_notificacao(notif(2))
        self.assertTrue(n.aguardar_ocioso())
        p1 = n.obter_pedido(n.obter_notificacao(v1["notificacao_id"])["pedido_id"])
        p2 = n.obter_pedido(n.obter_notificacao(v2["notificacao_id"])["pedido_id"])
        self.assertEqual(p1["entregador_responsavel_id"], "ent-solo")
        self.assertIsNone(p2["entregador_responsavel_id"])
        self.assertEqual(n.estatisticas()["pedidos_aguardando_entregador"], 1)

        n.confirmar_entrega(p1["pedido_id"], {"entregador_id": "ent-solo", "codigo_confirmacao": "C1"})
        self.assertTrue(n.aguardar_ocioso())
        self.assertEqual(n.obter_pedido(p2["pedido_id"])["entregador_responsavel_id"], "ent-solo")
        self.assertEqual(n.estatisticas()["pedidos_aguardando_entregador"], 0)
        self.assertTrue(n.auditoria()["ok"])
        n.parar()

    def test_redespacho_respeita_capacidade(self):
        n = novo_nucleo(restaurantes=1, iniciar=False)
        n._entregadores.clear(); n._lock_entregador.clear(); n._agenda.clear()
        n.iniciar()
        n.cadastrar_entregador({"entregador_id": "ent-a", "nome": "A", "veiculo": "moto", "capacidade": 1})
        n.cadastrar_entregador({"entregador_id": "ent-b", "nome": "B", "veiculo": "moto", "capacidade": 1})
        v1, _ = n.receber_notificacao(notif(1))
        v2, _ = n.receber_notificacao(notif(2))
        self.assertTrue(n.aguardar_ocioso())
        p1 = n.obter_notificacao(v1["notificacao_id"])["pedido_id"]
        p2 = n.obter_notificacao(v2["notificacao_id"])["pedido_id"]
        # ambos entregadores ficam com 1/1; redespachar um pro outro deve falhar
        with self.assertRaises(Conflito):
            n.redespachar_pedido(p1, {"entregador_destino": n.obter_pedido(p2)["entregador_responsavel_id"]})
        n.parar()

    def test_janela_recalcula_pedidos_existentes(self):
        pid = self.processar(notif(0))["pedido_id"]
        antes = self.n.obter_pedido(pid)["hora_limite_entrega"]
        r = self.n.declarar_janela({"inicio": "2026-09-21T11:00:00-03:00", "fim": "2026-09-21T12:00:00-03:00",
                                    "tipo": "PICO", "motivo": "hora do almoço"})
        self.assertEqual(r["versao"], 2)
        self.assertTrue(self.n.aguardar_ocioso())
        pedido = self.n.obter_pedido(pid)
        self.assertGreaterEqual(pedido["hora_limite_entrega"], antes)
        self.assertEqual(pedido["transito_versao"], 2)
        self.assertGreaterEqual(pedido["recalculos"], 1)
        tipos = [a["tipo"] for a in self.n.alertas.listar()["alertas"]]
        self.assertIn("PEDIDO_RECALCULADO", tipos)
        self.assertTrue(self.n.auditoria()["ok"])

    def test_monitor_alerta_uma_vez_por_nivel(self):
        self.processar(notif(0, preparo=10, distancia=1.0))
        self.n.relogio.avancar(minutes=8)
        self.assertEqual(self.n.executar_monitor(), 1)
        self.assertEqual(self.n.executar_monitor(), 0)     # não repete
        self.n.relogio.avancar(minutes=10)
        self.assertEqual(self.n.executar_monitor(), 1)     # EM_RISCO -> ATRASADO

    def test_fila_cheia_devolve_sobrecarga_e_nao_registra(self):
        n = novo_nucleo(fila=2, iniciar=False)
        n._aceitando = True                                 # aceita, mas sem workers consumindo
        n.receber_notificacao(notif(0, descricao="a. Tempo estimado de preparo: 10 minutos."))
        n.receber_notificacao(notif(0, descricao="b. Tempo estimado de preparo: 10 minutos."))
        with self.assertRaises(Sobrecarga):
            n.receber_notificacao(notif(0, descricao="c. Tempo estimado de preparo: 10 minutos."))
        self.assertEqual(len(n._notificacoes), 2)           # a rejeitada não "sujou" o índice

    def test_desligado_rejeita_e_drena(self):
        for i in range(30):
            self.n.receber_notificacao(notif(i % 10, descricao=f"t{i}. Tempo estimado de preparo: 10 minutos."))
        self.n.parar()
        self.assertTrue(all(n["status"] != "PENDENTE" for n in
                            [self.n.obter_notificacao(x) for x in list(self.n._notificacoes)]))
        with self.assertRaises(Sobrecarga):
            self.n.receber_notificacao(notif(0, descricao="depois. Tempo estimado de preparo: 10 minutos."))

    # ------------------------------------------------------------------ fila de espera e desligamento
    def _nucleo_com_um_entregador(self, capacidade):
        n = novo_nucleo(restaurantes=1, iniciar=False)
        n._entregadores.clear(); n._lock_entregador.clear(); n._agenda.clear()  # começa sem entregadores
        n.iniciar()
        n.cadastrar_entregador({"entregador_id": "ent-solo", "nome": "Solo", "veiculo": "moto",
                                "capacidade": capacidade})
        return n

    def test_vaga_liberada_vai_para_o_pedido_mais_urgente(self):
        """A fila de espera é ordenada pela hora limite: a vaga não vai para um pedido qualquer."""
        n = self._nucleo_com_um_entregador(capacidade=1)
        n.receber_notificacao(notif(0, preparo=15))                    # ocupa a única vaga
        self.assertTrue(n.aguardar_ocioso())
        for i in range(1, 31):
            preparo = 5 + (i * 7) % 60                                 # prazos bem diferentes
            n.receber_notificacao(notif(i, preparo=preparo,
                                        descricao=f"e{i}. Tempo estimado de preparo: {preparo} minutos."))
        self.assertTrue(n.aguardar_ocioso())
        pedidos = n.listar_pedidos(limite=1000)
        ocupante = next(p for p in pedidos if p["entregador_responsavel_id"] == "ent-solo")
        esperando = [p for p in pedidos if p["entregador_responsavel_id"] is None]
        mais_urgente = min(esperando, key=lambda p: (p["hora_limite_entrega"], p["pedido_id"]))
        self.assertEqual(len(esperando), 30)

        n.confirmar_entrega(ocupante["pedido_id"], {"entregador_id": "ent-solo", "codigo_confirmacao": "C"})
        self.assertTrue(n.aguardar_ocioso())
        com_vaga = [p for p in n.listar_pedidos(limite=1000)
                    if p["entregador_responsavel_id"] == "ent-solo" and p["status"] != ENTREGUE]
        self.assertEqual([p["pedido_id"] for p in com_vaga], [mais_urgente["pedido_id"]])
        self.assertTrue(n.auditoria()["ok"])
        n.parar()

    def test_varias_vagas_vao_para_os_mais_urgentes_em_ordem(self):
        n = self._nucleo_com_um_entregador(capacidade=2)
        for i in (0, 1):
            n.receber_notificacao(notif(i, preparo=15))
        self.assertTrue(n.aguardar_ocioso())
        for i in range(2, 22):
            preparo = 5 + (i * 11) % 55
            n.receber_notificacao(notif(i, preparo=preparo,
                                        descricao=f"e{i}. Tempo estimado de preparo: {preparo} minutos."))
        self.assertTrue(n.aguardar_ocioso())
        pedidos = n.listar_pedidos(limite=1000)
        ocupantes = [p for p in pedidos if p["entregador_responsavel_id"] == "ent-solo"]
        esperando = sorted((p for p in pedidos if p["entregador_responsavel_id"] is None),
                           key=lambda p: (p["hora_limite_entrega"], p["pedido_id"]))
        for p in ocupantes:
            n.confirmar_entrega(p["pedido_id"], {"entregador_id": "ent-solo", "codigo_confirmacao": "C"})
        self.assertTrue(n.aguardar_ocioso())
        novos = {p["pedido_id"] for p in n.listar_pedidos(limite=1000)
                 if p["entregador_responsavel_id"] == "ent-solo" and p["status"] != ENTREGUE}
        self.assertEqual(novos, {esperando[0]["pedido_id"], esperando[1]["pedido_id"]})
        n.parar()

    def test_desligamento_drena_tambem_o_despacho(self):
        """Todo trabalho aceito é processado, inclusive o que a ingestão ainda gera para o despacho."""
        n = novo_nucleo(workers=4, fila=5000, restaurantes=5)
        for i in range(1000):
            n.receber_notificacao(notif(i, restaurante=i % 5, numero_pedido=f"IFOOD-{i:06d}",
                                        descricao=f"x{i}. Tempo estimado de preparo: 20 minutos."))
        n.parar()
        self.assertTrue(n.ocioso(), "filas de ingestão, recálculo e despacho deveriam estar vazias")

    # ------------------------------------------------------------------ instantes e alertas
    def test_instante_com_z_ou_outro_fuso_e_o_mesmo_evento(self):
        """11:00 em Brasília = 14:00Z: o retry do webhook em UTC é a mesma notificação."""
        a, nova_a = self.n.receber_notificacao(notif(5, hora="2026-09-21T11:00:00-03:00"))
        b, nova_b = self.n.receber_notificacao(notif(5, hora="2026-09-21T14:00:00Z"))
        c, nova_c = self.n.receber_notificacao(notif(5, hora="2026-09-21T14:00:00+00:00"))
        self.assertTrue(nova_a)
        self.assertFalse(nova_b)
        self.assertFalse(nova_c)
        self.assertEqual(a["notificacao_id"], b["notificacao_id"])
        self.assertTrue(b["hora_notificacao"].endswith("-03:00"))      # tudo em horário de Brasília

    def test_alerta_e_carimbado_com_o_relogio_do_sistema(self):
        self.n.declarar_janela({"inicio": "2026-09-21T11:00:00-03:00", "fim": "2026-09-21T11:30:00-03:00",
                                "tipo": "PICO", "motivo": "teste"})
        alerta = self.n.alertas.listar()["alertas"][0]
        self.assertEqual(alerta["em"], "2026-09-21T11:00:00-03:00")    # relógio simulado, não o de parede


if __name__ == "__main__":
    unittest.main()
