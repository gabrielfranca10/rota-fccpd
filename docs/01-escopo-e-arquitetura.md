# 1. Escopo e arquitetura

> Critério da rubrica: **Project Scope and Architecture Design**

## 1.1 O problema

O **rota** é o núcleo de despacho de pedidos de uma central de entregas multi-plataforma (domínio: *Restaurante, Pedido, Entregador, SLA de entrega*). O risco central do domínio é **perder o prazo de entrega**: o cliente cancela, a plataforma pune o restaurante com nota baixa e a reputação da central cai.

Os pedidos nascem das **notificações** que as plataformas (iFood, Uber Eats, Rappi, balcão) mandam por webhook. Elas chegam em **rajada** — dezenas por segundo na hora do almoço e do jantar — e com características que tornam o problema naturalmente concorrente:

* a **mesma** notificação chega duas vezes (retry de webhook do agregador quando a resposta demora);
* vários pedidos do **mesmo** restaurante chegam ao mesmo tempo;
* o **trânsito muda** no meio do processamento (a central declara pico de horário de almoço ou uma via bloqueada), e todo pedido já calculado precisa ser revisto;
* entregadores confirmam entrega e são redespachados **enquanto** tudo isso acontece;
* cada entregador tem uma **capacidade** limitada de pedidos simultâneos — atribuir além da capacidade é tão grave quanto perder um pedido;
* o tempo passa: pedidos ficam em risco e atrasam sozinhos.

## 1.2 Objetivo do semestre e desta entrega

| Entrega | Foco (roadmap proposto — ajustar às próximas rubricas) |
|---|---|
| **1 (esta)** | Arquitetura completa + **protótipo single-node** do *Núcleo de Despacho* com concorrência local |
| 2 | Distribuição: serviços separados (Ingestão, Pedidos, Frota) comunicando por gRPC — contrato `rota.pedido.v1` |
| 3 | Replicação e consistência: réplicas do serviço de Pedidos, particionamento por restaurante, fila de mensagens durável |
| 4 | Tolerância a falhas e deploy: containers, health checks, retry com idempotência, failover |

### Dentro do escopo da Entrega 1

| Requisito funcional | Onde |
|---|---|
| RF1 Receber notificações via API, com resposta imediata (202) e processamento assíncrono | `receber_notificacao`, `_worker_ingestao` |
| RF2 Deduplicar notificações pelo conteúdo, mesmo em retries do webhook | `impressao_digital` |
| RF3 Vincular a notificação ao restaurante cadastrado | `_processar` (checagem em `_restaurantes`) |
| RF4 Calcular a hora limite de entrega (preparo + trajeto, pico, bloqueio, prioridade) | `calcular_hora_limite` |
| RF5 Despachar automaticamente para o entregador disponível de menor carga, respeitando a capacidade | `_tentar_atribuir` |
| RF6 Manter fila de espera para pedidos sem entregador disponível e, quando uma vaga libera, atribuí-la ao pedido **mais urgente** (menor hora limite) | `_aguardando`, `_worker_despacho`, `_mais_urgente_em_espera`, `_acordar_fila_espera` |
| RF7 Registrar confirmação de entrega (com ou sem atraso) e redespachar pedidos entre entregadores | `confirmar_entrega`, `redespachar_pedido` |
| RF8 Declarar janelas de pico/bloqueio no trânsito e recalcular os pedidos afetados | `declarar_janela`, `_recalcular_todos` |
| RF9 Monitorar pedidos e emitir alertas (EM_RISCO, ATRASADO, RECALCULADO, AGUARDANDO_ENTREGADOR) | `executar_monitor`, `Alertas` |
| RF10 Auditoria das invariantes do sistema | `auditoria` |

| Requisito não funcional | Como é atendido |
|---|---|
| RNF1 **Segurança (safety):** nunca pedido duplicado, nunca pedido "órfão" (sem restaurante), nunca entregador acima da capacidade, nunca pedido calculado com trânsito desatualizado | locks + auditoria com oráculo sequencial |
| RNF2 **Vivacidade (liveness):** sem deadlock, sem starvation do escritor de trânsito, pedido em espera eventualmente é despachado | hierarquia de locks, RWLock com preferência para escritor, fila de despacho + varredura do monitor |
| RNF3 **Desempenho:** aceitar rajadas sem criar threads sem limite | pools limitados, fila limitada com *backpressure* (503) |
| RNF4 **Portabilidade:** roda em qualquer máquina com Python ≥ 3.10, sem instalar nada | somente biblioteca padrão |
| RNF5 **Observabilidade:** métricas, alertas, `X-Request-Id`, logs com nome da thread | `/api/v1/metricas`, logging |

### Fora do escopo (planejado para entregas futuras)

Autenticação/autorização, persistência em banco, geolocalização real (a distância é um campo de entrada, não calculada por mapa), integração real com as APIs das plataformas, pagamento/comissão dos entregadores, múltiplos nós. O estado fica **em memória**: é um protótipo de concorrência local, como pede a entrega.

## 1.3 Modelo de domínio

```
 Entregador 1 ──── N Pedido N ──── 1 Restaurante 1 ──── N Pedido N ──── 1 Notificação
   │ agenda (pedidos em aberto, até `capacidade`)
   └── redespacho troca o dono; capacidade nunca é ultrapassada

 Notificação: PENDENTE ──► PROCESSADA (gerou pedido)
                       ├─► SEM_PEDIDO (informativa, ex.: cancelamento)
                       ├─► NAO_VINCULADA (restaurante não cadastrado → triagem manual)
                       └─► ERRO

 Pedido (status DERIVADO do relógio, não armazenado):
     NO_PRAZO ──(faltam ≤ janela de risco)──► EM_RISCO ──(passou a hora limite)──► ATRASADO
         └────────────────── confirmação de entrega (código) ────────────────► ENTREGUE

 Entregador (dimensão independente do status acima):
     entregador_responsavel_id = None  ──(vaga livre encontrada)──►  atribuído
        (pedido fica na fila de espera `_aguardando` enquanto isso)
```

Decisões importantes:

1. O status do pedido **é calculado na hora** a partir da hora limite e do relógio (`Nucleo._status`). Não existe uma thread "virando" pedidos para ATRASADO — portanto não existe corrida entre essa thread e um entregador confirmando a entrega no último minuto. O monitor só **emite alertas**.
2. A confirmação de entrega **nunca é recusada por estar atrasada** — o mundo real não deixa de registrar uma entrega só porque chegou tarde. O que muda é o campo `entregue_atrasado`, calculado no instante da confirmação.
3. A atribuição de entregador é uma dimensão **separada** do status de prazo: um pedido pode estar `NO_PRAZO` e ainda `aguardando entregador` — o relógio não espera a frota ter vaga.

## 1.4 Arquitetura do protótipo (um processo, várias threads)

```
                        Clientes (app do entregador, integrações das plataformas, script de carga)
                                          │ HTTP/1.0 + JSON
                                          ▼
 ┌──────────────────────────────── processo Python (single-node) ─────────────────────────────────┐
 │  [http-aceitador] 1 thread: accept()                                                           │
 │         │ entrega cada conexão                                                                 │
 │         ▼                                                                                      │
 │  [http-0 … http-31] POOL LIMITADO (ThreadPoolExecutor)      http_api.py                        │
 │         │ rotas REST → chamadas ao núcleo                                                      │
 │         ▼                                                                                      │
 │  ┌──────────────────────────────── Nucleo (nucleo.py) ─────────────────────────────────┐       │
 │  │ receber_notificacao ──(dedup + put_nowait)──► FILA DE INGESTÃO (queue.Queue, 1000)  │       │
 │  │                                                   │                                 │       │
 │  │                          [ingestao-0 … ingestao-3] consumidores                     │       │
 │  │                                   │ calcula hora limite (função pura) + despacha    │       │
 │  │                                   ▼                                                 │       │
 │  │  Transito (imutável, versão N) ◄── RWLock ──► [recalculo] 1 thread                  │       │
 │  │  Restaurantes + Pedidos  (1 Lock por restaurante)                                   │       │
 │  │  Agendas/capacidade dos entregadores  (1 Lock por entregador)                       │       │
 │  │  Fila de espera (`_aguardando`) ──► FILA DE DESPACHO ──► [despacho] 1 thread        │       │
 │  │  Índices globais (Lock curto)          Alertas (buffer circular)   Métricas         │       │
 │  │                                                      ▲                              │       │
 │  │                                   [monitor] 1 thread periódica                      │       │
 │  └──────────────────────────────────────────────────────────────────────────────────────┘      │
 │  [MainThread] sobe tudo, espera Ctrl+C/SIGTERM e faz o desligamento gracioso                   │
 └────────────────────────────────────────────────────────────────────────────────────────────────┘
```

| Componente | Arquivo | Responsabilidade | Papel na concorrência |
|---|---|---|---|
| API HTTP | `rota/http_api.py` | rotas REST, validação do corpo, mapeamento de erros para HTTP | pool limitado de threads; timeout de socket |
| Núcleo | `rota/nucleo.py` | regras de negócio e estado | todos os locks e a hierarquia |
| Motor de SLA | `rota/transito.py` | trânsito imutável e cálculo da hora limite | **função pura**: não compartilha estado |
| RWLock | `rota/rwlock.py` | leitores/escritores com preferência ao escritor | protege a troca do trânsito |
| Domínio | `rota/dominio.py` | entidades, validação de ids, erros | — |
| Relógio | `rota/relogio.py` | hora de Brasília; relógio simulado para testes e demo | lock próprio (folha) |
| Dados de demo | `rota/seed.py` | 4 entregadores e N restaurantes | — |
| Entrada | `rota/__main__.py` | CLI, sinais, desligamento ordenado | — |
| Dashboard | `rota/static/*` | painel visual somente leitura sobre a API | sem estado próprio (HTML/CSS/JS estáticos) |

### Fluxo principal: da notificação ao alerta

1. `POST /api/v1/notificacoes` → uma thread do pool HTTP valida o JSON e calcula a **impressão digital** (SHA-256 de plataforma + número do pedido + hora + descrição normalizada).
2. Dentro de **uma** seção crítica: se a impressão já existe → responde **200** com a notificação original; senão enfileira com `put_nowait` e registra → responde **202**. Fila cheia → **503** + `Retry-After`.
3. Um worker de ingestão retira o id da fila, acha o restaurante, e — segurando a **leitura** do trânsito — calcula a hora limite e, **na mesma seção crítica do restaurante**, tenta atribuir um entregador de menor carga com vaga (verificando a capacidade sob o lock daquele entregador). Sem vaga, o pedido entra na fila de espera.
4. Se o pedido já nasce em risco/atrasado, publica um alerta. O monitor continua acompanhando e também varre a fila de espera como rede de segurança.

## 1.5 Decisões de tecnologia (e por quê)

| Decisão | Escolha | Alternativas consideradas | Justificativa |
|---|---|---|---|
| Linguagem | **Python 3.10+** | Go, Java | Linguagem que toda a equipe domina e usada nos exercícios de concorrência da disciplina (`threading.Lock`). Go/Java seriam mais rápidos, mas o objetivo desta entrega é **clareza** do modelo de concorrência. |
| Modelo de concorrência | **threads** (`threading`) | `asyncio`, `multiprocessing` | Threads tornam explícitos locks, condições e deadlocks — os temas da disciplina. `asyncio` só troca de tarefa em `await` (esconde as corridas); `multiprocessing` não compartilha memória, o que eliminaria o problema que queremos estudar. O GIL não impede corridas (ver doc 02). |
| Servidor HTTP | `http.server` + **pool próprio** | Flask/FastAPI, `ThreadingHTTPServer` | Sem dependências e com o modelo de threads **visível e controlado**. `ThreadingHTTPServer` cria 1 thread por conexão sem limite; nosso pool limita a 32. |
| Dependências | **nenhuma** (só biblioteca padrão) | pytest, requests | Qualquer membro/professor roda com `python -m rota`, sem `pip install`. Testes com `unittest`. |
| Estado | **memória** | PostgreSQL, Redis | Entrega 1 é concorrência local; banco entra na Entrega 3 (e passaria a ser mais um recurso compartilhado). |
| Trânsito | objeto **imutável** + versão | objeto mutável com lock | Leitores nunca veem estado pela metade; declarar uma janela é trocar uma referência. |
| Relógio | injetável, **UTC−3 fixo** | `zoneinfo` | Brasil sem horário de verão desde 2019; `zoneinfo` exige `tzdata` no Windows. O relógio simulado permite testar atrasos sem esperar minutos de verdade. |
| Identidade da notificação | **impressão digital do conteúdo** | id da fonte | O mesmo evento pode chegar duas vezes num retry de webhook, com timestamps de recebimento diferentes. |
| Despacho | **capacidade por entregador + fila de espera** | fila global única; atribuição manual sempre | modela um recurso físico real (moto/bike carrega N pedidos) sem exigir intervenção humana no caso comum |
| Protocolo externo | **REST + JSON** | gRPC | Ver doc 03: REST na borda, gRPC no miolo a partir da Entrega 2. |

## 1.6 Arquitetura-alvo (distribuída) — para onde o protótipo evolui

```
   Plataformas (iFood, Uber Eats...)   App do entregador
         │ webhooks                        │ REST
         ▼                                 ▼
   ┌──────────────┐        ┌──────────────┐
   │   Gateway    │◄──────►│  API / BFF   │  (sem estado; várias réplicas atrás de balanceador)
   └──────┬───────┘        └──────┬───────┘
          │ publica                │ gRPC
          ▼                        ▼
   ┌──────────────┐  gRPC  ┌─────────────────────┐        ┌──────────────┐
   │ Fila durável │──────► │ Serviço de Pedidos  │◄──────►│  Frota       │
   │ (RabbitMQ/   │        │ particionado por    │  gRPC  │ (entregadores)│
   │  Kafka)      │        │ restaurante; réplicas│       └──────────────┘
   └──────────────┘        └──────────┬──────────┘
                                      │ stream AcompanharPedidosEmRisco
                                      ▼
                              Notificações / painel
```

| No protótipo (Entrega 1) | Vira (entregas seguintes) |
|---|---|
| `queue.Queue` limitada | fila durável (at-least-once) + consumidor idempotente pela impressão digital |
| Lock por restaurante | partição por restaurante: cada restaurante tem **um** nó dono (sem lock distribuído no caminho comum) |
| Ordem de locks das agendas de entregador | mesma regra aplicada a locks/leases distribuídos, ou saga com compensação |
| Trânsito imutável + versão | trânsito versionado replicado; pedido guarda a versão usada (já guarda hoje) |
| `calcular_hora_limite` (função pura) | RPC unário do contrato `rota.pedido.v1` |
| Alertas por *polling* com cursor | RPC server-streaming `AcompanharPedidosEmRisco` (retomada pelo cursor `desde`) |
| Relógio local | relógios não sincronizados entre nós → instantes com versão lógica, não só timestamp |

## 1.7 Riscos e limitações conhecidas

* Estado em memória: reiniciar o processo apaga tudo (proposital nesta entrega).
* Cálculo de trânsito simplificado (velocidade constante + fator de pico/bloqueio; não é um roteirizador real). **Não substitui um serviço de mapas real.**
* Índices de notificações crescem sem limite (sem expurgo); aceitável para o protótipo.
* O monitor, a listagem, as estatísticas e a auditoria percorrem todo o estado: custo linear no número de pedidos (medido no doc 04, seção 4.4). A ingestão em si não desacelera.
* O GIL do CPython impede paralelismo de CPU entre threads; o ganho aqui é concorrência (sobreposição de espera). Paralelismo real é tema de entregas futuras (processos/nós).
