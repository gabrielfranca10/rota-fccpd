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

    def test_minutos_restantes(self):
        limite = T0 + timedelta(minutes=30)
        self.assertEqual(minutos_restantes(Transito(), T0, limite), 30)
        self.assertEqual(minutos_restantes(Transito(), limite, limite), 0)
        self.assertEqual(minutos_restantes(Transito(), limite + timedelta(minutes=5), limite), 0)


if __name__ == "__main__":
    unittest.main()
