"""Testes de mutação:  python scripts/mutacoes.py [M1 M4 ...] [--rodadas 3] [--timeout 60]

Injeta, um por vez, os bugs de concorrência que o projeto diz prevenir, numa CÓPIA do código
(o original nunca é tocado), roda a suíte e confere se algum teste falha. Uma mutação que a
suíte NÃO acusa é um teste fraco: o código continuaria "passando" com o bug.

Código de saída 0 = todas as mutações foram detectadas.
Demora alguns minutos: uma mutação que trava o núcleo (M11) só é detectada pelo timeout.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

RAIZ = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
NULO = '__import__("contextlib").nullcontext()'
NUCLEO, RWLOCK = "rota/nucleo.py", "rota/rwlock.py"

# nome -> (arquivo, [(trecho original, trecho com o bug)])
MUTACOES = {
    "M1": ("deduplicação verificada FORA do lock (pausa de 1 ms)", NUCLEO, [(
        "        with self._notif_lock:\n            existente = self._por_digital.get(digital)\n",
        "        existente_fora = self._por_digital.get(digital)\n        time.sleep(0.001)\n"
        "        with self._notif_lock:\n            existente = existente_fora\n")]),
    "M2": ("redespacho SEM ordenar os locks dos entregadores", NUCLEO, [(
        "primeiro, segundo = sorted((origem, destino))", "primeiro, segundo = origem, destino")]),
    "M3": ("capacidade checada FORA do lock do entregador (pausa de 0,5 ms)", NUCLEO, [(
        "            with self._lock_entregador[e.entregador_id]:        # L3 — um de cada vez\n"
        "                if len(self._agenda[e.entregador_id]) < e.capacidade:\n"
        "                    self._agenda[e.entregador_id].add(pedido.pedido_id)\n"
        "                    pedido.entregador_responsavel_id = e.entregador_id\n"
        "                    return e.entregador_id\n",
        "            if len(self._agenda[e.entregador_id]) < e.capacidade:\n"
        "                time.sleep(0.0005)\n"
        "                with self._lock_entregador[e.entregador_id]:\n"
        "                    self._agenda[e.entregador_id].add(pedido.pedido_id)\n"
        "                    pedido.entregador_responsavel_id = e.entregador_id\n"
        "                    return e.entregador_id\n")]),
    "M3b": ("lock do entregador esquecido em _tentar_atribuir (sem pausa)", NUCLEO, [(
        "            with self._lock_entregador[e.entregador_id]:        # L3 — um de cada vez\n",
        "            with " + NULO + ":\n")]),
    "M4": ("trânsito lido SEM o lock de leitura na ingestão", NUCLEO, [(
        "        with self._transito_rw.leitura():                      # L1: trânsito não muda até o commit\n",
        "        with " + NULO + ":\n")]),
    "M5": ("confirmar_entrega SEM o lock do restaurante", NUCLEO, [(
        "        with rlock:                                              # L2\n"
        "            if pedido.entregue_em is not None:\n"
        "                if pedido.codigo_confirmacao == codigo:",
        "        with " + NULO + ":\n"
        "            if pedido.entregue_em is not None:\n"
        "                if pedido.codigo_confirmacao == codigo:")]),
    "M6": ("RWLock sem preferência para o escritor", RWLOCK, [(
        "            while self._escritor_ativo or self._escritores_esperando > 0:",
        "            while self._escritor_ativo:")]),
    "M7": ("fila de espera ignora a urgência (pega qualquer pedido)", NUCLEO, [(
        "        pid = min(self._aguardando, key=lambda i: (self._pedidos[i].hora_limite_entrega, i))",
        "        pid = next(iter(self._aguardando))")]),
    "M8": ("pílulas do despacho enviadas antes de a ingestão terminar", NUCLEO, [(
        "        for t in [t for t in self._threads if t.name.startswith(\"ingestao-\")]:\n"
        "            t.join(max(0.0, limite - time.monotonic()))\n", "")]),
    "M9": ("confirmar_entrega não libera a vaga do entregador", NUCLEO, [(
        "                self._agenda[entregador].discard(pedido.pedido_id)\n", "                pass\n")]),
    "M10": ("capacidade do redespacho não é conferida", NUCLEO, [(
        "                    if len(self._agenda[destino]) >= dest_ent.capacidade:\n"
        "                        raise Conflito(\"entregador destino está no limite de capacidade\",\n"
        "                                       {\"capacidade\": dest_ent.capacidade})\n"
        "                    self._agenda[origem].discard(pedido.pedido_id)",
        "                    self._agenda[origem].discard(pedido.pedido_id)")]),
    "M11": ("backpressure: fila cheia bloqueia em vez de devolver 503", NUCLEO, [(
        "self._fila.put_nowait(notif.notificacao_id)", "self._fila.put(notif.notificacao_id)")]),
}


def rodar_suite(pasta, rodadas, timeout):
    """Devolve os nomes dos testes que falharam em alguma rodada (ou o motivo de a suíte ter travado)."""
    falhas = set()
    for _ in range(rodadas):
        try:
            p = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-t", "."],
                               cwd=pasta, capture_output=True, text=True, timeout=timeout,
                               env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        except subprocess.TimeoutExpired:
            falhas.add(f"(suíte travou: timeout de {timeout} s)")
            break                       # travou: já foi detectada, não precisa repetir
        saida = p.stdout + p.stderr
        falhas.update(m.group(1) for m in re.finditer(r"^(?:FAIL|ERROR): (\S+) \(", saida, re.M))
        if p.returncode != 0 and not falhas:
            falhas.add("(a suíte quebrou: " + (saida.strip().splitlines() or ["?"])[-1][:80] + ")")
    return sorted(falhas)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("mutacoes", nargs="*", help="ids a rodar (padrão: todas)")
    ap.add_argument("--rodadas", type=int, default=3, help="vezes que a suíte roda por mutação")
    ap.add_argument("--timeout", type=int, default=60, help="segundos até considerar a suíte travada")
    a = ap.parse_args()
    ids = a.mutacoes or list(MUTACOES)
    desconhecidas = [i for i in ids if i not in MUTACOES]
    if desconhecidas:
        sys.exit(f"mutações desconhecidas: {desconhecidas}; use {list(MUTACOES)}")

    nao_detectadas = []
    for mid in ids:
        descricao, arquivo, trocas = MUTACOES[mid]
        pasta = tempfile.mkdtemp(prefix="rota-mutacao-")
        try:
            copia = os.path.join(pasta, "rota-copia")
            shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(".git", "__pycache__", "docs", ".github"))
            caminho = os.path.join(copia, arquivo)
            codigo = open(caminho, encoding="utf-8").read()
            for antigo, novo in trocas:
                if codigo.count(antigo) != 1:
                    sys.exit(f"[{mid}] o trecho a mutar não foi encontrado em {arquivo}: "
                             "o código mudou e a mutação precisa ser atualizada")
                codigo = codigo.replace(antigo, novo)
            open(caminho, "w", encoding="utf-8", newline="\n").write(codigo)
            falhas = rodar_suite(copia, a.rodadas, a.timeout)
        finally:
            shutil.rmtree(pasta, ignore_errors=True)
        if falhas:
            print(f"[{mid}] {descricao}\n      DETECTADA por: {', '.join(falhas)}", flush=True)
        else:
            print(f"[{mid}] {descricao}\n      NÃO DETECTADA em {a.rodadas} rodadas: teste fraco", flush=True)
            nao_detectadas.append(mid)

    print("\nRESULTADO:", "todas as mutações foram detectadas" if not nao_detectadas
          else f"NÃO detectadas: {nao_detectadas}")
    sys.exit(1 if nao_detectadas else 0)


if __name__ == "__main__":
    main()
