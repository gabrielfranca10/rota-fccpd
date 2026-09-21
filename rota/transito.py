"""Estado de trânsito (imutável) e motor de cálculo da hora limite de entrega.

Regras modeladas (simplificação didática — não substitui um roteirizador de verdade):
  * velocidade base de deslocamento: VELOCIDADE_BASE_KMH;
  * pedido pronto = hora da notificação + tempo de preparo;
  * se a cozinha fica pronta durante um BLOQUEIO (via interditada), a saída espera o
    bloqueio acabar — mesma ideia de "publicação empurrada pro próximo dia útil";
  * o trajeto é simulado minuto a minuto: PICO reduz a velocidade efetiva (fator < 1),
    BLOQUEIO zera o avanço (o entregador para até a via liberar);
  * entrega EXPRESSA usa rota priorizada: o trajeto alvo é menor.

O objeto Transito é IMUTÁVEL: declarar uma janela cria um novo objeto com versão+1.
Por isso uma thread que está calculando nunca vê um estado de trânsito "pela metade".
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

VELOCIDADE_BASE_KMH = 18.0
FATOR_PICO = 0.5          # velocidade cai pra metade durante pico
FATOR_EXPRESSA = 0.8      # entrega expressa: rota priorizada, 20% mais rápida
PASSO = timedelta(minutes=1)

MAX_PREPARO_MIN = 180
MAX_DISTANCIA_KM = 50.0

PICO = "PICO"
BLOQUEIO = "BLOQUEIO"
TIPOS_JANELA = (PICO, BLOQUEIO)


@dataclass(frozen=True)
class Janela:
    inicio: datetime
    fim: datetime
    tipo: str
    motivo: str

    def cobre(self, t: datetime) -> bool:
        return self.inicio <= t <= self.fim


@dataclass(frozen=True)
class Transito:
    versao: int = 1
    janelas: tuple = field(default_factory=tuple)

    def com_janela(self, j: Janela) -> "Transito":
        """Copy-on-write: devolve um NOVO estado; o atual continua intacto."""
        return Transito(versao=self.versao + 1, janelas=self.janelas + (j,))

    def motivo_bloqueio(self, t: datetime) -> str | None:
        for j in self.janelas:
            if j.tipo == BLOQUEIO and j.cobre(t):
                return f"via bloqueada: {j.motivo}"
        return None

    def fator_velocidade(self, t: datetime) -> float:
        """0.0 = parado (bloqueio); 1.0 = velocidade normal; entre os dois = pico."""
        if self.motivo_bloqueio(t) is not None:
            return 0.0
        fator = 1.0
        for j in self.janelas:
            if j.tipo == PICO and j.cobre(t):
                fator = min(fator, FATOR_PICO)
        return fator


@dataclass(frozen=True)
class ResultadoSLA:
    hora_pronto: datetime
    hora_saida: datetime
    hora_limite: datetime
    minutos_transito_alvo: int
    janelas_consideradas: tuple   # ((inicio, fim, motivo), ...)
    fundamento: str
    transito_versao: int


def calcular_hora_limite(transito: Transito, hora_notificacao: datetime, tempo_preparo_min: int,
                         distancia_km: float, prioridade: str = "PADRAO") -> ResultadoSLA:
    """Função PURA: mesma entrada -> mesma saída. Não toca em estado compartilhado."""
    if not 1 <= tempo_preparo_min <= MAX_PREPARO_MIN:
        raise ValueError(f"tempo_preparo_min deve estar entre 1 e {MAX_PREPARO_MIN}")
    if not 0 < distancia_km <= MAX_DISTANCIA_KM:
        raise ValueError(f"distancia_km deve estar entre 0 (exclusivo) e {MAX_DISTANCIA_KM}")

    hora_pronto = hora_notificacao + timedelta(minutes=tempo_preparo_min)

    # se a cozinha fica pronta durante um bloqueio, a saída espera a via liberar
    consideradas = []
    t = hora_pronto
    motivo = transito.motivo_bloqueio(t)
    if motivo is not None:
        inicio_bloqueio = t
        while transito.motivo_bloqueio(t) is not None:
            t += PASSO
        consideradas.append((inicio_bloqueio, t, motivo))
    hora_saida = t

    alvo_min = distancia_km / VELOCIDADE_BASE_KMH * 60.0
    if prioridade == "EXPRESSA":
        alvo_min *= FATOR_EXPRESSA

    progresso, cursor = 0.0, hora_saida
    inicio_pico = None
    while progresso < alvo_min:
        fator = transito.fator_velocidade(cursor)
        if fator <= 0.0:
            if inicio_pico is not None:
                consideradas.append((inicio_pico, cursor, "trânsito intenso"))
                inicio_pico = None
            inicio_bloqueio = cursor
            while transito.fator_velocidade(cursor) <= 0.0:
                cursor += PASSO
            consideradas.append((inicio_bloqueio, cursor, transito.motivo_bloqueio(inicio_bloqueio)
                                 or "via bloqueada"))
            continue
        if fator < 1.0 and inicio_pico is None:
            inicio_pico = cursor
        elif fator >= 1.0 and inicio_pico is not None:
            consideradas.append((inicio_pico, cursor, "trânsito intenso"))
            inicio_pico = None
        progresso += fator
        cursor += PASSO
    if inicio_pico is not None:
        consideradas.append((inicio_pico, cursor, "trânsito intenso"))

    fundamento = (f"preparo de {tempo_preparo_min} min + trajeto de ~{round(alvo_min)} min "
                 f"a {VELOCIDADE_BASE_KMH:g} km/h")
    if prioridade == "EXPRESSA":
        fundamento += " (entrega expressa: rota priorizada)"
    return ResultadoSLA(hora_pronto, hora_saida, cursor, round(alvo_min), tuple(consideradas),
                        fundamento, transito.versao)


def minutos_restantes(transito: Transito, agora: datetime, limite: datetime) -> int:
    """Minutos que ainda faltam até a hora limite (0 se já venceu). Não desconta pico/bloqueio:
    é uma estimativa de relógio de parede, usada só para o painel — o cálculo oficial do prazo
    é sempre feito por `calcular_hora_limite`."""
    return max(0, int((limite - agora).total_seconds() // 60))
