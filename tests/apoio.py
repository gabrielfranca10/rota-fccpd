from datetime import datetime

from rota.nucleo import Nucleo
from rota.relogio import BRT, RelogioSimulado
from rota.seed import popular, restaurante_id


def novo_nucleo(data="2026-09-21T11:00", workers=4, fila=1000, restaurantes=10, iniciar=True,
                intervalo=3600, janela_risco=10):
    rel = RelogioSimulado(datetime.fromisoformat(data).replace(tzinfo=BRT))
    n = Nucleo(rel, workers=workers, tamanho_fila=fila, intervalo_monitor=intervalo,
              janela_risco_min=janela_risco)
    popular(n, restaurantes)
    if iniciar:
        n.iniciar()
    return n


def notif(i=0, restaurante=0, hora="2026-09-21T11:00:00-03:00", preparo=15, distancia=5.0,
          descricao=None, **extra):
    if descricao is None:
        descricao = f"Pedido de teste {i}. Tempo estimado de preparo: {preparo} minutos."
    d = {"restaurante_id": restaurante_id(restaurante), "numero_pedido": f"IFOOD-{i:06d}",
         "plataforma": "IFOOD", "hora_notificacao": hora, "descricao": descricao,
         "distancia_km": distancia}
    d.update(extra)
    return d
