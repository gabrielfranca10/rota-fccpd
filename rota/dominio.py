"""Entidades do domínio, validação de identificadores e erros de negócio."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime

# ---------------------------------------------------------------- status do pedido (saúde do SLA)
NO_PRAZO = "NO_PRAZO"
EM_RISCO = "EM_RISCO"
ATRASADO = "ATRASADO"
ENTREGUE = "ENTREGUE"

# ---------------------------------------------------------------- status da notificação
PENDENTE = "PENDENTE"          # aceita, aguardando um worker
PROCESSADA = "PROCESSADA"      # pedido criado
SEM_PEDIDO = "SEM_PEDIDO"      # notificação informativa (ex.: cancelamento), não gera pedido
NAO_VINCULADA = "NAO_VINCULADA"  # restaurante não cadastrado: vai para triagem manual
ERRO = "ERRO"

# ---------------------------------------------------------------- plataformas e prioridade
PLATAFORMAS = ("IFOOD", "UBEREATS", "RAPPI", "BALCAO")
PADRAO = "PADRAO"
EXPRESSA = "EXPRESSA"
PRIORIDADES = (PADRAO, EXPRESSA)


# ---------------------------------------------------------------- erros -> HTTP
class ErroRota(Exception):
    status = 500
    codigo = "ERRO_INTERNO"

    def __init__(self, mensagem: str, detalhes: dict | None = None):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.detalhes = detalhes or {}


class ErroValidacao(ErroRota):
    status, codigo = 400, "REQUISICAO_INVALIDA"


class NaoEncontrado(ErroRota):
    status, codigo = 404, "NAO_ENCONTRADO"


class Conflito(ErroRota):
    status, codigo = 409, "CONFLITO"


class Sobrecarga(ErroRota):
    status, codigo = 503, "SISTEMA_SOBRECARREGADO"


# ---------------------------------------------------------------- identificadores
_RE_ID = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_RE_PEDIDO = re.compile(r"^[A-Z]{2,12}-\d{3,10}$")


def id_valido(v: str) -> bool:
    return bool(_RE_ID.match(v or ""))


def numero_pedido_valido(v: str) -> bool:
    return bool(_RE_PEDIDO.match(v or ""))


# ---------------------------------------------------------------- entidades
@dataclass
class Entregador:
    entregador_id: str
    nome: str
    veiculo: str
    capacidade: int


@dataclass
class Restaurante:
    restaurante_id: str
    nome: str
    endereco: str
    pedido_ids: list = field(default_factory=list)


@dataclass
class Notificacao:
    notificacao_id: str
    impressao_digital: str
    restaurante_id: str
    numero_pedido: str
    plataforma: str
    hora_notificacao: datetime
    descricao: str
    tempo_preparo_min: int | None
    distancia_km: float
    prioridade: str
    status: str = PENDENTE
    pedido_id: str | None = None
    erro: str | None = None
    recebida_em: str = ""
    duplicatas_recebidas: int = 0


@dataclass
class Pedido:
    pedido_id: str
    restaurante_id: str
    notificacao_id: str
    numero_pedido: str
    plataforma: str
    prioridade: str
    tempo_preparo_min: int
    distancia_km: float
    hora_notificacao: datetime
    hora_pronto: datetime
    hora_saida: datetime
    hora_limite_entrega: datetime
    fundamento: str
    janelas_consideradas: tuple
    transito_versao: int
    entregador_responsavel_id: str | None = None
    entregue_em: str | None = None
    entregue_atrasado: bool | None = None
    codigo_confirmacao: str | None = None
    nivel_alerta: str = NO_PRAZO    # último nível já alertado (evita alerta repetido)
    recalculos: int = 0
