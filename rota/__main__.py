"""Uso:  python -m rota [--porta 8080] [--relogio-simulado 2026-09-21T11:00] ..."""
import argparse
import logging
import signal
import threading
from datetime import datetime

from .http_api import ServidorComPool
from .nucleo import Nucleo
from .relogio import BRT, RelogioSimulado
from .seed import popular


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="rota", description="rota — núcleo de despacho de pedidos (single-node)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8080)
    ap.add_argument("--http-workers", type=int, default=32)
    ap.add_argument("--ingestao-workers", type=int, default=4)
    ap.add_argument("--fila", type=int, default=1000, help="capacidade da fila de ingestão")
    ap.add_argument("--janela-risco", type=int, default=10, help="minutos para o pedido virar EM_RISCO")
    ap.add_argument("--intervalo-monitor", type=float, default=1.0)
    ap.add_argument("--restaurantes", type=int, default=20, help="restaurantes fictícios pré-cadastrados")
    ap.add_argument("--relogio-simulado", metavar="AAAA-MM-DDTHH:MM",
                    help="usa um relógio controlável começando neste instante (permite avançar o tempo)")
    ap.add_argument("--log", default="INFO")
    a = ap.parse_args(argv)

    logging.basicConfig(level=a.log.upper(),
                        format="%(asctime)s %(levelname)-5s [%(threadName)s] %(name)s: %(message)s")
    relogio = None
    if a.relogio_simulado:
        relogio = RelogioSimulado(datetime.fromisoformat(a.relogio_simulado).replace(tzinfo=BRT))
    nucleo = Nucleo(relogio, workers=a.ingestao_workers, tamanho_fila=a.fila,
                    janela_risco_min=a.janela_risco, intervalo_monitor=a.intervalo_monitor)
    popular(nucleo, a.restaurantes)
    nucleo.iniciar()

    servidor = ServidorComPool((a.host, a.porta), nucleo, workers=a.http_workers)
    aceitador = threading.Thread(target=servidor.serve_forever, name="http-aceitador", daemon=True)
    aceitador.start()
    logging.info("rota ouvindo em http://%s:%d  (Ctrl+C para encerrar)", a.host, servidor.server_port)

    parar = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: parar.set())
    try:
        while not parar.wait(0.5):   # espera com timeout: Ctrl+C funciona também no Windows
            pass
    except KeyboardInterrupt:
        pass
    # um 2º Ctrl+C no meio do desligamento interromperia a drenagem da fila: ignoramos
    aviso = lambda *_: logging.warning("já estou encerrando; aguarde a fila ser drenada")  # noqa: E731
    signal.signal(signal.SIGINT, aviso)
    signal.signal(signal.SIGTERM, aviso)
    logging.info("encerrando: parando de aceitar conexões...")
    servidor.shutdown()        # para o loop de accept (chamado de OUTRA thread, senão trava)
    servidor.server_close()    # espera as requisições em andamento
    nucleo.parar()             # drena as filas e encerra workers
    logging.info("encerrado")


if __name__ == "__main__":
    main()
