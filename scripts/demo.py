"""Roteiro guiado para a apresentação. Suba o servidor antes com:
    python -m rota --relogio-simulado 2026-09-21T11:00
e rode:  python scripts/demo.py
"""
import http.client
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rota.seed import restaurante_id  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")   # console do Windows (cp1252) não tem "▶"/"✓" etc.

HOST, PORTA = "127.0.0.1", int(os.environ.get("ROTA_PORTA", "8080"))


def req(metodo, caminho, corpo=None):
    c = http.client.HTTPConnection(HOST, PORTA, timeout=10)
    c.request(metodo, caminho, body=json.dumps(corpo) if corpo is not None else None,
              headers={"Content-Type": "application/json"})
    r = c.getresponse()
    dados = json.loads(r.read() or b"null")
    c.close()
    return r.status, dados


def passo(titulo):
    input(f"\n\033[1m▶ {titulo}\033[0m  [Enter]")


def aguardar():
    while True:
        m = req("GET", "/api/v1/metricas")[1]
        if not m["fila_ingestao"] and not m["fila_despacho"] and not m["recalculo_pendente"]:
            return
        time.sleep(0.05)


def mostrar_pedido(pid):
    p = req("GET", f"/api/v1/pedidos/{pid}")[1]
    print(f"   pedido {p['numero_pedido']} | limite {p['hora_limite_entrega']} | status {p['status']} | "
          f"restam {p['minutos_restantes']} min | entregador {p['entregador_responsavel_id']} | "
          f"trânsito v{p['transito_versao']}")


if __name__ == "__main__":
    try:
        req("GET", "/health")
    except OSError:
        sys.exit(f"Servidor não encontrado em {HOST}:{PORTA}. Suba antes: "
                 "python -m rota --relogio-simulado 2026-09-21T11:00")
    rid = restaurante_id(0)
    corpo = {"restaurante_id": rid, "numero_pedido": "IFOOD-000001", "plataforma": "IFOOD",
             "hora_notificacao": "2026-09-21T11:00:00-03:00",
             "descricao": "Pedido: 2x X-Burger, 1x Batata. Tempo estimado de preparo: 18 minutos.",
             "distancia_km": 6.0}
    passo("1. Chega uma notificação de pedido do iFood (resposta 202: aceita e enfileirada)")
    s, notif = req("POST", "/api/v1/notificacoes", corpo)
    print(f"   HTTP {s} -> {notif['notificacao_id']} status={notif['status']}")
    aguardar()
    pid = req("GET", f"/api/v1/notificacoes/{notif['notificacao_id']}")[1]["pedido_id"]
    mostrar_pedido(pid)

    passo("2. A MESMA notificação chega de novo (retry do webhook do agregador: deduplicação por conteúdo)")
    s, dup = req("POST", "/api/v1/notificacoes", corpo)
    print(f"   HTTP {s} -> mesmo id? {dup['notificacao_id'] == notif['notificacao_id']} | "
          f"duplicatas recebidas: {dup['duplicatas_recebidas']}")

    passo("3. Central declara pico de trânsito das 11h às 12h (novo trânsito + recálculo)")
    s, r = req("POST", "/api/v1/transito/janelas", {"inicio": "2026-09-21T11:00:00-03:00",
                                                     "fim": "2026-09-21T12:00:00-03:00",
                                                     "tipo": "PICO", "motivo": "hora do almoço"})
    print(f"   HTTP {s} -> trânsito versão {r['versao']}")
    aguardar()
    mostrar_pedido(pid)

    passo("4. O tempo passa 25 minutos (relógio simulado): o monitor emite alerta de risco/atraso")
    print("  ", req("POST", "/api/v1/admin/relogio", {"minutos": 25})[1])
    mostrar_pedido(pid)
    for al in req("GET", "/api/v1/alertas?apos=0")[1]["alertas"][-3:]:
        print(f"   alerta #{al['seq']}: {al['tipo']}")

    passo("5. A moto do João quebrou: pedido redespachado para a Márcia")
    req("POST", f"/api/v1/pedidos/{pid}/redespacho", {"entregador_destino": "ent-marcia"})
    mostrar_pedido(pid)

    passo("6. Márcia confirma a entrega")
    s, p = req("POST", f"/api/v1/pedidos/{pid}/entrega", {"entregador_id": "ent-marcia", "codigo_confirmacao": "FOTO-0001"})
    print(f"   HTTP {s} -> {p['status']} em {p['entregue_em']} (atrasada? {p['entregue_atrasado']})")

    passo("7. Auditoria: invariantes + comparação com recálculo sequencial")
    print("  ", req("GET", "/api/v1/auditoria")[1])
