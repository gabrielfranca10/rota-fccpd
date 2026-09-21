"""API REST (HTTP/1.0 + JSON) sobre a biblioteca padrão.

Modelo de threads: 1 thread aceita conexões e entrega cada uma a um POOL LIMITADO de
workers (ThreadPoolExecutor). Diferente de ThreadingHTTPServer (1 thread nova por
conexão, sem limite), o pool impede que um pico de acessos crie milhares de threads.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .dominio import ErroRota, ErroValidacao
from .relogio import RelogioSimulado

log = logging.getLogger("rota.http")
MAX_CORPO = 256 * 1024

# ------------------------------------------------------------------- dashboard estático
# Carregado uma vez, na importação: servir bytes já em memória evita I/O de disco a cada
# requisição. Só o que está neste dicionário pode ser servido — nomes vêm de um regex sem
# "/" (ver rota /static/), mas a checagem por chave exata também barra qualquer tentativa
# de sair da pasta (p.ex. "..").
_TIPOS_ESTATICOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
                    ".js": "text/javascript; charset=utf-8"}
_ESTATICOS: dict[str, tuple[str, bytes]] = {}
for _arq in (Path(__file__).parent / "static").iterdir():
    if _arq.suffix in _TIPOS_ESTATICOS:
        _ESTATICOS[_arq.name] = (_TIPOS_ESTATICOS[_arq.suffix], _arq.read_bytes())


class _RespostaEstatica:
    __slots__ = ("tipo", "dados")

    def __init__(self, tipo: str, dados: bytes):
        self.tipo, self.dados = tipo, dados


class ServidorComPool(HTTPServer):
    request_queue_size = 1024      # backlog do listen(); o padrão (5) derruba conexões em rajadas

    def __init__(self, endereco, nucleo, workers: int = 32):
        self.nucleo = nucleo
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="http")
        super().__init__(endereco, Handler)

    def server_bind(self):
        # evita socket.getfqdn() do HTTPServer, que pode travar segundos em DNS mal configurado
        super(HTTPServer, self).server_bind()
        self.server_name, self.server_port = self.server_address[:2]

    def process_request(self, request, client_address):
        self._pool.submit(self._atender, request, client_address)

    def _atender(self, request, client_address):
        try:
            self.finish_request(request, client_address)
        except Exception:
            self.handle_error(request, client_address)
        finally:
            self.shutdown_request(request)

    def server_close(self):
        super().server_close()
        self._pool.shutdown(wait=True)


class ErroHttp(ErroRota):
    def __init__(self, status: int, codigo: str, mensagem: str, detalhes=None):
        super().__init__(mensagem, detalhes)
        self.status, self.codigo = status, codigo


ROTAS = []


def rota(metodo: str, padrao: str):
    def deco(fn):
        ROTAS.append((metodo, re.compile("^" + padrao + "$"), fn))
        return fn
    return deco


class Handler(BaseHTTPRequestHandler):
    server_version = "rota/0.1"
    sys_version = ""
    timeout = 15   # socket: cliente lento não prende um worker para sempre

    def log_message(self, fmt, *args):   # o padrão escreve cada requisição no stderr (lento sob carga)
        log.debug("%s - %s", self.address_string(), fmt % args)

    def do_GET(self):
        self._despachar("GET")

    def do_POST(self):
        self._despachar("POST")

    # ------------------------------------------------------------------
    def _despachar(self, metodo: str) -> None:
        t0 = time.perf_counter()
        self.request_id = self.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        url = urlparse(self.path)
        self.query = {k: v[-1] for k, v in parse_qs(url.query).items()}
        nucleo = self.server.nucleo
        try:
            metodos_do_caminho = []
            for m, rx, fn in ROTAS:
                achou = rx.match(url.path)
                if achou:
                    metodos_do_caminho.append(m)
                    if m == metodo:
                        status, corpo = fn(self, nucleo, *achou.groups())
                        break
            else:
                if metodos_do_caminho:
                    raise ErroHttp(405, "METODO_NAO_PERMITIDO", "método não permitido",
                                   {"permitidos": metodos_do_caminho})
                raise ErroHttp(404, "ROTA_NAO_ENCONTRADA", "rota não encontrada", {"caminho": url.path})
            if isinstance(corpo, _RespostaEstatica):
                self._bruto(status, corpo.tipo, corpo.dados)
            else:
                self._json(status, corpo)
        except ErroRota as e:
            extra = {"Retry-After": "1"} if e.status == 503 else None
            self._json(e.status, {"erro": {"codigo": e.codigo, "mensagem": e.mensagem,
                                           "detalhes": e.detalhes}}, extra)
        except Exception:
            log.exception("erro inesperado em %s %s", metodo, self.path)
            self._json(500, {"erro": {"codigo": "ERRO_INTERNO", "mensagem": "erro interno", "detalhes": {}}})
        finally:
            nucleo.metricas.inc("http_requisicoes")
            nucleo.metricas.inc("http_tempo_total_us", int((time.perf_counter() - t0) * 1e6))

    def _json(self, status: int, corpo, extra=None) -> None:
        dados = json.dumps(corpo, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-Id", self.request_id)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(dados)
        self.server.nucleo.metricas.inc(f"http_{status}")

    def _bruto(self, status: int, tipo: str, dados: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Request-Id", self.request_id)
        self.end_headers()
        self.wfile.write(dados)
        self.server.nucleo.metricas.inc(f"http_{status}")

    def corpo_json(self) -> dict:
        tipo = self.headers.get("Content-Type", "application/json").split(";")[0].strip().lower()
        if tipo != "application/json":
            raise ErroHttp(415, "TIPO_NAO_SUPORTADO", "envie o cabeçalho Content-Type: application/json")
        tam = self.headers.get("Content-Length")
        if tam is None:
            raise ErroHttp(411, "TAMANHO_OBRIGATORIO", "cabeçalho Content-Length obrigatório")
        try:
            n = int(tam)
        except ValueError:
            raise ErroValidacao("Content-Length inválido") from None
        if n < 0 or n > MAX_CORPO:
            self._descartar_corpo(n)
            raise ErroHttp(413, "CORPO_MUITO_GRANDE", f"corpo acima de {MAX_CORPO} bytes")
        bruto = self.rfile.read(n)
        if len(bruto) != n:
            raise ErroValidacao("corpo incompleto")
        try:
            dados = json.loads(bruto.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ErroValidacao("JSON malformado") from None
        if not isinstance(dados, dict):
            raise ErroValidacao("o corpo deve ser um objeto JSON")
        return dados

    def _descartar_corpo(self, n: int) -> None:
        # Lê e joga fora o corpo que o cliente já está enviando antes de fechar a conexão:
        # fechar o socket com dados não lidos no buffer manda RST em vez de FIN (no Windows
        # isso derruba a conexão do cliente antes de ele ler a resposta de erro). Limitado a
        # um múltiplo de MAX_CORPO para não virar um jeito de prender o worker num corpo enorme.
        restante = min(max(n, 0), MAX_CORPO * 4)
        while restante > 0:
            pedaco = self.rfile.read(min(restante, 65536))
            if not pedaco:
                break
            restante -= len(pedaco)

    def inteiro(self, nome: str, padrao: int, minimo: int, maximo: int) -> int:
        try:
            v = int(self.query.get(nome, padrao))
        except ValueError:
            raise ErroValidacao(f"parâmetro '{nome}' deve ser inteiro") from None
        if not minimo <= v <= maximo:
            raise ErroValidacao(f"parâmetro '{nome}' deve estar entre {minimo} e {maximo}")
        return v


# =============================================================================== rotas
P = r"([A-Za-z0-9_.-]{1,80})"


@rota("GET", "/health")
def _health(h, n):
    return 200, {"status": "ok"}


def _resposta_estatica(nome: str):
    item = _ESTATICOS.get(nome)
    if item is None:
        raise ErroHttp(404, "ROTA_NAO_ENCONTRADA", "arquivo não encontrado", {"arquivo": nome})
    tipo, dados = item
    return 200, _RespostaEstatica(tipo, dados)


@rota("GET", "/")
def _raiz(h, n):
    return _resposta_estatica("dashboard.html")


@rota("GET", "/static/" + P)
def _estatico(h, n, nome):
    return _resposta_estatica(nome)


@rota("GET", "/api/v1/entregadores")
def _entregadores(h, n):
    return 200, {"entregadores": n.listar_entregadores()}


@rota("POST", "/api/v1/entregadores")
def _novo_entregador(h, n):
    return 201, n.cadastrar_entregador(h.corpo_json())


@rota("GET", "/api/v1/restaurantes")
def _restaurantes(h, n):
    return 200, {"restaurantes": n.listar_restaurantes()}


@rota("POST", "/api/v1/restaurantes")
def _novo_restaurante(h, n):
    return 201, n.cadastrar_restaurante(h.corpo_json())


@rota("GET", "/api/v1/restaurantes/" + P)
def _restaurante(h, n, rid):
    return 200, n.obter_restaurante(rid)


@rota("POST", "/api/v1/notificacoes")
def _nova_notificacao(h, n):
    notif, nova = n.receber_notificacao(h.corpo_json())
    return (202 if nova else 200), notif       # 202: aceita, processamento assíncrono


@rota("GET", "/api/v1/notificacoes/" + P)
def _notificacao(h, n, nid):
    return 200, n.obter_notificacao(nid)


@rota("GET", "/api/v1/pedidos")
def _pedidos(h, n):
    status = h.query.get("status")
    if status and status not in ("NO_PRAZO", "EM_RISCO", "ATRASADO", "ENTREGUE"):
        raise ErroValidacao("status deve ser NO_PRAZO, EM_RISCO, ATRASADO ou ENTREGUE")
    itens = n.listar_pedidos(status, h.query.get("entregador"), h.inteiro("limite", 100, 1, 1000))
    return 200, {"pedidos": itens, "total": len(itens)}


@rota("GET", "/api/v1/pedidos/" + P)
def _pedido(h, n, pid):
    return 200, n.obter_pedido(pid)


@rota("POST", "/api/v1/pedidos/" + P + "/entrega")
def _confirmar_entrega(h, n, pid):
    return 200, n.confirmar_entrega(pid, h.corpo_json())


@rota("POST", "/api/v1/pedidos/" + P + "/redespacho")
def _redespachar(h, n, pid):
    return 200, n.redespachar_pedido(pid, h.corpo_json())


@rota("GET", "/api/v1/transito")
def _transito(h, n):
    return 200, n.obter_transito()


@rota("POST", "/api/v1/transito/janelas")
def _janela(h, n):
    return 202, n.declarar_janela(h.corpo_json())


@rota("GET", "/api/v1/alertas")
def _alertas(h, n):
    return 200, n.alertas.listar(h.inteiro("apos", 0, 0, 10**12), h.inteiro("limite", 100, 1, 1000))


@rota("GET", "/api/v1/metricas")
def _metricas(h, n):
    return 200, n.estatisticas()


@rota("GET", "/api/v1/auditoria")
def _auditoria(h, n):
    return 200, n.auditoria()


@rota("POST", "/api/v1/admin/relogio")
def _relogio(h, n):
    if not isinstance(n.relogio, RelogioSimulado):
        raise ErroHttp(409, "RELOGIO_REAL", "inicie o servidor com --relogio-simulado para avançar o tempo")
    minutos = h.corpo_json().get("minutos")
    if isinstance(minutos, bool) or not isinstance(minutos, int) or not 1 <= minutos <= 24 * 60:
        raise ErroValidacao("'minutos' deve ser inteiro entre 1 e 1440")
    agora = n.relogio.avancar(minutes=minutos)
    n.executar_monitor()
    return 200, {"agora": agora.isoformat(timespec="seconds")}
