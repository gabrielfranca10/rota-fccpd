"""Teste de carga contra o servidor rodando:  python scripts/carga.py [--clientes 50]

Simula a 'rajada do almoço': dezenas de plataformas enviando notificações de pedido (com
duplicatas vindas de retries de webhook), entregadores confirmando entrega e redespachando,
e a central declarando picos de trânsito no meio do processo. No fim, pede a auditoria ao
servidor. Código de saída 0 = nenhum erro e todas as invariantes OK.
"""
import argparse
import http.client
import json
import os
import random
import statistics
import sys
import threading
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from rota.seed import restaurante_id  # noqa: E402


class Cliente:
    def __init__(self, host, porta):
        self.host, self.porta = host, porta

    def req(self, metodo, caminho, corpo=None):
        dados = json.dumps(corpo) if corpo is not None else None
        for tentativa in range(4):
            c = http.client.HTTPConnection(self.host, self.porta, timeout=30)
            try:
                c.request(metodo, caminho, body=dados, headers={"Content-Type": "application/json"})
                r = c.getresponse()
                return r.status, json.loads(r.read() or b"null")
            except OSError:
                # Windows esgota momentaneamente as portas efêmeras quando dezenas de threads
                # abrem milhares de conexões novas em poucos segundos (TIME_WAIT); não é falha
                # do servidor nem do núcleo, então só espera um instante e tenta de novo.
                if tentativa == 3:
                    raise
                time.sleep(0.05 * (tentativa + 1))
            finally:
                c.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--porta", type=int, default=8080)
    ap.add_argument("--clientes", type=int, default=50)
    ap.add_argument("--por-cliente", type=int, default=100)
    ap.add_argument("--restaurantes", type=int, default=20, help="deve bater com o --restaurantes do servidor")
    ap.add_argument("--entregadores", type=int, default=4, help="threads simulando entregadores")
    ap.add_argument("--distintas", type=int, default=2000, help="notificações distintas (o resto é duplicata)")
    a = ap.parse_args()
    cli = Cliente(a.host, a.porta)
    if cli.req("GET", "/health")[0] != 200:
        sys.exit("servidor não respondeu em /health")

    latencias = {}          # operação -> lista (cada thread grava na SUA lista; junta no fim)
    status_contagem = {}
    lk = threading.Lock()
    barreira = threading.Barrier(a.clientes + a.entregadores + 1)
    fim_ingestao = threading.Event()

    def medir(local, op, metodo, caminho, corpo=None):
        t0 = time.perf_counter()
        try:
            s, r = cli.req(metodo, caminho, corpo)
        except Exception as e:
            s, r = f"EXC {type(e).__name__}", None
        local.setdefault(op, []).append(time.perf_counter() - t0)
        local.setdefault("_status", []).append((op, s))
        return s, r

    def juntar(local):
        with lk:
            for op, v in local.items():
                if op == "_status":
                    for o, s in v:
                        status_contagem[(o, s)] = status_contagem.get((o, s), 0) + 1
                else:
                    latencias.setdefault(op, []).extend(v)

    def notificador(i):
        rnd, local = random.Random(i), {}
        barreira.wait()
        for k in range(a.por_cliente):
            j = rnd.randrange(a.distintas)
            corpo = {"restaurante_id": restaurante_id(j % a.restaurantes), "numero_pedido": f"IFOOD-{j:06d}",
                     "plataforma": rnd.choice(["IFOOD", "UBEREATS", "RAPPI", "BALCAO"]),
                     "hora_notificacao": "2026-09-21T12:00:00-03:00",
                     "descricao": f"Pedido {j}. Tempo estimado de preparo: {5 + j % 60} minutos.",
                     "distancia_km": round(0.5 + (j % 45), 1),
                     "prioridade": rnd.choice(["PADRAO", "EXPRESSA"])}
            s, _ = medir(local, "notificar", "POST", "/api/v1/notificacoes", corpo)
            while s == 503:                 # backpressure: respeita o Retry-After e tenta de novo
                time.sleep(0.2)
                s, _ = medir(local, "notificar", "POST", "/api/v1/notificacoes", corpo)
        juntar(local)

    def entregadores(semente):
        rnd, local = random.Random(semente), {}
        barreira.wait()
        while not fim_ingestao.is_set():
            s, r = medir(local, "listar", "GET", "/api/v1/pedidos?status=NO_PRAZO&limite=50")
            if s == 200 and r["pedidos"]:
                p = rnd.choice(r["pedidos"])
                if not p["entregador_responsavel_id"]:
                    continue
                if rnd.random() < 0.5:
                    medir(local, "redespachar", "POST", f"/api/v1/pedidos/{p['pedido_id']}/redespacho",
                          {"entregador_destino": rnd.choice(["ent-joao", "ent-marcia", "ent-caio", "ent-duda"])})
                else:
                    medir(local, "confirmar", "POST", f"/api/v1/pedidos/{p['pedido_id']}/entrega",
                          {"entregador_id": p["entregador_responsavel_id"], "codigo_confirmacao": f"FOTO-{rnd.random()}"})
        juntar(local)

    def central():
        local = {}
        barreira.wait()
        for h in range(3):
            time.sleep(0.3)
            medir(local, "declarar_janela", "POST", "/api/v1/transito/janelas",
                  {"inicio": "2026-09-21T12:00:00-03:00", "fim": "2026-09-21T12:30:00-03:00",
                   "tipo": "PICO" if h % 2 == 0 else "BLOQUEIO", "motivo": f"evento {h}"})
        juntar(local)

    ts = [threading.Thread(target=notificador, args=(i,)) for i in range(a.clientes)]
    ts += [threading.Thread(target=entregadores, args=(s,)) for s in range(a.entregadores)]
    ts.append(threading.Thread(target=central))
    t0 = time.perf_counter()
    for t in ts:
        t.start()
    for t in ts[:a.clientes]:
        t.join()
    fim_ingestao.set()
    for t in ts[a.clientes:]:
        t.join()
    duracao = time.perf_counter() - t0

    while True:                              # espera o servidor esvaziar fila e recálculos
        m = cli.req("GET", "/api/v1/metricas")[1]
        if m["fila_ingestao"] == 0 and m["fila_despacho"] == 0 and not m["recalculo_pendente"]:
            break
        time.sleep(0.1)
    audit = cli.req("GET", "/api/v1/auditoria")[1]

    total = sum(len(v) for v in latencias.values())
    print(f"\n=== Teste de carga: {a.clientes} clientes simultâneos ===")
    print(f"requisições: {total} em {duracao:.2f} s  ->  {total / duracao:.0f} req/s")
    print(f"{'operação':<14}{'qtd':>7}{'p50 ms':>9}{'p95 ms':>9}{'p99 ms':>9}{'máx ms':>9}")
    for op, v in sorted(latencias.items()):
        v = sorted(v)
        q = statistics.quantiles(v, n=100, method="inclusive") if len(v) > 1 else v * 99
        print(f"{op:<14}{len(v):>7}{q[49]*1e3:>9.1f}{q[94]*1e3:>9.1f}{q[98]*1e3:>9.1f}{v[-1]*1e3:>9.1f}")
    print("\nrespostas por (operação, status HTTP):")
    for (op, s), c in sorted(status_contagem.items(), key=lambda x: str(x)):
        print(f"  {op:<14}{str(s):<12}{c}")
    ruins = {k: v for k, v in status_contagem.items() if not isinstance(k[1], int) or k[1] >= 500 and k[1] != 503}
    print("\nauditoria:", json.dumps(audit, ensure_ascii=False))
    ok = audit["ok"] and audit["oraculo_executado"] and not ruins
    print("\nRESULTADO:", "OK — nenhuma falha e todas as invariantes preservadas" if ok else f"FALHA {ruins}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
