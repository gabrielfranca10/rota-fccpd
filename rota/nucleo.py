"""Núcleo concorrente do rota (single-node).

HIERARQUIA DE LOCKS — toda thread adquire locks SEMPRE nesta ordem (nunca ao contrário).
Isso elimina a "espera circular", uma das 4 condições de Coffman para deadlock.

  L1  _transito_rw .......... RWLock: leitura para calcular a hora limite / escrita para
                               declarar uma janela de pico ou bloqueio
  L2  lock do restaurante .... um Lock por restaurante (protege seus pedidos)
                               (só a auditoria segura vários L2 — e em ordem crescente de id)
  L3  lock do entregador ..... um Lock por agenda/capacidade; quando precisa de dois, pega
                               em ordem de id (redespacho, igual à redistribuição de prazo)
  L4  _indice_lock / _notif_lock  índices globais (seções críticas curtíssimas)
  L5  Alertas / Metricas ..... "folhas": nunca adquirem outro lock enquanto seguram o seu

Regras complementares:
  * nenhuma I/O lenta (rede, disco, sleep) acontece segurando lock;
  * nada mutável sai de uma seção crítica: a API recebe apenas cópias (dicts) montadas sob lock;
  * threading.Lock (não reentrante) de propósito: reentrância acidental vira erro visível;
  * despacho pra um entregador é sempre feito com o L2 do pedido já em mãos, e cada tentativa
    segura NO MÁXIMO um L3 por vez (verifica capacidade, libera se cheio, tenta o próximo) —
    por isso nunca precisa de ordenação especial nesse caminho.
"""
from __future__ import annotations

import hashlib
import logging
import queue
import re
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timedelta

from .dominio import (ATRASADO, EM_RISCO, ENTREGUE, ERRO, NAO_VINCULADA, NO_PRAZO, PENDENTE,
                      PLATAFORMAS, PRIORIDADES, PROCESSADA, SEM_PEDIDO, Conflito,
                      ErroValidacao, Entregador, NaoEncontrado, Notificacao, Pedido, Restaurante,
                      Sobrecarga, id_valido, numero_pedido_valido)
from .relogio import BRT, Relogio
from .rwlock import RWLock
from .transito import Transito, Janela, TIPOS_JANELA, calcular_hora_limite

log = logging.getLogger("rota.nucleo")

_PILULA = None  # "pílula de veneno": sinaliza fim para os workers
_SINAL_DESPACHO = "despachar"  # "há vaga? atribua ao pedido mais urgente": o conteúdo não importa
_RE_PREPARO = re.compile(r"preparo\w*\s*(?:de|em|:)?\s*(\d{1,3})\s*min", re.I)


# =============================================================================== utilitários
class Metricas:
    """Contadores thread-safe. `x += 1` NÃO é atômico em Python (ler, somar, gravar)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._c: dict[str, int] = {}

    def inc(self, nome: str, n: int = 1) -> None:
        with self._lock:
            self._c[nome] = self._c.get(nome, 0) + n

    def snapshot(self) -> dict:
        with self._lock:
            return dict(sorted(self._c.items()))


class Alertas:
    """Buffer circular de alertas com cursor (seq). Clientes fazem polling com ?apos=<seq>."""

    def __init__(self, capacidade: int = 5000, relogio: Relogio | None = None) -> None:
        self._lock = threading.Lock()
        self._buf: deque = deque(maxlen=capacidade)
        self._seq = 0
        self._relogio = relogio or Relogio()

    def publicar(self, tipo: str, **dados) -> None:
        # o carimbo vem do relógio do sistema (o simulado, nas demos) e é lido ANTES do lock:
        # Alertas e Relogio são folhas e nenhuma folha segura o seu lock ao pedir outro
        em = self._relogio.agora().isoformat(timespec="seconds")
        with self._lock:
            self._seq += 1
            self._buf.append({"seq": self._seq, "tipo": tipo, "em": em, **dados})

    def listar(self, apos: int = 0, limite: int = 100) -> dict:
        with self._lock:
            itens = [a for a in self._buf if a["seq"] > apos][:limite]
            mais_antigo = self._buf[0]["seq"] if self._buf else self._seq + 1
            return {"alertas": itens, "ultimo_seq": self._seq,
                    "perdidos": apos + 1 < mais_antigo and apos < self._seq}


def _iso(d) -> str | None:
    return d.isoformat(timespec="seconds") if d is not None else None


def _parse_datetime(valor, campo: str) -> datetime:
    if not isinstance(valor, str):
        raise ErroValidacao(f"'{campo}' deve ser uma data/hora ISO 8601", {"campo": campo})
    # o Python 3.10 não entende o sufixo 'Z' (UTC), muito comum em webhooks; do 3.11 em diante entende
    texto = valor[:-1] + "+00:00" if valor.endswith(("Z", "z")) else valor
    try:
        dt = datetime.fromisoformat(texto)
    except ValueError:
        raise ErroValidacao(f"'{campo}' deve ser uma data/hora ISO 8601", {"campo": campo}) from None
    # sem fuso = horário de Brasília; com fuso, converte: o mesmo instante vira a mesma impressão digital
    return dt.replace(tzinfo=BRT) if dt.tzinfo is None else dt.astimezone(BRT)


def _texto(dados: dict, campo: str, obrigatorio=True, maximo=200, padrao=None) -> str | None:
    v = dados.get(campo, padrao)
    if v is None:
        if obrigatorio:
            raise ErroValidacao(f"campo obrigatório: '{campo}'", {"campo": campo})
        return None
    if not isinstance(v, str) or not v.strip() or len(v) > maximo:
        raise ErroValidacao(f"'{campo}' deve ser texto não vazio com até {maximo} caracteres",
                            {"campo": campo})
    return v.strip()


def _numero(dados: dict, campo: str, minimo: float, maximo: float, obrigatorio=True, padrao=None):
    v = dados.get(campo, padrao)
    if v is None:
        if obrigatorio:
            raise ErroValidacao(f"campo obrigatório: '{campo}'", {"campo": campo})
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        raise ErroValidacao(f"'{campo}' deve ser numérico", {"campo": campo})
    if not minimo <= v <= maximo:
        raise ErroValidacao(f"'{campo}' deve estar entre {minimo} e {maximo}", {"campo": campo})
    return v


def impressao_digital(plataforma: str, numero_pedido: str, hora_notificacao: datetime, descricao: str) -> str:
    """Identidade pelo CONTEÚDO: o mesmo evento reenviado pelo agregador (retry de webhook)
    tem timestamps de recebimento diferentes, mas a mesma impressão digital."""
    normal = " ".join(descricao.lower().split())
    chave = f"{plataforma}|{numero_pedido}|{hora_notificacao.isoformat()}|{normal}"
    return hashlib.sha256(chave.encode()).hexdigest()


# =============================================================================== núcleo
class Nucleo:
    def __init__(self, relogio: Relogio | None = None, workers: int = 4, tamanho_fila: int = 1000,
                 janela_risco_min: int = 10, intervalo_monitor: float = 1.0) -> None:
        self.relogio = relogio or Relogio()
        self.janela_risco_min = janela_risco_min
        self.metricas = Metricas()
        self.alertas = Alertas(relogio=self.relogio)

        self._transito_rw = RWLock()                        # L1
        self._transito = Transito()

        self._indice_lock = threading.Lock()                # L4
        self._entregadores: dict[str, Entregador] = {}
        self._lock_entregador: dict[str, threading.Lock] = {}  # L3
        self._agenda: dict[str, set] = {}                   # entregador_id -> {pedido_id} em aberto
        self._aguardando: set[str] = set()                  # pedido_id sem entregador disponível
        self._restaurantes: dict[str, Restaurante] = {}
        self._lock_restaurante: dict[str, threading.Lock] = {}  # L2
        self._pedidos: dict[str, Pedido] = {}

        self._notif_lock = threading.Lock()                 # L4
        self._notificacoes: dict[str, Notificacao] = {}
        self._por_digital: dict[str, str] = {}
        self._aceitando = False

        self._n_workers = workers
        self._fila: queue.Queue = queue.Queue(maxsize=tamanho_fila)     # buffer limitado
        self._fila_recalculo: queue.Queue = queue.Queue()
        self._fila_despacho: queue.Queue = queue.Queue()
        self._intervalo_monitor = intervalo_monitor
        self._parar = threading.Event()
        self._threads: list[threading.Thread] = []

    # ------------------------------------------------------------------ ciclo de vida
    def iniciar(self) -> None:
        with self._notif_lock:
            self._aceitando = True
        for i in range(self._n_workers):
            self._threads.append(threading.Thread(target=self._worker_ingestao,
                                                  name=f"ingestao-{i}", daemon=True))
        self._threads.append(threading.Thread(target=self._worker_recalculo, name="recalculo", daemon=True))
        self._threads.append(threading.Thread(target=self._worker_despacho, name="despacho", daemon=True))
        self._threads.append(threading.Thread(target=self._loop_monitor, name="monitor", daemon=True))
        for t in self._threads:
            t.start()
        log.info("núcleo iniciado: %d workers de ingestão", self._n_workers)

    def parar(self, timeout: float = 10.0) -> None:
        """Desligamento gracioso: para de aceitar, drena as filas e só então encerra os workers."""
        with self._notif_lock:         # mesmo lock do receber(): nenhum job entra depois da 1ª pílula
            if not self._aceitando and not self._threads:
                return
            self._aceitando = False
        limite = time.monotonic() + timeout
        self._parar.set()              # o monitor não precisa mais rodar
        for _ in range(self._n_workers):
            self._fila.put(_PILULA)    # FIFO: as pílulas ficam atrás de todo o trabalho já aceito
        # 1º a ingestão: enquanto ela roda, ainda gera trabalho para o despacho. Só depois de ela
        # terminar o despacho e o recálculo recebem a pílula, e assim drenam tudo o que chegou.
        for t in [t for t in self._threads if t.name.startswith("ingestao-")]:
            t.join(max(0.0, limite - time.monotonic()))
        self._fila_recalculo.put(_PILULA)
        self._fila_despacho.put(_PILULA)
        for t in self._threads:
            t.join(max(0.0, limite - time.monotonic()))
        self._threads.clear()
        log.info("núcleo parado")

    def ocioso(self) -> bool:
        """True quando não há notificação, recálculo nem despacho pendente."""
        for q in (self._fila, self._fila_recalculo, self._fila_despacho):
            with q.all_tasks_done:
                if q.unfinished_tasks:
                    return False
        return True

    def aguardar_ocioso(self, timeout: float = 30.0) -> bool:
        limite = time.monotonic() + timeout
        while time.monotonic() < limite:
            if self.ocioso():
                return True
            time.sleep(0.01)
        return self.ocioso()

    # ------------------------------------------------------------------ cadastro
    def cadastrar_entregador(self, dados: dict) -> dict:
        eid = _texto(dados, "entregador_id", maximo=64)
        if not id_valido(eid):
            raise ErroValidacao("entregador_id aceita letras, números, '.', '_' e '-'")
        capacidade = _numero(dados, "capacidade", 1, 10)
        if capacidade != int(capacidade):
            raise ErroValidacao("capacidade deve ser um inteiro")
        ent = Entregador(eid, _texto(dados, "nome"), _texto(dados, "veiculo", maximo=20), int(capacidade))
        with self._indice_lock:
            if eid in self._entregadores:
                raise Conflito("entregador já cadastrado", {"entregador_id": eid})
            self._entregadores[eid] = ent
            self._lock_entregador[eid] = threading.Lock()
            self._agenda[eid] = set()
        return self._view_entregador(ent, 0)

    def cadastrar_restaurante(self, dados: dict) -> dict:
        rid = _texto(dados, "restaurante_id", maximo=64)
        if not id_valido(rid):
            raise ErroValidacao("restaurante_id aceita letras, números, '.', '_' e '-'")
        rest = Restaurante(rid, _texto(dados, "nome"), _texto(dados, "endereco"))
        with self._indice_lock:
            if rid in self._restaurantes:
                raise Conflito("restaurante já cadastrado", {"restaurante_id": rid})
            self._lock_restaurante[rid] = threading.Lock()
            self._restaurantes[rid] = rest
        return {"restaurante_id": rid, "nome": rest.nome, "endereco": rest.endereco, "pedidos": []}

    # ------------------------------------------------------------------ ingestão (produtor)
    def receber_notificacao(self, dados: dict) -> tuple[dict, bool]:
        """Valida, deduplica e enfileira. Retorna (notificação, nova?).

        Verificar-e-inserir no índice + enfileirar acontecem DENTRO da mesma seção crítica:
        duas requisições com a mesma notificação nunca geram dois jobs.
        """
        restaurante_id = _texto(dados, "restaurante_id", maximo=64)
        if not id_valido(restaurante_id):
            raise ErroValidacao("restaurante_id inválido", {"restaurante_id": restaurante_id})
        numero_pedido = _texto(dados, "numero_pedido", maximo=32)
        if not numero_pedido_valido(numero_pedido):
            raise ErroValidacao("numero_pedido deve ser no formato PLATAFORMA-CODIGO (ex.: IFOOD-000123)",
                                {"numero_pedido": numero_pedido})
        plataforma = _texto(dados, "plataforma", maximo=20)
        if plataforma not in PLATAFORMAS:
            raise ErroValidacao(f"plataforma deve ser uma de {list(PLATAFORMAS)}")
        hora_notificacao = _parse_datetime(dados.get("hora_notificacao"), "hora_notificacao")
        descricao = _texto(dados, "descricao", maximo=2000)
        distancia_km = _numero(dados, "distancia_km", 0.1, 50.0)
        prioridade = dados.get("prioridade", "PADRAO")
        if prioridade not in PRIORIDADES:
            raise ErroValidacao(f"prioridade deve ser uma de {list(PRIORIDADES)}")

        tempo_preparo_min = dados.get("tempo_preparo_min")
        if tempo_preparo_min is None:
            m = _RE_PREPARO.search(descricao)   # extração simples: "tempo de preparo: 18 minutos"
            tempo_preparo_min = int(m.group(1)) if m else None
        if tempo_preparo_min is not None and (isinstance(tempo_preparo_min, bool)
                                              or not isinstance(tempo_preparo_min, int)
                                              or not 1 <= tempo_preparo_min <= 180):
            raise ErroValidacao("tempo_preparo_min deve ser inteiro entre 1 e 180")

        digital = impressao_digital(plataforma, numero_pedido, hora_notificacao, descricao)
        with self._notif_lock:
            existente = self._por_digital.get(digital)
            if existente is not None:
                notif = self._notificacoes[existente]
                notif.duplicatas_recebidas += 1
                view = self._view_notificacao(notif)
                nova = False
            else:
                if not self._aceitando:
                    raise Sobrecarga("sistema em desligamento; tente novamente")
                notif = Notificacao(f"notif_{uuid.uuid4().hex}", digital, restaurante_id, numero_pedido,
                                    plataforma, hora_notificacao, descricao, tempo_preparo_min,
                                    distancia_km, prioridade,
                                    recebida_em=self.relogio.agora().isoformat(timespec="seconds"))
                try:
                    self._fila.put_nowait(notif.notificacao_id)   # não bloqueia segurando lock
                except queue.Full:
                    raise Sobrecarga("fila de ingestão cheia; tente novamente em instantes") from None
                self._notificacoes[notif.notificacao_id] = notif
                self._por_digital[digital] = notif.notificacao_id
                view = self._view_notificacao(notif)
                nova = True
        self.metricas.inc("notificacoes_aceitas" if nova else "notificacoes_duplicadas")
        return view, nova

    # ------------------------------------------------------------------ ingestão (consumidores)
    def _worker_ingestao(self) -> None:
        while True:
            notif_id = self._fila.get()
            try:
                if notif_id is _PILULA:
                    return
                self._processar(notif_id)
            except Exception as exc:  # um erro não pode matar o worker
                log.exception("falha processando %s", notif_id)
                with self._notif_lock:
                    notif = self._notificacoes[notif_id]
                    notif.status, notif.erro = ERRO, str(exc)
                self.metricas.inc("notificacoes_com_erro")
            finally:
                self._fila.task_done()

    def _processar(self, notif_id: str) -> None:
        with self._notif_lock:
            notif = self._notificacoes[notif_id]   # campos usados abaixo são imutáveis após a criação
        if notif.tempo_preparo_min is None:
            self._marcar_notificacao(notif, SEM_PEDIDO)
            self.metricas.inc("notificacoes_sem_pedido")
            return
        with self._indice_lock:
            rest = self._restaurantes.get(notif.restaurante_id)
            rlock = self._lock_restaurante.get(notif.restaurante_id)
        if rest is None:
            self._marcar_notificacao(notif, NAO_VINCULADA)
            self.alertas.publicar("NOTIFICACAO_NAO_VINCULADA", notificacao_id=notif_id,
                                  restaurante_id=notif.restaurante_id)
            self.metricas.inc("notificacoes_nao_vinculadas")
            return

        with self._transito_rw.leitura():                      # L1: trânsito não muda até o commit
            transito = self._transito
            r = calcular_hora_limite(transito, notif.hora_notificacao, notif.tempo_preparo_min,
                                     notif.distancia_km, notif.prioridade)
            with rlock:                                         # L2
                pedido = Pedido(f"ped_{uuid.uuid4().hex}", rest.restaurante_id, notif_id, notif.numero_pedido,
                                notif.plataforma, notif.prioridade, notif.tempo_preparo_min,
                                notif.distancia_km, notif.hora_notificacao, r.hora_pronto, r.hora_saida,
                                r.hora_limite, r.fundamento, r.janelas_consideradas, r.transito_versao)
                pedido.nivel_alerta = self._status(pedido, self.relogio.agora())
                entregador_id = self._tentar_atribuir(pedido)    # L3 nested, no máximo um por vez
                with self._indice_lock:                         # L4
                    self._pedidos[pedido.pedido_id] = pedido
                    if entregador_id is None:
                        self._aguardando.add(pedido.pedido_id)
                rest.pedido_ids.append(pedido.pedido_id)
                self._marcar_notificacao(notif, PROCESSADA, pedido.pedido_id)
                nivel = pedido.nivel_alerta
        self.metricas.inc("pedidos_criados")
        if entregador_id is None:
            self._fila_despacho.put_nowait(_SINAL_DESPACHO)
            self.alertas.publicar("PEDIDO_AGUARDANDO_ENTREGADOR", pedido_id=pedido.pedido_id,
                                  restaurante_id=rest.restaurante_id)
        if nivel in (EM_RISCO, ATRASADO):
            self.alertas.publicar(f"PEDIDO_{nivel}", pedido_id=pedido.pedido_id,
                                  numero_pedido=pedido.numero_pedido,
                                  hora_limite_entrega=_iso(pedido.hora_limite_entrega))

    def _marcar_notificacao(self, notif: Notificacao, status: str, pedido_id: str | None = None) -> None:
        with self._notif_lock:
            notif.status, notif.pedido_id = status, pedido_id

    # ------------------------------------------------------------------ despacho (alocação de entregador)
    def _tentar_atribuir(self, pedido: Pedido) -> str | None:
        """Chamada com o L2 do pedido já em mãos. Ranking otimista pelo tamanho da agenda
        (pode estar levemente desatualizado); a decisão real é sempre verificada sob o L3
        do candidato — por isso nunca atribui além da capacidade, mesmo sob concorrência."""
        with self._indice_lock:
            candidatos = list(self._entregadores.values())
        candidatos.sort(key=lambda e: len(self._agenda.get(e.entregador_id, ())))
        for e in candidatos:
            with self._lock_entregador[e.entregador_id]:        # L3 — um de cada vez
                if len(self._agenda[e.entregador_id]) < e.capacidade:
                    self._agenda[e.entregador_id].add(pedido.pedido_id)
                    pedido.entregador_responsavel_id = e.entregador_id
                    return e.entregador_id
        return None

    def _worker_despacho(self) -> None:
        while True:
            item = self._fila_despacho.get()
            try:
                if item is _PILULA:
                    return
                self._tentar_despachar()
            except Exception:
                log.exception("falha no despacho")
            finally:
                self._fila_despacho.task_done()

    def _ha_vaga(self) -> bool:
        """Olhada otimista (sem L3): só decide se vale a pena procurar um pedido em espera.
        A decisão real continua sendo tomada sob o lock do entregador, em _tentar_atribuir."""
        with self._indice_lock:
            entregadores = list(self._entregadores.values())
        return any(len(self._agenda[e.entregador_id]) < e.capacidade for e in entregadores)

    def _mais_urgente_em_espera(self) -> Pedido | None:
        """Chamada com o L4 em mãos. Menor hora limite primeiro (desempate pelo id): a vaga que
        libera vai para quem tem menos tempo, e não para quem foi enfileirado antes. A hora limite
        é lida sem o L2 do restaurante: um recálculo concorrente pode deixar o ranking levemente
        defasado, mas quem decide de fato é _tentar_atribuir."""
        if not self._aguardando:
            return None
        pid = min(self._aguardando, key=lambda i: (self._pedidos[i].hora_limite_entrega, i))
        return self._pedidos[pid]

    def _tentar_despachar(self) -> None:
        """A fila de despacho só carrega um sinal ('pode ter vaga'). Enquanto houver vaga, atribui
        ao pedido em espera mais urgente; um único sinal preenche todas as vagas abertas."""
        while self._ha_vaga():
            with self._indice_lock:
                pedido = self._mais_urgente_em_espera()
                rlock = self._lock_restaurante[pedido.restaurante_id] if pedido else None
            if pedido is None:
                return
            with rlock:                                          # L2
                if pedido.entregue_em is not None or pedido.entregador_responsavel_id is not None:
                    with self._indice_lock:                      # já resolvido por outro caminho
                        self._aguardando.discard(pedido.pedido_id)
                    continue
                entregador_id = self._tentar_atribuir(pedido)
                if entregador_id is None:                        # a vaga sumiu entre a olhada e o lock
                    return
                with self._indice_lock:
                    self._aguardando.discard(pedido.pedido_id)
                self.metricas.inc("pedidos_despachados_apos_espera")
                self.alertas.publicar("PEDIDO_DESPACHADO", pedido_id=pedido.pedido_id,
                                      entregador_id=entregador_id)

    # ------------------------------------------------------------------ operações sobre pedidos
    def _localizar(self, pedido_id: str):
        with self._indice_lock:
            pedido = self._pedidos.get(pedido_id)
            if pedido is None:
                raise NaoEncontrado("pedido não encontrado", {"pedido_id": pedido_id})
            return pedido, self._lock_restaurante[pedido.restaurante_id]

    def confirmar_entrega(self, pedido_id: str, dados: dict) -> dict:
        """Entregador informa o código de confirmação. O instante em que o lock é obtido é o
        'ponto de linearização': é ali que se decide se a entrega já estava atrasada."""
        entregador = _texto(dados, "entregador_id", maximo=64)
        codigo = _texto(dados, "codigo_confirmacao", maximo=64)
        pedido, rlock = self._localizar(pedido_id)
        with rlock:                                              # L2
            if pedido.entregue_em is not None:
                if pedido.codigo_confirmacao == codigo:          # repetição do mesmo pedido: idempotente
                    return self._view_pedido(pedido, self.relogio.agora())
                raise Conflito("pedido já foi confirmado com outro código",
                               {"codigo_confirmacao": pedido.codigo_confirmacao})
            if entregador != pedido.entregador_responsavel_id:
                raise Conflito("somente o entregador responsável pode confirmar a entrega",
                               {"entregador_responsavel_id": pedido.entregador_responsavel_id})
            agora = self.relogio.agora()
            with self._lock_entregador[entregador]:               # L3
                self._agenda[entregador].discard(pedido.pedido_id)
            pedido.entregue_em = agora.isoformat(timespec="seconds")
            pedido.entregue_atrasado = agora > pedido.hora_limite_entrega
            pedido.codigo_confirmacao = codigo
            view = self._view_pedido(pedido, agora)
        self.metricas.inc("pedidos_entregues_atrasados" if pedido.entregue_atrasado else "pedidos_entregues")
        self._acordar_fila_espera()
        return view

    def _acordar_fila_espera(self) -> None:
        """Uma vaga liberou (ou o monitor conferiu): se há pedido esperando, acorda o despacho."""
        with self._indice_lock:
            ha_espera = bool(self._aguardando)
        if ha_espera:
            self._fila_despacho.put_nowait(_SINAL_DESPACHO)

    def redespachar_pedido(self, pedido_id: str, dados: dict) -> dict:
        """Move o pedido da agenda de um entregador para a de outro (ex.: pane na moto).

        Precisa de DOIS locks de agenda quando origem e destino já existem. Se A->B e B->A
        acontecerem juntos e cada thread pegar primeiro o lock da origem, cada uma segura um
        e espera o outro: DEADLOCK. Solução: adquirir sempre em ordem crescente de entregador_id.
        """
        destino = _texto(dados, "entregador_destino", maximo=64)
        with self._indice_lock:
            dest_ent = self._entregadores.get(destino)
            if dest_ent is None:
                raise ErroValidacao("entregador_destino não cadastrado", {"entregador_id": destino})
        pedido, rlock = self._localizar(pedido_id)
        with rlock:                                              # L2
            if pedido.entregue_em is not None:
                raise Conflito("pedido já entregue não pode ser redespachado")
            origem = pedido.entregador_responsavel_id
            if origem == destino:
                return self._view_pedido(pedido, self.relogio.agora())
            if origem is None:
                with self._lock_entregador[destino]:              # L3
                    if len(self._agenda[destino]) >= dest_ent.capacidade:
                        raise Conflito("entregador destino está no limite de capacidade",
                                       {"capacidade": dest_ent.capacidade})
                    self._agenda[destino].add(pedido.pedido_id)
                    pedido.entregador_responsavel_id = destino
                with self._indice_lock:
                    self._aguardando.discard(pedido_id)
            else:
                primeiro, segundo = sorted((origem, destino))
                with self._lock_entregador[primeiro], self._lock_entregador[segundo]:   # L3 ordenado
                    if len(self._agenda[destino]) >= dest_ent.capacidade:
                        raise Conflito("entregador destino está no limite de capacidade",
                                       {"capacidade": dest_ent.capacidade})
                    self._agenda[origem].discard(pedido.pedido_id)
                    self._agenda[destino].add(pedido.pedido_id)
                    pedido.entregador_responsavel_id = destino
            view = self._view_pedido(pedido, self.relogio.agora())
        self.metricas.inc("pedidos_redespachados")
        self.alertas.publicar("PEDIDO_REDESPACHADO", pedido_id=pedido_id, de=origem, para=destino)
        return view

    # ------------------------------------------------------------------ trânsito (escritor)
    def declarar_janela(self, dados: dict) -> dict:
        inicio = _parse_datetime(dados.get("inicio"), "inicio")
        fim = _parse_datetime(dados.get("fim"), "fim")
        if fim <= inicio or (fim - inicio) > timedelta(hours=6):
            raise ErroValidacao("intervalo inválido (fim > inicio, no máximo 6 horas)")
        tipo = dados.get("tipo")
        if tipo not in TIPOS_JANELA:
            raise ErroValidacao(f"tipo deve ser um de {list(TIPOS_JANELA)}")
        j = Janela(inicio, fim, tipo, _texto(dados, "motivo"))
        with self._transito_rw.escrita():                        # L1 exclusivo: espera cálculos em curso
            self._transito = self._transito.com_janela(j)
            versao = self._transito.versao
            self._fila_recalculo.put(versao)                     # fila sem limite: put nunca bloqueia
        self.metricas.inc("transito_atualizacoes")
        self.alertas.publicar("TRANSITO_ATUALIZADO", versao=versao, tipo_janela=tipo, motivo=j.motivo)
        return {"versao": versao, "recalculo": "agendado"}

    def _worker_recalculo(self) -> None:
        while True:
            item = self._fila_recalculo.get()
            try:
                if item is _PILULA:
                    return
                self._recalcular_todos()
            except Exception:
                log.exception("falha no recálculo")
            finally:
                self._fila_recalculo.task_done()

    def _recalcular_todos(self) -> int:
        """Uma passada cobre qualquer quantidade de atualizações anteriores (sempre usa o
        trânsito mais recente), então várias versões enfileiradas não geram trabalho extra."""
        with self._indice_lock:
            rids = list(self._restaurantes)
        alterados = 0
        for rid in rids:
            with self._transito_rw.leitura():                    # L1
                transito = self._transito
                with self._lock_restaurante[rid]:                 # L2
                    rest = self._restaurantes[rid]
                    for pedido_id in rest.pedido_ids:
                        p = self._pedidos_get(pedido_id)
                        if p.entregue_em is not None or p.transito_versao == transito.versao:
                            continue
                        r = calcular_hora_limite(transito, p.hora_notificacao, p.tempo_preparo_min,
                                                 p.distancia_km, p.prioridade)
                        mudou = r.hora_limite != p.hora_limite_entrega
                        antiga = p.hora_limite_entrega
                        (p.hora_pronto, p.hora_saida, p.hora_limite_entrega, p.fundamento,
                         p.janelas_consideradas, p.transito_versao) = (
                            r.hora_pronto, r.hora_saida, r.hora_limite, r.fundamento,
                            r.janelas_consideradas, r.transito_versao)
                        p.nivel_alerta = self._status(p, self.relogio.agora())
                        if mudou:
                            p.recalculos += 1
                            alterados += 1
                            self.alertas.publicar("PEDIDO_RECALCULADO", pedido_id=p.pedido_id,
                                                  de=_iso(antiga), para=_iso(p.hora_limite_entrega))
        self.metricas.inc("pedidos_recalculados", alterados)
        return alterados

    def _pedidos_get(self, pedido_id: str) -> Pedido:
        with self._indice_lock:
            return self._pedidos[pedido_id]

    # ------------------------------------------------------------------ monitor
    def _status(self, p: Pedido, agora: datetime) -> str:
        """Status DERIVADO do relógio: não existe uma thread que 'vira' o pedido para ATRASADO,
        logo não existe corrida entre essa thread e a confirmação de entrega."""
        if p.entregue_em is not None:
            return ENTREGUE
        if agora > p.hora_limite_entrega:
            return ATRASADO
        restante_min = (p.hora_limite_entrega - agora).total_seconds() / 60
        return EM_RISCO if restante_min <= self.janela_risco_min else NO_PRAZO

    def _loop_monitor(self) -> None:
        while not self._parar.wait(self._intervalo_monitor):     # sleep interrompível
            try:
                self.executar_monitor()
            except Exception:
                log.exception("falha no monitor")

    def executar_monitor(self) -> int:
        """Emite alerta quando um pedido PIORA de nível (NO_PRAZO -> EM_RISCO -> ATRASADO) e
        reagenda, como rede de segurança, qualquer pedido ainda sem entregador."""
        ordem = {NO_PRAZO: 0, EM_RISCO: 1, ATRASADO: 2, ENTREGUE: -1}
        with self._indice_lock:
            rids = list(self._restaurantes)
        emitidos = 0
        agora = self.relogio.agora()
        for rid in rids:
            with self._lock_restaurante[rid]:
                for pedido_id in self._restaurantes[rid].pedido_ids:
                    p = self._pedidos_get(pedido_id)
                    novo = self._status(p, agora)
                    if novo == p.nivel_alerta:
                        continue
                    piorou = ordem[novo] > ordem[p.nivel_alerta]
                    p.nivel_alerta = novo
                    if piorou:
                        emitidos += 1
                        self.alertas.publicar(f"PEDIDO_{novo}", pedido_id=p.pedido_id,
                                              numero_pedido=p.numero_pedido,
                                              hora_limite_entrega=_iso(p.hora_limite_entrega))
        if emitidos:
            self.metricas.inc("alertas_de_pedido", emitidos)
        self._acordar_fila_espera()
        return emitidos

    # ------------------------------------------------------------------ consultas (cópias!)
    def _view_pedido(self, p: Pedido, agora: datetime) -> dict:
        status = self._status(p, agora)
        return {
            "pedido_id": p.pedido_id, "restaurante_id": p.restaurante_id, "notificacao_id": p.notificacao_id,
            "numero_pedido": p.numero_pedido, "plataforma": p.plataforma, "status": status,
            "prioridade": p.prioridade, "tempo_preparo_min": p.tempo_preparo_min,
            "distancia_km": p.distancia_km, "hora_notificacao": _iso(p.hora_notificacao),
            "hora_pronto": _iso(p.hora_pronto), "hora_saida": _iso(p.hora_saida),
            "hora_limite_entrega": _iso(p.hora_limite_entrega),
            "minutos_restantes": (max(0, int((p.hora_limite_entrega - agora).total_seconds() // 60))
                                  if status in (NO_PRAZO, EM_RISCO) else 0),
            "fundamento": p.fundamento,
            "janelas_consideradas": [{"inicio": _iso(i), "fim": _iso(f), "motivo": m}
                                     for i, f, m in p.janelas_consideradas],
            "transito_versao": p.transito_versao, "entregador_responsavel_id": p.entregador_responsavel_id,
            "entregue_em": p.entregue_em, "entregue_atrasado": p.entregue_atrasado,
            "codigo_confirmacao": p.codigo_confirmacao, "recalculos": p.recalculos,
        }

    def _view_notificacao(self, notif: Notificacao) -> dict:
        return {"notificacao_id": notif.notificacao_id, "restaurante_id": notif.restaurante_id,
                "numero_pedido": notif.numero_pedido, "plataforma": notif.plataforma,
                "hora_notificacao": _iso(notif.hora_notificacao), "tempo_preparo_min": notif.tempo_preparo_min,
                "distancia_km": notif.distancia_km, "prioridade": notif.prioridade, "status": notif.status,
                "pedido_id": notif.pedido_id, "erro": notif.erro, "recebida_em": notif.recebida_em,
                "duplicatas_recebidas": notif.duplicatas_recebidas, "impressao_digital": notif.impressao_digital}

    @staticmethod
    def _view_entregador(e: Entregador, abertos: int) -> dict:
        return {"entregador_id": e.entregador_id, "nome": e.nome, "veiculo": e.veiculo,
                "capacidade": e.capacidade, "pedidos_em_aberto": abertos}

    def obter_pedido(self, pedido_id: str) -> dict:
        pedido, rlock = self._localizar(pedido_id)
        with rlock:
            return self._view_pedido(pedido, self.relogio.agora())

    def obter_notificacao(self, notif_id: str) -> dict:
        with self._notif_lock:
            notif = self._notificacoes.get(notif_id)
            if notif is None:
                raise NaoEncontrado("notificação não encontrada", {"notificacao_id": notif_id})
            return self._view_notificacao(notif)

    def listar_entregadores(self) -> list:
        with self._indice_lock:
            ents = list(self._entregadores.values())
        out = []
        for e in ents:
            with self._lock_entregador[e.entregador_id]:
                out.append(self._view_entregador(e, len(self._agenda[e.entregador_id])))
        return out

    def listar_restaurantes(self) -> list:
        with self._indice_lock:
            rests = [(r, self._lock_restaurante[r.restaurante_id]) for r in self._restaurantes.values()]
        out = []
        for r, rlock in rests:
            with rlock:
                out.append({"restaurante_id": r.restaurante_id, "nome": r.nome, "endereco": r.endereco,
                            "total_pedidos": len(r.pedido_ids)})
        return out

    def obter_restaurante(self, rid: str) -> dict:
        with self._indice_lock:
            r = self._restaurantes.get(rid)
            if r is None:
                raise NaoEncontrado("restaurante não encontrado", {"restaurante_id": rid})
            rlock = self._lock_restaurante[rid]
        agora = self.relogio.agora()
        with rlock:
            return {"restaurante_id": r.restaurante_id, "nome": r.nome, "endereco": r.endereco,
                    "pedidos": [self._view_pedido(self._pedidos_get(i), agora) for i in r.pedido_ids]}

    def listar_pedidos(self, status: str | None = None, entregador: str | None = None,
                       limite: int = 100) -> list:
        """Duas fases: (1) sob o lock de cada restaurante, só filtra e guarda (hora_limite, id);
        (2) monta a visão completa apenas dos `limite` primeiros."""
        with self._indice_lock:
            rests = [(r, self._lock_restaurante[r.restaurante_id]) for r in self._restaurantes.values()]
        agora = self.relogio.agora()
        chaves = []
        for r, rlock in rests:
            with rlock:
                for i in r.pedido_ids:
                    pedido = self._pedidos_get(i)
                    if entregador and pedido.entregador_responsavel_id != entregador:
                        continue
                    if status and self._status(pedido, agora) != status:
                        continue
                    chaves.append((pedido.hora_limite_entrega, i, rlock))
        chaves.sort(key=lambda c: (c[0], c[1]))
        out = []
        for _, i, rlock in chaves[:limite]:
            with rlock:
                out.append(self._view_pedido(self._pedidos_get(i), agora))
        return out

    def obter_transito(self) -> dict:
        transito = self._transito       # leitura de referência: atômica; o objeto é imutável
        return {"versao": transito.versao, "janelas": [
            {"inicio": _iso(j.inicio), "fim": _iso(j.fim), "tipo": j.tipo, "motivo": j.motivo}
            for j in transito.janelas]}

    def estatisticas(self) -> dict:
        with self._notif_lock:
            por_status: dict[str, int] = {}
            for notif in self._notificacoes.values():
                por_status[notif.status] = por_status.get(notif.status, 0) + 1
        with self._indice_lock:
            n_pedidos, n_rest, n_aguardando = len(self._pedidos), len(self._restaurantes), len(self._aguardando)
        return {"agora": self.relogio.agora().isoformat(timespec="seconds"),
                "fila_ingestao": self._fila.qsize(), "fila_despacho": self._fila_despacho.qsize(),
                "recalculo_pendente": not self.ocioso(), "transito_versao": self._transito.versao,
                "restaurantes": n_rest, "pedidos": n_pedidos, "pedidos_aguardando_entregador": n_aguardando,
                "notificacoes_por_status": por_status, "contadores": self.metricas.snapshot(),
                "threads_ativas": threading.active_count()}

    # ------------------------------------------------------------------ auditoria
    def auditoria(self) -> dict:
        """Congela o sistema respeitando a hierarquia (L1 escrita -> todos L2 em ordem ->
        todos L3 em ordem -> L4) e confere as invariantes. Se ocioso, compara cada pedido em
        aberto com um recálculo sequencial ('oráculo')."""
        violacoes: list[str] = []
        with self._transito_rw.escrita():
            # sob o lock de escrita nenhuma atualização de trânsito entra; se não há nada
            # pendente agora, todos os pedidos em aberto deveriam estar na versão atual
            ocioso = self.ocioso()
            transito = self._transito
            with self._indice_lock:
                rids = sorted(self._restaurantes)
                eids = sorted(self._entregadores)
            rlocks = [self._lock_restaurante[r] for r in rids]
            elocks = [self._lock_entregador[e] for e in eids]
            for lk in rlocks + elocks:
                lk.acquire()
            try:
                with self._indice_lock, self._notif_lock:
                    pedidos = dict(self._pedidos)
                    notifs = dict(self._notificacoes)
                    aguardando = set(self._aguardando)
                    if len(self._por_digital) != len(notifs):
                        violacoes.append("índice de impressões digitais diverge das notificações")
                    for dig, nid in self._por_digital.items():
                        if notifs[nid].impressao_digital != dig:
                            violacoes.append(f"impressão digital inconsistente em {nid}")
                    processadas = {n.notificacao_id for n in notifs.values() if n.status == PROCESSADA}
                    por_notif: dict[str, int] = {}
                    for pe in pedidos.values():
                        por_notif[pe.notificacao_id] = por_notif.get(pe.notificacao_id, 0) + 1
                    duplicados = [k for k, v in por_notif.items() if v > 1]
                    if duplicados:
                        violacoes.append(f"{len(duplicados)} notificações com mais de um pedido")
                    if set(por_notif) != processadas:
                        violacoes.append("pedidos e notificações PROCESSADAS não batem 1:1")
                    for notif in notifs.values():
                        if notif.status == PROCESSADA and pedidos.get(notif.pedido_id) is None:
                            violacoes.append(f"{notif.notificacao_id} aponta para pedido inexistente")
                    # agendas: todo pedido em aberto com entregador está em EXATAMENTE uma agenda
                    dono: dict[str, list] = {}
                    for e in eids:
                        for pid in self._agenda[e]:
                            dono.setdefault(pid, []).append(e)
                    for eid in eids:
                        if len(self._agenda[eid]) > self._entregadores[eid].capacidade:
                            violacoes.append(f"entregador {eid} excede a capacidade "
                                             f"({len(self._agenda[eid])}/{self._entregadores[eid].capacidade})")
                    for pid, pe in pedidos.items():
                        donos = dono.get(pid, [])
                        if pe.entregue_em is None and pe.entregador_responsavel_id is not None:
                            if donos != [pe.entregador_responsavel_id]:
                                violacoes.append(f"pedido {pid} em agendas {donos}, responsável "
                                                 f"{pe.entregador_responsavel_id}")
                        if pe.entregue_em is None and pe.entregador_responsavel_id is None:
                            if donos:
                                violacoes.append(f"pedido {pid} aguardando entregador mas está em agenda {donos}")
                            if pid not in aguardando:
                                violacoes.append(f"pedido {pid} sem entregador não está na fila de espera")
                        if pe.entregue_em is not None and donos:
                            violacoes.append(f"pedido entregue {pid} ainda em agenda {donos}")
                        if pe.entregue_em is not None:
                            atraso_real = pe.entregue_em > _iso(pe.hora_limite_entrega)
                            if atraso_real != pe.entregue_atrasado:
                                violacoes.append(f"pedido {pid}: entregue_atrasado inconsistente "
                                                 f"com os horários registrados")
                    for pid in dono:
                        if pid not in pedidos:
                            violacoes.append(f"agenda contém pedido inexistente {pid}")
                    for pid in aguardando:
                        pe = pedidos.get(pid)
                        if pe is None:
                            violacoes.append(f"fila de espera contém pedido inexistente {pid}")
                        elif pe.entregador_responsavel_id is not None or pe.entregue_em is not None:
                            violacoes.append(f"pedido {pid} na fila de espera mas já tem destino")
                    ligados = sum(len(self._restaurantes[r].pedido_ids) for r in rids)
                    if ligados != len(pedidos):
                        violacoes.append("pedidos ligados aos restaurantes != total de pedidos")
                    divergencias = 0
                    if ocioso:
                        for pe in pedidos.values():
                            if pe.entregue_em is not None:
                                continue
                            ref = calcular_hora_limite(transito, pe.hora_notificacao, pe.tempo_preparo_min,
                                                       pe.distancia_km, pe.prioridade)
                            if ref.hora_limite != pe.hora_limite_entrega or pe.transito_versao != transito.versao:
                                divergencias += 1
                        if divergencias:
                            violacoes.append(f"{divergencias} pedidos divergem do recálculo sequencial")
                    abertos = sum(1 for p in pedidos.values() if p.entregue_em is None)
            finally:
                for lk in reversed(rlocks + elocks):
                    lk.release()
        return {"ok": not violacoes, "violacoes": violacoes[:50], "total_violacoes": len(violacoes),
                "oraculo_executado": ocioso, "transito_versao": transito.versao,
                "notificacoes": len(notifs), "pedidos": len(pedidos), "pedidos_em_aberto": abertos,
                "pedidos_aguardando_entregador": len(aguardando)}
