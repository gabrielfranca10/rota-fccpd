"""Demonstra a condição de corrida da deduplicação (sem servidor):  python scripts/demo_corrida.py

50 threads recebem a MESMA notificação de pedido no mesmo instante (retries de webhook vindos
de conexões diferentes do agregador).
  - Padrão ingênuo: 'verifica se já existe' e 'insere' em passos separados. É um exemplo didático
    do bug, não o código do rota.
  - Rota: o núcleo de verdade (`Nucleo.receber_notificacao`), onde verificar + inserir acontecem
    dentro da mesma seção crítica. Conta os pedidos que ele realmente criou.
"""
import os
import sys
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rota.nucleo import Nucleo  # noqa: E402
from rota.relogio import BRT, RelogioSimulado  # noqa: E402
from rota.seed import popular, restaurante_id  # noqa: E402

THREADS = 50


class DeduplicadorIngenuo:
    def __init__(self):
        self.vistos, self.pedidos_criados = set(), 0
        self._lock = threading.Lock()

    def receber(self, digital):
        if digital not in self.vistos:         # 1) verifica  ...
            time.sleep(0.001)                  #    (latência realista: validar, calcular hora limite, gravar)
            self.vistos.add(digital)           # 2) ... age — outra thread pode ter passado no meio!
            with self._lock:
                self.pedidos_criados += 1


def rodar_ingenuo(n=THREADS):
    d, barreira = DeduplicadorIngenuo(), threading.Barrier(n)

    def t():
        barreira.wait()
        d.receber("IFOOD|IFOOD-000123|2026-09-21T11:00:00|pedido: 2x x-burger...")

    ts = [threading.Thread(target=t) for _ in range(n)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    return d.pedidos_criados


def rodar_rota(n=THREADS):
    """Mesmo cenário contra o núcleo real: quantos pedidos ele criou para a mesma notificação?"""
    nucleo = Nucleo(RelogioSimulado(datetime(2026, 9, 21, 11, 0, tzinfo=BRT)), intervalo_monitor=3600)
    popular(nucleo, 2)
    nucleo.iniciar()
    barreira = threading.Barrier(n)
    corpo = {"restaurante_id": restaurante_id(0), "numero_pedido": "IFOOD-000123", "plataforma": "IFOOD",
             "hora_notificacao": "2026-09-21T11:00:00-03:00", "distancia_km": 5.0,
             "descricao": "Pedido: 2x X-Burger. Tempo estimado de preparo: 18 minutos."}

    def t():
        barreira.wait()
        nucleo.receber_notificacao(dict(corpo))

    ts = [threading.Thread(target=t) for _ in range(n)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    nucleo.aguardar_ocioso()
    criados = len(nucleo.listar_pedidos(limite=1000))
    nucleo.parar()
    return criados


if __name__ == "__main__":
    print(f"Mesma notificação recebida por {THREADS} threads simultâneas. Pedidos criados (esperado: 1)")
    print(f"  sem sincronização (padrão ingênuo) : {rodar_ingenuo()}   <- pedidos duplicados na agenda do entregador")
    print(f"  rota (Nucleo real, com lock)       : {rodar_rota()}")
