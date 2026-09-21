# 2. Concorrência: riscos e sincronização

> Critério da rubrica: **Identification of Concurrency Risks and Synchronization**

## 2.1 Quem executa ao mesmo tempo

| Thread(s) | Quantidade | O que faz | Estado que toca |
|---|---|---|---|
| `MainThread` | 1 | inicialização, espera sinal, desligamento | ciclo de vida |
| `http-aceitador` | 1 | `accept()` e entrega a conexão ao pool | — |
| `http-N` | até 32 | atende requisições (notificar, confirmar, redespachar, consultar, declarar janela) | **tudo** |
| `ingestao-N` | 4 | consome a fila, calcula hora limite, grava pedido e tenta despachar | notificações, restaurantes, pedidos, agendas, trânsito (leitura) |
| `recalculo` | 1 | revisa pedidos quando o trânsito muda | restaurantes, pedidos, trânsito (leitura) |
| `despacho` | 1 | enquanto houver vaga, atribui ao pedido em espera mais urgente | restaurantes, pedidos, agendas |
| `monitor` | 1 | a cada 1 s, emite alertas de EM_RISCO/ATRASADO e varre a fila de espera | pedidos (nível de alerta), fila de espera |

Ou seja: **até 41 threads** podem tocar as mesmas estruturas simultaneamente.

## 2.2 Mapa do estado compartilhado

| Recurso | Escritores | Leitores | Proteção |
|---|---|---|---|
| Trânsito | http (janela) | ingestão, recálculo, http | objeto **imutável** + `RWLock` (L1) |
| Restaurante e seus pedidos | ingestão, recálculo, http (confirmar/redespachar), despacho | http | **1 Lock por restaurante** (L2) |
| Agenda/capacidade de cada entregador | ingestão (despacho inicial), http (confirmar/redespachar), despacho | http, auditoria | **1 Lock por entregador** (L3), em ordem |
| Fila de espera (`_aguardando`) | ingestão, despacho, http (confirmar libera vaga) | despacho, monitor, auditoria | `_indice_lock` (L4) |
| Índices (restaurantes, entregadores, pedidos) | http (cadastro), ingestão | todos | `_indice_lock` (L4) |
| Notificações + índice de impressões digitais + "aceitando" | http, ingestão | http | `_notif_lock` (L4) |
| Fila de ingestão / recálculo / despacho | produtores diversos | consumidores dedicados | `queue.Queue` (mutex + variáveis de condição internas) |
| Alertas, métricas | todos | http | lock próprio (L5, folha) |

## 2.3 Catálogo de riscos

Cada risco tem: o cenário, a intercalação que causa o problema, a solução implementada e o teste que a comprova.

### R1 — Notificação duplicada vira dois pedidos (verificar-e-agir)

| t | Thread A (webhook original) | Thread B (retry do agregador) |
|---|---|---|
| 1 | "essa impressão digital já existe?" → não | |
| 2 | | "essa impressão digital já existe?" → não |
| 3 | cria pedido | cria pedido ⇒ **dois pedidos para o mesmo ato** |

**Solução:** verificar, enfileirar e registrar ocorrem **dentro da mesma seção crítica** (`_notif_lock` em `receber_notificacao`). **Prova:** `test_mesma_notificacao_100_threads_gera_um_pedido` (100 threads soltas por uma `Barrier`: 1 pedido). `scripts/demo_corrida.py` mostra a versão ingênua criando dezenas de pedidos. Teste de mutação: tirando a verificação do lock, o teste acusa mais de um pedido.

### R2 — Atualização perdida no mesmo restaurante

Duas notificações do mesmo restaurante chegam juntas; os dois workers fazem `pedido_ids.append(...)` e tentam despachar ao mesmo tempo. Sem exclusão, uma escrita pode sobrescrever a outra ou a lista pode ser lida no meio de uma alteração. **Solução:** **lock por restaurante** (L2) — restaurantes diferentes andam em paralelo; o mesmo restaurante é serializado. **Prova:** `test_ingestao_em_massa_com_duplicatas` (20 threads × 200 envios; auditoria confere pedidos ↔ notificações 1:1).

### R3 — Trânsito muda no meio do cálculo (pedido calculado com regra velha)

| t | Worker de ingestão | Central (http) | Recálculo |
|---|---|---|---|
| 1 | lê trânsito v1, calcula limite 11:35 | | |
| 2 | | troca para v2 (declara pico 11:00–12:00) | |
| 3 | | | revisa todos os pedidos existentes |
| 4 | **grava** o pedido com v1 (11:35) ⇒ ficou fora da revisão, **limite errado** | | |

**Solução (leitores-escritores):** o worker segura a **leitura** do `RWLock` desde a leitura do trânsito até gravar o pedido. A troca de trânsito pega a **escrita**, que espera todos os cálculos em curso terminarem. Assim, todo pedido gravado com a versão antiga já existe quando o recálculo começa, e todo pedido gravado depois já usa a nova. Cada pedido guarda `transito_versao`. **Prova:** `test_transito_muda_durante_ingestao` (10 janelas declaradas durante ~1.650 envios; a auditoria recalcula *sequencialmente* todos os pedidos e compara — zero divergências) e `test_janela_declarada_no_meio_do_calculo_nao_deixa_pedido_com_transito_velho`, que **força** a intercalação ruim: segura o cálculo por 0,3 s dentro da seção crítica enquanto a central declara o pico. Só o primeiro teste não bastava: tirando o lock de leitura, ele continuava passando (ver E15 no doc 05).

### R4 — Starvation do escritor

Com ingestão contínua sempre há algum leitor ativo; um RWLock ingênuo nunca daria vez à atualização do trânsito. **Solução:** `RWLock` com **preferência para escritor**: havendo escritor esperando, novos leitores aguardam (`rota/rwlock.py`). **Prova:** `TestRWLock`: `test_escritor_exclusivo_e_leitores_simultaneos` (o escritor nunca convive com leitor) e `test_escritor_nao_passa_fome_com_leitores_sobrepostos` (4 leitores escalonados mantêm sempre algum leitor ativo; o escritor precisa entrar em até 2 s). Antes só existia o primeiro, que prova exclusão mas **não** a preferência para o escritor.

### R5 — Despachar além da capacidade do entregador (a corrida específica deste domínio)

| t | Worker de ingestão (pedido X) | Worker de ingestão (pedido Y) |
|---|---|---|
| 1 | vê agenda do João com 3/4 vagas ocupadas | vê agenda do João com 3/4 vagas ocupadas (ainda não gravou) |
| 2 | atribui X ao João → 4/4 | atribui Y ao João → **5/4: capacidade estourada** |

É o risco mais específico deste domínio: o entregador é um recurso físico com capacidade limitada. **Solução:** ranking por tamanho de agenda é feito **sem** lock (só para ordenar candidatos — pode estar levemente desatualizado), mas a decisão final — checar `len(agenda) < capacidade` e inserir — acontece **sob o lock daquele entregador** (`_tentar_atribuir`), sempre chamada com o lock do restaurante (L2) já em mãos e segurando **no máximo um** lock de entregador (L3) por vez. Se o candidato encheu entre o ranking e a checagem, a função simplesmente tenta o próximo. **Prova:** a auditoria confere `len(agenda) <= capacidade` para todo entregador em toda execução; `test_capacidade_limita_atribuicao_e_fila_de_espera` e `test_redespacho_respeita_capacidade` (sequenciais) e `test_capacidade_nao_estoura_com_atribuicoes_simultaneas`, em que 8 pedidos de restaurantes diferentes disputam 2 vagas com o `len` da agenda deliberadamente lento (alarga a janela entre checar e atribuir).

### R6 — Deadlock no redespacho cruzado

Redespachar exige travar a agenda de origem **e** a de destino.

| t | Thread 1 (João → Márcia) | Thread 2 (Márcia → João) |
|---|---|---|
| 1 | trava agenda João | trava agenda Márcia |
| 2 | espera agenda Márcia… | espera agenda João… ⇒ **espera circular: deadlock** |

As 4 condições de Coffman estão presentes (exclusão mútua, posse-e-espera, não preempção, espera circular). **Solução:** quebrar a **espera circular** — sempre travar as duas agendas em **ordem crescente de `entregador_id`** (`redespachar_pedido`). **Prova:** `test_redespacho_cruzado_sem_deadlock` (16 threads × 2000 redespachos cruzados). Teste de mutação: com a ordem "origem primeiro", o teste falha com "N threads presas após 20 s (provável deadlock)". Demonstração visual: `scripts/demo_deadlock.py`.

### R7 — Pedido "órfão", em duas agendas, ou preso na fila de espera errado

Se a remoção da agenda de origem e a inclusão na de destino não forem atômicas, alguém pode ver o pedido em nenhuma agenda (pedido sem responsável = pedido perdido) ou em duas. Da mesma forma, um pedido não pode estar ao mesmo tempo "com entregador" e "na fila de espera". **Solução:** as operações de mover acontecem com **os locks de agenda necessários seguros**; a fila de espera (`_aguardando`) só é tocada sob `_indice_lock`, sempre junto com a decisão de atribuir/desatribuir. **Prova:** a auditoria verifica "todo pedido em aberto com entregador está em exatamente uma agenda, a do responsável" e "todo pedido sem entregador está na fila de espera e vice-versa".

### R8 — Confirmar entrega × redespachar o mesmo pedido

Um entregador confirma a entrega enquanto o despachante redireciona o pedido para outro. **Solução:** ambas as operações pegam primeiro o **lock do restaurante** (L2) — ficam serializadas; quem chega depois vê o estado novo (redespachar um pedido já entregue → 409; confirmar sendo quem deixou de ser responsável → 409). **Prova:** `test_confirmar_e_redespachar_ao_mesmo_tempo` (20 threads) e `test_confirmar_nao_intercala_com_redespacho`, que congela a confirmação entre "conferir o responsável" e "liberar a vaga" e exige que o redespacho espere e receba 409.

### R9 — Confirmação no último minuto × atraso

**Solução:** não existe thread que "atrasa" o pedido; o status é **derivado do relógio** no momento em que é consultado, e o campo `entregue_atrasado` é decidido no momento em que o lock do restaurante é obtido durante a confirmação (ponto de linearização) — comparando `agora` com `hora_limite_entrega` ali mesmo, sob lock. A confirmação **nunca é recusada** por estar atrasada (entrega atrasada ainda é uma entrega real). **Prova:** `test_confirmacao_apos_atraso_marca_entregue_atrasado`, `test_status_derivado_do_relogio`; a auditoria confere que `entregue_atrasado` bate com os horários registrados.

### R10 — Alertas repetidos ou perdidos

Monitor e recálculo podem avaliar o mesmo pedido. **Solução:** o "último nível alertado" é gravado **no pedido, sob o lock do restaurante**; só se alerta quando o nível piora. **Prova:** `test_monitor_alerta_uma_vez_por_nivel`.

### R11 — I/O ou trabalho lento dentro da seção crítica

Segurar um lock enquanto espera rede/disco congela todos que precisam dele. **Solução:** HTTP roda no pool, sem lock; o cálculo da hora limite é função pura; `put_nowait` nunca bloqueia; nenhuma `sleep`/I/O com lock. **Consequência:** seções críticas de microssegundos.

### R12 — Sobrecarga (threads e memória sem limite)

**Solução:** pool HTTP **limitado** (32), fila de ingestão **limitada** (1000) com *backpressure* (`503` + `Retry-After`), backlog de `listen` = 1024 (o padrão 5 causa perda de conexões em rajadas), timeout de socket de 15 s (cliente lento não prende worker). **Prova:** `test_fila_cheia_devolve_sobrecarga_e_nao_registra` (a notificação rejeitada **não** fica registrada no índice — senão o retry seria tratado como duplicata e o pedido nunca seria criado).

### R13 — Corrida no desligamento

| t | http (notificar) | main (desligar) |
|---|---|---|
| 1 | vê "aceitando = sim" | |
| 2 | | marca "aceitando = não" e enfileira as pílulas de veneno |
| 3 | enfileira o job **depois** das pílulas ⇒ nenhum worker o processa: **pedido perdido** | |

**Solução:** a flag `_aceitando` é lida e alterada sob o **mesmo** `_notif_lock` que protege o enfileiramento; as pílulas entram depois, e por ser FIFO todo trabalho aceito é processado antes. Ordem de desligamento: para o accept → espera requisições em curso → **drena a ingestão primeiro** → só então o recálculo e o despacho recebem a pílula e drenam o que a ingestão ainda gerou para eles → encerra workers. (Numa versão anterior as três pílulas entravam juntas: a ingestão ainda gerava trabalho para o despacho depois de ele já ter encerrado e centenas de itens ficavam sem processar; ver E11 no doc 05.) **Prova:** `test_desligado_rejeita_e_drena` e `test_desligamento_drena_tambem_o_despacho`.

### R14 — Contadores com atualização perdida

`x += 1` são três passos (ler, somar, gravar). **Solução:** classe `Metricas` com lock.

### R15 — Vazamento de referência mutável

Se a API devolvesse o objeto `Pedido` ou uma lista interna, o `json.dumps` poderia serializá-lo **enquanto** outra thread o altera (`RuntimeError: dictionary changed size during iteration`, ou dados misturados). **Solução:** a API só recebe **cópias** (`dict`) montadas sob lock (`_view_pedido`, `_view_notificacao`). Mesmo motivo para `Alertas.listar` copiar sob lock (iterar um `deque` alterado por outra thread lança erro).

### R16 — Relógio

Horário de parede pode ser ajustado (NTP). **Solução:** datas civis de Brasília (UTC−3 fixo) para regras de SLA e `time.monotonic()` para medições/timeouts.

### R17 — Vaga liberada vai para o pedido errado (inversão de prioridade na fila de espera)

Quando um entregador confirma uma entrega, abre-se uma vaga e vários pedidos esperam por ela. Se a escolha depender da ordem de chegada na fila (ou da ordem arbitrária de um conjunto), a vaga pode ir para um pedido com folga enquanto outro, a poucos minutos de estourar o prazo, continua esperando — justamente o que o sistema existe para evitar. **Solução:** a fila de despacho carrega só um sinal ("pode haver vaga"); o worker olha se há vaga (leitura otimista, sem lock) e, havendo, escolhe o pedido em espera com a **menor hora limite** (`_mais_urgente_em_espera`, sob `_indice_lock`), trava o restaurante dele (L2) e só então decide, sob o lock do entregador (L3), se a vaga ainda existe. Um único sinal preenche todas as vagas abertas. A hora limite é lida sem o L2: um recálculo concorrente pode deixar o ranking levemente defasado, mas a atribuição em si continua sendo decidida sob os locks (R5). **Prova:** `test_vaga_liberada_vai_para_o_pedido_mais_urgente` e `test_varias_vagas_vao_para_os_mais_urgentes_em_ordem`. Os dois falhavam no código anterior (numa execução, a vaga foi para um pedido com prazo 19 min depois do mais urgente).

## 2.4 Hierarquia de locks (regra anti-deadlock)

```
L1  RWLock do trânsito         (leitura: ingestão/recálculo · escrita: janela/auditoria)
 └─ L2  Lock do restaurante    (uma thread segura no máximo UM — exceto a auditoria, em ordem de id)
     └─ L3  Lock do entregador  (dois de uma vez só em ordem de entregador_id; despacho segura no máx. um)
         └─ L4  _indice_lock → _notif_lock  (curtos)
             └─ L5  Alertas, Métricas, Relógio simulado  (folhas)
```

Regra: **só se pode pedir um lock de nível maior do que os que já se tem.** Como toda thread respeita a mesma ordem total, é impossível formar um ciclo de espera. A `auditoria` mostra o caso extremo: ela "congela o mundo" pegando todos os locks — e mesmo assim não trava, porque pega na mesma ordem (L1 escrita → todos os L2 ordenados → todos os L3 ordenados → L4).

Usamos `threading.Lock` (não reentrante) de propósito: se um trecho tentar pegar de novo um lock que já tem, trava de forma visível no teste em vez de esconder um erro de desenho.

## 2.5 Primitivas usadas e por quê

| Primitiva | Onde | Por quê |
|---|---|---|
| `threading.Lock` | restaurante, entregador, índices, métricas, alertas | exclusão mútua simples, seções curtas |
| `threading.Condition` | dentro do `RWLock` | leitores/escritores esperam sem *busy-waiting* |
| `queue.Queue(maxsize)` | ingestão | produtor-consumidor com buffer limitado (mutex + condições `not_empty`/`not_full`) |
| `queue.Queue()` sem limite | recálculo, despacho | eventos internos que nunca devem bloquear quem os gera |
| Pílula de veneno (`None`) | fim dos workers | encerramento ordenado sem matar thread |
| `threading.Event` | monitor | `wait(1.0)` = sono interrompível no desligamento |
| `ThreadPoolExecutor` | HTTP | pool limitado e reutilizável |
| `threading.Barrier` | testes e demos | força as threads a colidirem no mesmo instante |
| Objeto imutável | `Transito` | publicação segura: trocar a referência é atômica |

## 2.6 E o GIL?

O GIL garante que o **interpretador** não se corrompa; ele **não** torna atômica uma sequência de operações do programa. O sistema operacional pode trocar de thread entre o "verificar" e o "agir" (R1) ou entre "rankear" e "atribuir" (R5), e a demonstração mostra dezenas de pedidos duplicados em Python. Todo o código usa locks explícitos, então continua correto no Python sem GIL (3.13t) e seria o mesmo desenho em Java ou Go.

Granularidade: com o GIL, locks mais finos que "por restaurante"/"por entregador" não aumentariam o throughput de CPU; eles importam para reduzir **espera** e, principalmente, definem a **unidade de particionamento** na versão distribuída (restaurante → nó dono).

## 2.7 Estratégia de verificação

1. **Testes de estresse** com `Barrier` (todas as threads colidem ao mesmo tempo) — `tests/test_concorrencia.py`.
2. **Testes de mutação** (`python scripts/mutacoes.py`): injeta, numa cópia do código, 12 bugs de concorrência (dedup fora do lock, locks sem ordem, capacidade fora do lock, lock de leitura do trânsito ou do restaurante esquecido, RWLock sem preferência ao escritor, fila de espera sem urgência, desligamento fora de ordem etc.) e confirma que a suíte **falha** em cada um — prova de que os testes detectam o problema. A primeira rodada mostrou que só os testes de estresse não bastavam para 4 deles; por isso existem os testes de "janela alargada" (`TestJanelasAlargadas`), que forçam a intercalação ruim em vez de torcer para ela acontecer.
3. **Auditoria de invariantes** (`GET /api/v1/auditoria`): congela o sistema e confere 1:1 notificações↔pedidos, agendas, capacidade, vínculos com restaurantes, consistência de `entregue_atrasado` e, quando ocioso, **compara cada pedido em aberto com um recálculo sequencial (oráculo)**.
4. **Teste de carga** (`scripts/carga.py`): 50 notificadores + 4 entregadores + central simultâneos, terminando com a auditoria.
