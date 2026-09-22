# 4. Protótipo single-node: execução e resultados

> Critério da rubrica: **Single-Node Prototype Execution**

## 4.1 Como executar (Windows, macOS ou Linux)

Requisito único: **Python 3.10 ou superior**. Nenhuma biblioteca externa (nada de `pip install`).
No Windows, troque `python3` por `python`.

```bash
# 1) testes automatizados (50 testes: unidade, estresse e HTTP)
python3 -m unittest discover -s tests -t .

# 2) servidor (terminal 1) — relógio simulado permite "avançar o tempo" na demo
python3 -m rota --relogio-simulado 2026-09-21T11:00

# 3) em outro terminal
python3 scripts/demo_corrida.py     # corrida de deduplicação: sem lock x com lock
python3 scripts/demo_deadlock.py    # redespacho cruzado: trava x não trava
python3 scripts/demo.py             # roteiro guiado (Enter a cada passo)
python3 scripts/carga.py            # teste de carga terminando em auditoria
```

Abra `http://127.0.0.1:8080` no navegador pra ver o dashboard atualizando em tempo real.

Parâmetros úteis do servidor: `--porta`, `--http-workers` (32), `--ingestao-workers` (4),
`--fila` (1000), `--janela-risco` (10 minutos), `--restaurantes` (20). Veja `python3 -m rota -h`.

## 4.2 Resultados obtidos no ambiente de desenvolvimento

> Máquina: Windows 11, Python 3.13. **Os números variam por máquina — rodem no computador de
> vocês antes da apresentação e substituam esta seção pelos seus resultados.**

**Testes automatizados** — 50 testes, todos passando; a suíte foi executada várias vezes seguidas sem
nenhuma falha intermitente. Os 5 testes acrescentados na revisão final (fila de espera por urgência,
desligamento que drena o despacho, instante com `Z`/outro fuso e carimbo dos alertas) foram
escritos **antes** da correção e falhavam no código antigo (ver E9 a E14 no doc 05).

**Testes de mutação** — `python scripts/mutacoes.py` injeta, um por vez e numa cópia do código, os
bugs de concorrência que o projeto diz prevenir, roda a suíte 3 vezes e confere se algum teste falha.
Uma mutação que a suíte não acusa seria um teste fraco. Resultado atual: **as 12 são detectadas.**

| # | Bug injetado | Detectado por |
|---|---|---|
| M1 | Deduplicação verificada **fora** do lock (pausa de 1 ms antes de inserir) | `test_mesma_notificacao_100_threads_gera_um_pedido`, `test_ingestao_em_massa_com_duplicatas`, `test_rajada_de_requisicoes_concorrentes` |
| M2 | Redespacho travando as agendas **sem ordenar** (sem o `sorted`) | `test_redespacho_cruzado_sem_deadlock` (threads presas: deadlock) |
| M3 | Capacidade do entregador checada **fora** do lock (pausa de 0,5 ms) | `test_capacidade_nao_estoura_com_atribuicoes_simultaneas` e mais 3 |
| M3b | Lock do entregador esquecido em `_tentar_atribuir` (sem pausa) | `test_capacidade_nao_estoura_com_atribuicoes_simultaneas` |
| M4 | Trânsito lido **sem** o lock de leitura na ingestão | `test_janela_declarada_no_meio_do_calculo_nao_deixa_pedido_com_transito_velho` |
| M5 | `confirmar_entrega` **sem** o lock do restaurante | `test_confirmar_nao_intercala_com_redespacho`, `test_confirmar_e_redespachar_ao_mesmo_tempo` |
| M6 | RWLock **sem** preferência para o escritor | `test_escritor_nao_passa_fome_com_leitores_sobrepostos` |
| M7 | Fila de espera ignora a urgência | `test_vaga_liberada_vai_para_o_pedido_mais_urgente`, `test_varias_vagas_...` |
| M8 | Pílulas do despacho enviadas antes de a ingestão terminar | `test_desligamento_drena_tambem_o_despacho` |
| M9 | Entrega confirmada não libera a vaga do entregador | 8 testes, entre eles `test_confirmacao_de_entrega` |
| M10 | Capacidade do redespacho não é conferida | `test_redespacho_respeita_capacidade` |
| M11 | Fila cheia bloqueia em vez de devolver 503 | suíte trava (timeout): o teste `test_fila_cheia_devolve_sobrecarga_e_nao_registra` nunca termina |

Dois achados que só apareceram por causa desse teste (E1 e E15 no doc 05):

* A primeira versão do teste de deadlock usava só **1 restaurante** para todos os pedidos, e a mutação
  M2 **não era detectada**: o lock do restaurante (L2), sozinho, já serializava todo mundo antes de
  chegar nos locks de entregador (L3), escondendo a corrida que a ordenação deveria resolver.
  Corrigido espalhando os pedidos em **8 restaurantes diferentes**.
* Na primeira rodada completa, **M3b, M4, M5 e M6 não eram detectadas**: os testes de estresse dependiam
  de a troca de thread cair por acaso no meio do "verificar-e-agir", o que quase nunca acontece sob o
  GIL. Foram acrescentados os testes de "janela alargada" (`TestJanelasAlargadas`), que forçam a
  intercalação ruim de propósito, e um de starvation do escritor.

**Demonstrações**

```
$ python3 scripts/demo_corrida.py
Mesma notificação recebida por 50 threads simultâneas. Pedidos criados (esperado: 1)
  sem sincronização (padrão ingênuo) : 50   <- pedidos duplicados na agenda do entregador
  rota (Nucleo real, com lock)       : 1

$ python3 scripts/demo_deadlock.py
1) Cada thread trava primeiro a agenda de ORIGEM (espera circular):
    ent-marcia->ent-joao: TRAVOU esperando ent-joao (deadlock)
    ent-joao->ent-marcia: ok
2) rota: sempre trava em ordem alfabética de entregador_id (sem espera circular):
    ent-joao->ent-marcia: ok
    ent-marcia->ent-joao: ok
```

O número da primeira linha varia a cada execução (entre ~35 e 50 nas nossas); a segunda é sempre 1.
A linha "rota" chama o `Nucleo.receber_notificacao` de verdade. Já o deadlock é demonstrado com locks
didáticos, porque o núcleo real está correto e não trava: quem prova que a ordenação é necessária é a
mutação M2.

Roteiro guiado (`scripts/demo.py`), resumido:

```
1. notificação do iFood        -> HTTP 202; limite 11:38, NO_PRAZO, 38 min restantes, ent-joao
2. mesma notificação de novo   -> HTTP 200, mesmo id, duplicatas_recebidas = 1
3. pico de trânsito 11h-12h    -> trânsito v2; limite recalculado para 11:58
4. relógio +25 minutos         -> ainda NO_PRAZO (33 min restantes); alertas TRANSITO_ATUALIZADO
                                   e PEDIDO_RECALCULADO
5. redespacho (moto quebrou)   -> responsável ent-joao -> ent-marcia
6. confirmação de entrega      -> ENTREGUE às 11:25, entregue_atrasado = False
7. auditoria                   -> ok: true, oráculo executado
```

Conferência manual do passo 1: notificação às 11:00, preparo de 18 min → pronto às 11:18;
distância 6 km a 18 km/h → trajeto de 20 min → limite às 11:38. Bate com o valor devolvido.

**Teste de carga** (`scripts/carga.py`, padrão: 50 clientes enviando 5 000 notificações — das quais
cerca de 3 700 distintas —, 4 entregadores confirmando e redespachando, e a central declarando 3
janelas de trânsito no meio da rajada, contra um servidor recém-iniciado):

```
requisições: 5406 em 13.19 s  ->  410 req/s
operação          qtd   p50 ms   p95 ms   p99 ms   máx ms
confirmar           8    103.2    116.4    118.2    118.6
declarar_janela      3    145.4    175.2    177.9    178.6
listar            392    131.9    167.7    195.8    222.4
notificar        5000    129.9    167.6    201.9    230.7
redespachar         3    100.3    109.0    109.7    109.9

respostas por (operação, status HTTP):
  confirmar     200 8          declarar_janela 202 3
  listar        200 392        notificar 200 1284 | 202 3716
  redespachar   200 1 | 409 2

auditoria: ok = true, violações = 0, oráculo executado, trânsito v4,
           3716 notificações -> 3716 pedidos (1:1), 3693 aguardando entregador
RESULTADO: OK — nenhuma falha e todas as invariantes preservadas
```

Antes da revisão final (E10 no doc 05) o mesmo teste dava ~213 req/s e `notificar` com p50 de ~256 ms.
A explicação mais provável, pela leitura do código (não medimos com profiler): cada pedido sem vaga fazia
o worker de despacho travar o restaurante e tentar os 4 entregadores mesmo com todos cheios, disputando
CPU e locks com a ingestão. Agora o despacho olha primeiro se existe vaga e só então procura o pedido
mais urgente.

Como ler: **nenhum 5xx e nenhum erro de conexão**; cada notificação distinta gerou exatamente um
pedido; depois de 3 mudanças de trânsito no meio da carga, **todos** os pedidos em aberto batem com
um recálculo sequencial. Os poucos `409` do redespacho são esperados: o "entregador destino" já
estava na capacidade máxima quando a requisição chegou — o sistema detectou e recusou, em vez de
estourar a capacidade. Os **3 693 pedidos aguardando entregador** também são esperados e revelam
uma característica real do domínio: a frota de 4 entregadores (capacidade total 15) não acompanha
uma rajada de milhares de pedidos — no mundo real, isso é sinal de que a central precisa escalar a
frota, exatamente o tipo de decisão operacional que este painel deveria expor.

## 4.3 Dashboard ao vivo (capturas)

Capturas do dashboard (`http://127.0.0.1:8080`) em três momentos, com o relógio simulado avançado para
mostrar os estados de prazo. O painel só lê a API (`/api/v1/metricas`, `/pedidos`, `/entregadores`,
`/alertas`, `/auditoria`); nada nele altera o estado do núcleo.

**Operação normal** (49 pedidos de uma carga reduzida; 2 atrasados, 5 em risco, 28 no prazo e 14 entregues):

![Visão geral do dashboard](img/dashboard-visao-geral.png)

**Sob a carga completa** (`scripts/carga.py`): 1 000 pedidos na tela (o painel lê no máximo os 1 000
primeiros por hora limite), 3 694 aguardando entregador e os quatro entregadores no limite de capacidade:

![Dashboard sob carga](img/dashboard-sob-carga.png)

**Tela estreita:**

<img src="img/dashboard-celular.png" alt="Dashboard em tela estreita" width="320">

## 4.4 O sistema desacelera com o volume? (medido)

Duas medições, porque a pergunta tem duas respostas.

**O núcleo (sem HTTP).** 8 threads enviam lotes de 10 000 notificações **distintas** (o estado só cresce),
4 workers de ingestão, Windows 11 e Python 3.13. Depois de cada lote medimos o custo de cada operação:

| pedidos no sistema | ingestão (notif/s) | monitor (1 volta) | listar 1 000 | estatísticas | auditoria |
|---:|---:|---:|---:|---:|---:|
| 10 000 | 5 828 | 20 ms | 55 ms | 3 ms | 503 ms |
| 40 000 | 3 967 | 86 ms | 265 ms | 11 ms | 2 321 ms |
| 80 000 | 5 712 | 220 ms | 517 ms | 23 ms | 4 692 ms |

* **A ingestão não desacelera**: fica entre ~4 000 e ~5 800 notificações/s de 10 mil a 80 mil pedidos
  (a oscilação é ruído da máquina, não tendência).
* **O que cresce é o que percorre o estado inteiro**: a volta do monitor (1 por segundo), a listagem
  do dashboard, as estatísticas e a auditoria têm custo **linear** no número de pedidos. Na escala da
  demonstração (alguns milhares de pedidos) são dezenas de milissegundos; a auditoria "congela o
  mundo" de propósito e só roda sob demanda.
* Caminho para tirar o custo linear (fora desta entrega): fila de prazos ordenada (heap) para o monitor
  só visitar quem está perto de mudar de nível, índice ordenado para a listagem e contadores
  incrementais para as estatísticas.

**Por HTTP no Windows.** O `req/s` da carga **varia muito entre execuções** (604, 267 e 288 req/s em
três rodadas seguidas, com o mesmo servidor e o mesmo código). Não é o servidor: cada requisição abre
uma conexão nova (HTTP/1.0, escolha do doc 03) e, depois de milhares de execuções seguidas, o Windows
fica com 9 a 17 mil sockets em `TIME_WAIT` e o cliente quase esgota as portas efêmeras. Na demonstração,
rodem a carga **uma vez**, com o servidor recém-iniciado; repetir em sequência faz o `req/s` cair.

## 4.5 Limitações conhecidas (e em que entrega serão tratadas)

| Limitação | Por quê é aceitável agora | Plano |
|---|---|---|
| Estado só em memória | a entrega pede protótipo de concorrência local | persistência + fila durável (Entrega 3) |
| `http.server` da biblioteca padrão | deixa o modelo de threads explícito | gRPC entre serviços (Entrega 2) |
| Sem autenticação | fora do escopo de concorrência | gateway/BFF com autenticação |
| Cálculo de trânsito simplificado (velocidade constante + fator de pico/bloqueio) | foco da disciplina é concorrência | integração com serviço de mapas real |
| Notificações e alertas crescem sem limite de tempo | volume do protótipo é pequeno | retenção/arquivamento |
| Monitor, listagem, estatísticas e auditoria percorrem todo o estado (custo linear; ver 4.4) | na escala da demo custam dezenas de ms | heap de prazos, índice ordenado e contadores incrementais |
| Frota pequena por padrão (4 entregadores) faz a maioria dos pedidos ficar "aguardando" sob carga alta | evidencia o comportamento real do sistema sob escassez de recurso, que é justamente o que a disciplina quer expor | `--restaurantes`/seed configuráveis; dimensionamento de frota fica para um estudo de capacidade futuro |
