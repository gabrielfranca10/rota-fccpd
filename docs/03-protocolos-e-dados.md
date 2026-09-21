# 3. Protocolos de comunicação e tratamento de dados

> Critério da rubrica: **Communication Protocols and Data Handling**

## 3.1 Onde há comunicação

| Canal | Entre | Protocolo (Entrega 1) | Evolução |
|---|---|---|---|
| Externo | clientes ↔ rota | **HTTP/1.0 + JSON (REST)** | continua REST na borda |
| Interno assíncrono | API → workers de ingestão/recálculo/despacho | filas em memória (mensagem = id do recurso) | fila durável (RabbitMQ/Kafka) |
| Interno síncrono | API → núcleo | chamada de método | **gRPC** (`rota.pedido.v1`) entre serviços |
| Notificação | núcleo → clientes | *polling* com cursor em `/alertas` | *server streaming* gRPC |

## 3.2 Por que REST + JSON na borda

| Opção | Prós | Contras | Decisão |
|---|---|---|---|
| **REST + JSON** | universal (navegador, `curl`, integrações das plataformas), legível, fácil de depurar, sem estado entre requisições (escala horizontal atrás de balanceador) | sem contrato tipado; JSON maior e mais lento | **borda** (esta entrega) |
| gRPC + Protobuf | contrato forte, binário compacto, HTTP/2, streaming, deadlines | navegador/app exige mais integração; dependência externa | **miolo**, a partir da Entrega 2 |
| WebSocket | push em tempo real pro app do entregador | conexão longa prende uma thread do pool no nosso modelo | não nesta entrega |
| Socket TCP próprio | controle total | reinventar enquadramento, parsing e erros | descartado |

**HTTP/1.0 (conexão fechada por resposta):** cada requisição ocupa uma thread do pool só enquanto é atendida. Com *keep-alive*, um cliente ocioso (ex.: app do entregador esperando) seguraria uma thread do pool limitado. Custo aceito: um *handshake* TCP por requisição.

## 3.3 Convenções

* Base: `/api/v1` (versão na URL para evoluir sem quebrar clientes).
* Corpo: JSON UTF-8 com `Content-Type: application/json` (outro tipo → `415`); limite de 256 KB (`413`); `Content-Length` obrigatório em POST (`411`).
* Instantes: ISO 8601 com fuso (`2026-09-21T11:00:00-03:00`) — granularidade de **minuto**, diferente de um domínio de dias úteis. O sufixo `Z` (UTC) é aceito e qualquer fuso é convertido para o horário de Brasília: `14:00:00Z` e `11:00:00-03:00` são o mesmo instante e, portanto, a mesma notificação (mesma impressão digital). Sem fuso, vale Brasília.
* IDs: `notif_<uuid4>`, `ped_<uuid4>` (não adivinháveis, gerados sem coordenação — funcionam igual quando houver vários nós).
* Todo response traz `X-Request-Id` (ecoa o do cliente ou gera um) para rastrear uma requisição nos logs.
* Timeout de leitura do socket: 15 s.

## 3.4 Formato de erro (único para toda a API)

```json
{ "erro": { "codigo": "CONFLITO", "mensagem": "entregador destino está no limite de capacidade",
            "detalhes": { "capacidade": 4 } } }
```

| HTTP | `codigo` | Quando |
|---|---|---|
| 400 | `REQUISICAO_INVALIDA` | JSON malformado, campo faltando/inválido, formato de id/número de pedido errado |
| 404 | `NAO_ENCONTRADO` / `ROTA_NAO_ENCONTRADA` | recurso ou rota inexistente |
| 405 | `METODO_NAO_PERMITIDO` | rota existe, método não (`detalhes.permitidos`); vale também para `PUT`, `PATCH`, `DELETE` e `OPTIONS`, que a API não usa |
| 409 | `CONFLITO` | estado não permite (já entregue, não é o responsável, capacidade esgotada, duplicidade de cadastro) |
| 411 / 413 / 415 | `TAMANHO_OBRIGATORIO` / `CORPO_MUITO_GRANDE` / `TIPO_NAO_SUPORTADO` | problemas no corpo |
| 503 | `SISTEMA_SOBRECARREGADO` | fila cheia ou desligando; vem com `Retry-After: 1` |
| 500 | `ERRO_INTERNO` | bug; detalhes só no log |

O `codigo` é para máquinas (estável); a `mensagem` é para pessoas.

## 3.5 Endpoints

| Método | Caminho | Sucesso | Semântica |
|---|---|---|---|
| GET | `/health` | 200 | vivo? |
| GET | `/` , `/static/{arquivo}` | 200 | dashboard estático (HTML/CSS/JS) |
| GET/POST | `/api/v1/entregadores` | 200/201 | listar / cadastrar |
| GET/POST | `/api/v1/restaurantes` | 200/201 | listar / cadastrar |
| GET | `/api/v1/restaurantes/{id}` | 200 | restaurante + pedidos |
| POST | `/api/v1/notificacoes` | **202** nova / **200** duplicata | ingestão assíncrona e idempotente |
| GET | `/api/v1/notificacoes/{id}` | 200 | acompanhar o processamento |
| GET | `/api/v1/pedidos?status=&entregador=&limite=` | 200 | ordenados por hora limite |
| GET | `/api/v1/pedidos/{id}` | 200 | pedido com memória de cálculo |
| POST | `/api/v1/pedidos/{id}/entrega` | 200 | idempotente para o mesmo código de confirmação |
| POST | `/api/v1/pedidos/{id}/redespacho` | 200 | troca o entregador responsável |
| GET | `/api/v1/transito` | 200 | versão + janelas declaradas |
| POST | `/api/v1/transito/janelas` | **202** | nova versão; recálculo assíncrono |
| GET | `/api/v1/alertas?apos=<seq>&limite=` | 200 | polling com cursor |
| GET | `/api/v1/metricas` | 200 | contadores, filas, threads |
| GET | `/api/v1/auditoria` | 200 | invariantes (`ok: true/false`) |
| POST | `/api/v1/admin/relogio` | 200 | só com `--relogio-simulado`: avança N minutos |

Confirmação e redespacho usam `POST .../entrega` (e não `PUT`/`DELETE`) porque são **transições de estado** com regras, não substituição do recurso; o pedido continua existindo e consultável.

### Exemplo: ingestão

```http
POST /api/v1/notificacoes
Content-Type: application/json

{ "restaurante_id": "rest-0000", "numero_pedido": "IFOOD-000123", "plataforma": "IFOOD",
  "hora_notificacao": "2026-09-21T11:00:00-03:00", "distancia_km": 5.0,
  "descricao": "Pedido: 2x X-Burger. Tempo estimado de preparo: 18 minutos." }
```

Campos opcionais: `tempo_preparo_min` (se ausente, extraído da descrição por expressão regular — "tempo de preparo: N minutos"), `prioridade` (`PADRAO` padrão / `EXPRESSA`).

```http
HTTP/1.0 202 Accepted
X-Request-Id: 3f9a1c...
{ "notificacao_id": "notif_83ee...", "status": "PENDENTE", "pedido_id": null,
  "duplicatas_recebidas": 0, "impressao_digital": "7e57d4...", ... }
```

Padrão **202 + consulta**: a API responde em milissegundos mesmo na rajada; o cliente acompanha em `GET /notificacoes/{id}` até `PROCESSADA` e lê `pedido_id`.

### Exemplo: pedido calculado (com memória de cálculo)

```json
{ "pedido_id": "ped_a3be...", "status": "NO_PRAZO", "tempo_preparo_min": 18, "distancia_km": 5.0,
  "hora_notificacao": "2026-09-21T11:00:00-03:00", "hora_pronto": "2026-09-21T11:18:00-03:00",
  "hora_saida": "2026-09-21T11:18:00-03:00", "hora_limite_entrega": "2026-09-21T11:35:00-03:00",
  "minutos_restantes": 35, "fundamento": "preparo de 18 min + trajeto de ~17 min a 18 km/h",
  "janelas_consideradas": [], "transito_versao": 1, "entregador_responsavel_id": "ent-joao" }
```

Os nomes (`hora_limite_entrega`, `hora_saida`, `minutos_restantes`, `fundamento`, `janelas_consideradas`, `NO_PRAZO`/`EM_RISCO`/`ATRASADO`/`ENTREGUE`) são os que viram o contrato gRPC `rota.pedido.v1` da Entrega 2 — a migração não muda o modelo.

## 3.6 Semântica das operações

| Propriedade | Como |
|---|---|
| **Idempotência da ingestão** | a identidade é a impressão digital SHA-256 de `plataforma + número do pedido + hora da notificação + descrição normalizada` (minúsculas, espaços colapsados). Reenviar = `200` com a mesma notificação e `duplicatas_recebidas+1`. Isso torna seguro o *retry* do webhook — pré-requisito para tolerância a falhas nas próximas entregas. |
| Idempotência da confirmação | mesmo `codigo_confirmacao` repetido → `200` com o mesmo estado; outro código → `409` |
| Consistência | num único nó, cada operação é **atômica e linearizável** por restaurante (lock). Listagens são montadas restaurante a restaurante — podem refletir instantes ligeiramente diferentes (documentado). |
| Entrega das filas internas | *exatamente uma vez* enquanto o processo vive (memória); na versão distribuída será *pelo menos uma vez* + consumidor idempotente (a impressão digital já resolve) |
| Backpressure | fila cheia → `503` + `Retry-After`; o cliente de carga respeita e reenvia |

## 3.7 Tratamento e validação de dados

* **Número do pedido**: formato `PLATAFORMA-CODIGO` (ex.: `IFOOD-000123`), validado por expressão regular; `plataforma` restrita a um conjunto fechado (`IFOOD`, `UBEREATS`, `RAPPI`, `BALCAO`).
* Tipos estritos: `tempo_preparo_min` inteiro 1–180 (`true` é rejeitado, embora em Python `bool` seja subclasse de `int`); `distancia_km` numérico 0,1–50; `capacidade` do entregador inteiro 1–10; textos não vazios e com tamanho máximo.
* Instantes ISO 8601 com granularidade de minuto, no fuso do restaurante (UTC−3) — diferente de datas civis, porque o SLA aqui é de minutos, não de dias.
* A API só devolve **cópias** do estado (ver R15 no doc 02).

## 3.8 Mensagens internas (futuras mensagens de rede)

A mensagem da fila de ingestão hoje é o `notificacao_id`; o conteúdo da notificação é imutável após a criação. A fila de despacho carrega apenas um **sinal** ("pode haver vaga"): quem recebe a vaga é sempre o pedido em espera mais urgente (menor hora limite), e não o que foi enfileirado primeiro. Sinal repetido não custa nada: sem vaga, o despacho encerra na primeira olhada. Na Entrega 2, as mensagens de ingestão viram os próprios objetos serializados (os campos já são tipos simples: strings, instantes ISO, inteiros, booleanos), sem mudar os consumidores.
