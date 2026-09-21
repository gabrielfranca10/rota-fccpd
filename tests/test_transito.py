import unittest
from datetime import datetime, timedelta

from rota.relogio import BRT
from rota.transito import (BLOQUEIO, PICO, Janela, Transito, calcular_hora_limite,
                           minutos_restantes)

T0 = datetime(2026, 9, 21, 12, 0, tzinfo=BRT)


class TestTransito(unittest.TestCase):
    def test_calculo_simples_sem_janelas(self):
        r = calcular_hora_limite(Transito(), T0, 20, 6.0)
        self.assertEqual(r.hora_pronto, T0 + timedelta(minutes=20))
        self.assertEqual(r.hora_saida, r.hora_pronto)
        self.assertEqual(r.minutos_transito_alvo, round(6.0 / 18.0 * 60))
        self.assertEqual(r.hora_limite, r.hora_saida + timedelta(minutes=r.minutos_transito_alvo))
        self.assertEqual(r.janelas_consideradas, ())

    def test_entrega_expressa_e_mais_rapida(self):
        padrao = calcular_hora_limite(Transito(), T0, 20, 6.0, "PADRAO")
        expressa = calcular_hora_limite(Transito(), T0, 20, 6.0, "EXPRESSA")
        self.assertLess(expressa.hora_limite, padrao.hora_limite)

    def test_bloqueio_empurra_a_saida(self):
        bloqueio = Janela(T0 + timedelta(minutes=20), T0 + timedelta(minutes=35), BLOQUEIO, "acidente")
        tr = Transito().com_janela(bloqueio)
        r = calcular_hora_limite(tr, T0, 20, 6.0)
        # janela inclusiva: bloqueado até o minuto do fim, libera no minuto seguinte
        self.assertEqual(r.hora_saida, bloqueio.fim + timedelta(minutes=1))
        self.assertEqual(r.janelas_consideradas[0][:2], (bloqueio.inicio, r.hora_saida))

    def test_pico_atrasa_mas_nao_bloqueia(self):
        pico = Janela(T0, T0 + timedelta(hours=2), PICO, "hora do almoço")
        tr = Transito().com_janela(pico)
        normal = calcular_hora_limite(Transito(), T0, 20, 6.0)
        com_pico = calcular_hora_limite(tr, T0, 20, 6.0)
        self.assertGreater(com_pico.hora_limite, normal.hora_limite)

    def test_funcao_pura_e_deterministica(self):
        tr = Transito().com_janela(Janela(T0, T0 + timedelta(hours=1), PICO, "x"))
        r1 = calcular_hora_limite(tr, T0, 20, 6.0)
        r2 = calcular_hora_limite(tr, T0, 20, 6.0)
        self.assertEqual(r1, r2)

    def test_versao_imutavel_copy_on_write(self):
        base = Transito()
        novo = base.com_janela(Janela(T0, T0 + timedelta(hours=1), PICO, "x"))
        self.assertEqual((base.versao, novo.versao), (1, 2))
        self.assertEqual(base.janelas, ())
        self.assertEqual(len(novo.janelas), 1)

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            calcular_hora_limite(Transito(), T0, 0, 6.0)
        with self.assertRaises(ValueError):
            calcular_hora_limite(Transito(), T0, 20, 0)
        with self.assertRaises(ValueError):
            calcular_hora_limite(Transito(), T0, 181, 6.0)
        with self.assertRaises(ValueError):
            calcular_hora_limite(Transito(), T0, 20, 51.0)

    def test_pico_cobrindo_todo_o_trajeto_dobra_o_tempo(self):
        # 6 km a 18 km/h = 20 min; em pico a velocidade cai à metade, então o trajeto leva 40 min
        pico = Janela(T0, T0 + timedelta(hours=3), PICO, "hora do almoço")
        r = calcular_hora_limite(Transito().com_janela(pico), T0, 20, 6.0)
        self.assertEqual(r.hora_saida, T0 + timedelta(minutes=20))
        self.assertEqual(r.hora_limite, r.hora_saida + timedelta(minutes=40))
        self.assertEqual(len(r.janelas_consideradas), 1)
        self.assertEqual(r.janelas_consideradas[0], (r.hora_saida, r.hora_limite, "trânsito intenso"))

    def test_bloqueio_no_meio_do_trajeto_para_o_avanco(self):
        # sai às 12:20; roda 5 min; bloqueio de 12:25 a 12:34 (inclusive) para o avanço até 12:35;
        # faltam 15 min de trajeto, então chega às 12:50
        bloqueio = Janela(T0 + timedelta(minutes=25), T0 + timedelta(minutes=34), BLOQUEIO, "acidente")
        r = calcular_hora_limite(Transito().com_janela(bloqueio), T0, 20, 6.0)
        self.assertEqual(r.hora_saida, T0 + timedelta(minutes=20))
        self.assertEqual(r.hora_limite, T0 + timedelta(minutes=50))
        self.assertEqual(r.janelas_consideradas,
                         ((T0 + timedelta(minutes=25), T0 + timedelta(minutes=35), "via bloqueada: acidente"),))

    def test_janela_inclui_as_duas_pontas(self):
        j = Janela(T0, T0 + timedelta(minutes=10), PICO, "x")
        self.assertTrue(j.cobre(T0))
        self.assertTrue(j.cobre(T0 + timedelta(minutes=10)))
        self.assertFalse(j.cobre(T0 - timedelta(seconds=1)))
        self.assertFalse(j.cobre(T0 + timedelta(minutes=10, seconds=1)))

    def test_minutos_restantes(self):
        limite = T0 + timedelta(minutes=30)
        self.assertEqual(minutos_restantes(Transito(), T0, limite), 30)
        self.assertEqual(minutos_restantes(Transito(), limite, limite), 0)
        self.assertEqual(minutos_restantes(Transito(), limite + timedelta(minutes=5), limite), 0)


if __name__ == "__main__":
    unittest.main()
