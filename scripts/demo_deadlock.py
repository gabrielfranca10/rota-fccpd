"""Demonstra deadlock no redespacho de pedidos e a correção:  python scripts/demo_deadlock.py

Thread 1 move um pedido do João para a Márcia; thread 2 move outro da Márcia para o João.
Cada redespacho precisa travar as DUAS agendas.
"""
import threading
import time

agenda_lock = {"ent-joao": threading.Lock(), "ent-marcia": threading.Lock()}


def redespachar(origem, destino, ordenado, resultado):
    primeiro, segundo = sorted((origem, destino)) if ordenado else (origem, destino)
    with agenda_lock[primeiro]:
        time.sleep(0.1)                                    # janela para a outra thread pegar o seu lock
        if not agenda_lock[segundo].acquire(timeout=2):    # timeout só para a demo não travar para sempre
            resultado.append(f"{origem}->{destino}: TRAVOU esperando {segundo} (deadlock)")
            return
        try:
            resultado.append(f"{origem}->{destino}: ok")
        finally:
            agenda_lock[segundo].release()


def cenario(ordenado):
    r = []
    ts = [threading.Thread(target=redespachar, args=("ent-joao", "ent-marcia", ordenado, r)),
          threading.Thread(target=redespachar, args=("ent-marcia", "ent-joao", ordenado, r))]
    [t.start() for t in ts]
    [t.join() for t in ts]
    return r


if __name__ == "__main__":
    print("1) Cada thread trava primeiro a agenda de ORIGEM (espera circular):")
    for linha in cenario(False):
        print("   ", linha)
    print("2) rota: sempre trava em ordem alfabética de entregador_id (sem espera circular):")
    for linha in cenario(True):
        print("   ", linha)
