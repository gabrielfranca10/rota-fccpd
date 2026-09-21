# 4. Protótipo single-node: execução e resultados

> Critério da rubrica: **Single-Node Prototype Execution**

## 4.1 Como executar (Windows, macOS ou Linux)

Requisito único: **Python 3.10 ou superior**. Nenhuma biblioteca externa (nada de `pip install`).
No Windows, troque `python3` por `python`.

```bash
# 1) testes automatizados (37 testes: unidade, estresse e HTTP)
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

**Testes automatizados** — 37 testes, todos passando; a suíte foi executada 6 vezes seguidas sem
nenhuma falha intermitente (uma sequência de 5 rodadas limpas após a suíte estabilizar, mais a
rodada final de conferência).

**Testes de mutação** — introduzimos os bugs de propósito no `rota/nucleo.py`, rodamos os testes,
confirmamos que **falham**, e só então revertemos:

| Bug injetado | Resultado (3 execuções) |
|---|---|
| Deduplicação verificando a impressão digital **fora** do lock, com uma pausa de 1 ms antes de reentrar para inserir | `test_mesma_notificacao_100_threads_gera_um_pedido` falhou nas 3 vezes: **23, 17 e 22** notificações "novas" em vez de 1 |
| Redespacho travando a agenda de origem **sem ordenar** (removendo o `sorted(...)`) | `test_redespacho_cruzado_sem_deadlock` falhou nas 3 vezes com **"16 threads presas após 20 s (provável deadlock)"** |

Achado interessante durante a preparação deste teste: a primeira versão do teste de deadlock usava
só **1 restaurante** pra todos os pedidos — e a mutação **não era detectada**, porque o lock do
restaurante (L2), sozinho, já serializava todo mundo antes de chegar nos locks de entregador (L3),
escondendo a corrida que a ordenação deveria resolver. Corrigido espalhando os pedidos em **8
restaurantes diferentes** (precisa de recursos independentes
concorrendo de verdade para a corrida aparecer). Ver E1 no doc 05.

**Demonstrações**

```
$ python3 scripts/demo_corrida.py
Mesma notificação recebida por 50 threads simultâneas. Pedidos criados (esperado: 1)
  sem sincronização : 39   <- pedidos duplicados na agenda do entregador
  rota (com lock)   : 1

$ python3 scripts/demo_deadlock.py
1) Cada thread trava primeiro a agenda de ORIGEM (espera circular):
    ent-marcia->ent-joao: TRAVOU esperando ent-joao (deadlock)
    ent-joao->ent-marcia: ok
2) rota: sempre trava em ordem alfabética de entregador_id (sem espera circular):
    ent-joao->ent-marcia: ok
    ent-marcia->ent-joao: ok
```

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
requisições: 5404 em 25.39 s  ->  213 req/s
operação          qtd   p50 ms   p95 ms   p99 ms   máx ms
confirmar           3     70.4    183.9    194.0    196.6
declarar_janela      3    241.0    260.2    261.9    262.4
listar            393    264.4    374.3    395.3    492.5
notificar        5000    256.2    369.0    390.5    604.6
redespachar         5     75.1    298.4    324.5    331.0

respostas por (operação, status HTTP):
  confirmar     200 3          declarar_janela 202 3
  listar        200 393        notificar 200 1284 | 202 3716
  redespachar   200 2 | 409 3

auditoria: ok = true, violações = 0, oráculo executado, trânsito v4,
           3716 notificações -> 3716 pedidos (1:1), 3698 aguardando entregador
RESULTADO: OK — nenhuma falha e todas as invariantes preservadas
```

Como ler: **nenhum 5xx e nenhum erro de conexão**; cada notificação distinta gerou exatamente um
pedido; depois de 3 mudanças de trânsito no meio da carga, **todos** os pedidos em aberto batem com
um recálculo sequencial. Os poucos `409` do redespacho são esperados: o "entregador destino" já
estava na capacidade máxima quando a requisição chegou — o sistema detectou e recusou, em vez de
estourar a capacidade. Os **3 698 pedidos aguardando entregador** também são esperados e revelam
uma característica real do domínio: a frota de 4 entregadores (capacidade total 15) não acompanha
uma rajada de milhares de pedidos — no mundo real, isso é sinal de que a central precisa escalar a
frota, exatamente o tipo de decisão operacional que este painel deveria expor.

## 4.3 Dashboard ao vivo (capturas)

Capturas do dashboard (`http://127.0.0.1:8080`) em três momentos, com o relógio simulado avançado para
mostrar os estados de prazo. O painel só lê a API (`/api/v1/metricas`, `/pedidos`, `/entregadores`,
`/alertas`, `/auditoria`); nada nele altera o estado do núcleo.

**Operação normal** (49 pedidos de uma carga reduzida; 2 atrasados, 5 em risco, 30 no prazo e 12 entregues):

![Visão geral do dashboard](img/dashboard-visao-geral.png)

**Sob a carga completa** (`scripts/carga.py`): 1 000 pedidos na tela (o painel lê no máximo os 1 000
primeiros por hora limite), 3 697 aguardando entregador e os quatro entregadores no limite de capacidade:

![Dashboard sob carga](img/dashboard-sob-carga.png)

**Tela estreita:**

<img src="img/dashboard-celular.png" alt="Dashboard em tela estreita" width="320">

## 4.4 Limitações conhecidas (e em que entrega serão tratadas)

| Limitação | Por quê é aceitável agora | Plano |
|---|---|---|
| Estado só em memória | a entrega pede protótipo de concorrência local | persistência + fila durável (Entrega 3) |
| `http.server` da biblioteca padrão | deixa o modelo de threads explícito | gRPC entre serviços (Entrega 2) |
| Sem autenticação | fora do escopo de concorrência | gateway/BFF com autenticação |
| Cálculo de trânsito simplificado (velocidade constante + fator de pico/bloqueio) | foco da disciplina é concorrência | integração com serviço de mapas real |
| Notificações e alertas crescem sem limite de tempo | volume do protótipo é pequeno | retenção/arquivamento |
| Frota pequena por padrão (4 entregadores) faz a maioria dos pedidos ficar "aguardando" sob carga alta | evidencia o comportamento real do sistema sob escassez de recurso, que é justamente o que a disciplina quer expor | `--restaurantes`/seed configuráveis; dimensionamento de frota fica para um estudo de capacidade futuro |
