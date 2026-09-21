"""Demonstra a condição de corrida da deduplicação (sem servidor):  python scripts/demo_corrida.py

50 threads recebem a MESMA notificação de pedido no mesmo instante (retries de webhook vindos
de conexões diferentes do agregador).
  - Versão ingênua: 'verifica se já existe' e 'insere' em passos separados.
  - Versão rota: verificar + inserir dentro da mesma seção crítica.
"""
import threading
import time


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


class DeduplicadorRota:
    def __init__(self):
        self.vistos, self.pedidos_criados = set(), 0
        self._lock = threading.Lock()

    def receber(self, digital):
        with self._lock:                       # verificar + inserir são UMA operação atômica
            if digital in self.vistos:
                return
            self.vistos.add(digital)
            self.pedidos_criados += 1
        time.sleep(0.001)                      # trabalho lento fica FORA do lock


def rodar(classe, n=50):
    d, barreira = classe(), threading.Barrier(n)

    def t():
        barreira.wait()
        d.receber("IFOOD|IFOOD-000123|2026-09-21T11:00:00|pedido: 2x x-burger...")

    ts = [threading.Thread(target=t) for _ in range(n)]
    [x.start() for x in ts]
    [x.join() for x in ts]
    return d.pedidos_criados


if __name__ == "__main__":
    print("Mesma notificação recebida por 50 threads simultâneas. Pedidos criados (esperado: 1)")
    print(f"  sem sincronização : {rodar(DeduplicadorIngenuo)}   <- pedidos duplicados na agenda do entregador")
    print(f"  rota (com lock)   : {rodar(DeduplicadorRota)}")
