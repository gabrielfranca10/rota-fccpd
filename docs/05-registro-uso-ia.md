# 5. Registro de uso de IA

> Critério da rubrica: **Artificial Intelligence Usage and Documentation**
> Regra da disciplina: *a IA é copiloto, não substituta — a equipe deve dominar e explicar qualquer trecho do projeto.*

**Ferramenta:** Claude (Anthropic), via Claude Code, com execução de código real (testes, servidor,
scripts) no ambiente da equipe — não só geração de texto.

> ⚠️ **A equipe precisa completar este documento com honestidade antes de entregar.** As colunas
> "Decisão da equipe" e "Justificativa da equipe" e o texto literal dos prompts **só podem ser
> preenchidos por vocês** — são exatamente o que a rubrica avalia.

## 5.1 Sessões

| # | Data | Quem | Prompt (colar o texto literal) | O que a IA produziu | O que a equipe revisou/alterou |
|---|---|---|---|---|---|
| 1 | 21/09/2026 | Gabriel França | *(colar)* — pedido: gerar um projeto de tema livre com foco em Computação Paralela, seguindo a rubrica da Entrega 1; construir peça por peça e testar tudo ao final | arquitetura, código, testes, scripts, dashboard e documentação desta entrega, a partir do domínio de despacho de pedidos de delivery | *(preencher)* |
| 2 | 21/09/2026 | *(preencher)* | *ver a lista 5.1.1 (22 prompts, na ordem em que foram enviados)* | explicou como executar o projeto; conferiu os docs 01–06 contra a rubrica e apontou o doc 05 incompleto; rodou testes (3 vezes), `carga.py`, `demo_corrida.py`, `demo_deadlock.py`, `demo.py` e um teste de fumaça da API, todos sem falha; redesenhou o dashboard (`static/dashboard.html`, `.css` e `.js`); registrou esta sessão e o erro E8 neste documento; configurou o CI e gerou os screenshots; revisou o código do núcleo e da API, encontrou seis defeitos (E9 a E14), escreveu os testes antes da correção e corrigiu, atualizando os docs 01 a 04; depois auditou os próprios testes com testes de mutação, achou quatro testes fracos e quatro problemas nos scripts (E15 a E18) e os corrigiu; por fim mediu se o sistema desacelera com o volume (núcleo sem HTTP e por HTTP) e registrou o resultado no doc 04, seção 4.4 | *(preencher)* |

### 5.1.1 Prompts da sessão 2, na ordem em que foram enviados

Texto literal das mensagens do usuário (com os erros de digitação originais) e o que cada uma gerou.
A mensagem só com `]` (digitada sem querer) ficou de fora. As mensagens 14, 15 e 16 estão resumidas
porque incluem endereços de repositórios e instruções sobre autoria de commits.

| # | Prompt | O que a IA fez com ele |
|---|---|---|
| 1 | "opa, como que roda o projeto" | leu o README e explicou os comandos (testes, servidor, carga) |
| 2 | "eu vou te mandar os requisitos do projeto, e vc verifica se esta faltando alguma coisa ok" | combinou o procedimento |
| 3 | (7 imagens da rubrica) "aqui estao os requisitos, veja se esta tudo certo" | leu os docs 01 a 06, rodou os testes e comparou com a rubrica: apontou o doc 05 incompleto, os números do doc 04 e o ensaio |
| 4 | "rode vc o carga.py e veja se esta tudo certo" | subiu o servidor, rodou a carga: auditoria `ok`, 175 req/s |
| 5 | "rode TUDO que tiver que rodar para ver se esta tudo cefto" | testes 3 vezes, `demo_corrida`, `demo_deadlock`, `demo.py` e teste de fumaça da API: sem falhas |
| 6 | "como que roda o projeto mesmo" | repetiu os comandos, em dois terminais |
| 7 | "tem como deixar esse dashboard mais bonito ai nao mano, ta feioso" | primeira reformulação do dashboard (tema escuro) |
| 8 | "so falta ajeitar o doc 5 ne" | explicou o que só a equipe pode preencher e ofereceu registrar a sessão |
| 9 | "quero por favor" | registrou a sessão 2 e o erro E8; listou as perguntas D1 a D13 |
| 10 | "divida essas perguntas para gabriel caio fernando" | dividiu as perguntas pelos blocos de fala do doc 06 |
| 11 | (imagem de outro painel) "voce pode fazer um dashboard nesse estilo? eu quero um dashboard muito bonito" | segunda reformulação do dashboard (tema claro, menu lateral, rosca de status) e screenshots |
| 12 | "o codigo tem certeza que pode ser em python?" | disse que a rubrica não cita linguagem, recomendou confirmar com o professor e apontou uma frase não verificada no doc 01 |
| 13 | "se o codigo tiver q ser em java, vc refaz tudo ne? mas sem perder nada" | descreveu como seria portar para Java (não executado: o professor aceitou Python) |
| 14 | (resumo) pediu para ler o repositório de outra equipe, separar o que é de Requisitos e de Computação Paralela e dizer o que faltava | leu o repositório para comparação (nada foi copiado); concluiu que o painel de admin é só de Requisitos |
| 15 | (resumo) "eu vou criar o repositorio aqui e voce conecta ok" | verificou git e credenciais e pediu o endereço |
| 16 | (resumo) URL do repositório e instrução de que os commits saiam somente com a autoria do usuário | `git init` só na pasta do projeto, `.gitignore` e commits sem nenhuma atribuição à IA |
| 17 | "pode subir assim, sem problemas" | `git push`; conferiu o remoto |
| 18 | "faz o CI e os screenshots pfv" | workflow do GitHub Actions (testes em 3.10 e 3.13, demos e carga reduzida) e três capturas do dashboard |
| 19 | "foi sem qrer, eu queria perguntar se tirando a aprte dos docs, tem mais alguma coisa que a gnt ta esquecendo? eu quero o codigo perfeito" | revisão do código: seis defeitos (E9 a E14), testes escritos antes da correção |
| 20 | "o professor ja confirmou que pode fazer em python, mas eu to falando se ta faltando ALGUM requisito entendeu, e se tem algum erro nos testes, ou em alguma parte do codigo tambem" | testes de mutação: quatro testes fracos e quatro problemas nos scripts (E15 a E18) |
| 21 | (imagem do critério "Single-Node Prototype Execution / Exceeding") "." | mediu se o sistema desacelera com o volume: doc 04, seção 4.4 |
| 22 | (imagem do critério "AI Usage / Exceeding") "e esse aqui" | esta lista e a coluna "Onde no código" da seção 5.4 |

O prompt da **sessão 1** (que gerou o projeto) não está registrado aqui: a equipe precisa colar o texto
original na tabela acima.

## 5.2 Decisões propostas pela IA

Para cada linha: marquem **Aceita / Rejeitada / Modificada** e escrevam **por quê com as palavras de
vocês**. Se rejeitarem algo, alterem o código e registrem aqui.

| # | Proposta da IA | Alternativas que a IA descartou | Justificativa dada pela IA | Decisão da equipe | Justificativa da equipe |
|---|---|---|---|---|---|
| D1 | Domínio = despacho de pedidos de delivery ("Rota") | central de emergência, monitoramento IoT, motor de leilão | rico em concorrência (rajada, dedup, recálculo, recurso limitado), tema relatável e fácil de apresentar | | |
| D2 | Python + biblioteca padrão | Go, Java, Flask/FastAPI | todos dominam; sem instalação; modelo de threads visível | | |
| D3 | Threads | asyncio, multiprocessing | expõe locks/deadlocks, tema da disciplina | | |
| D4 | Capacidade por entregador + fila de espera com redespacho automático | atribuição manual sempre; fila global sem limite por entregador | modela um recurso físico real sem exigir intervenção humana no caso comum; cria um risco de concorrência específico do domínio (R5 no doc 02) | | |
| D5 | Trânsito simulado minuto a minuto (pico reduz velocidade, bloqueio zera) | binário "conta/não conta" como no calendário forense original | modela um domínio de SLA contínuo (minutos, não dias úteis) de forma realista sem precisar de um roteirizador de verdade | | |
| D6 | Confirmação de entrega nunca é recusada por atraso (`entregue_atrasado` como campo, não erro) | recusar confirmação após a hora limite | no mundo real uma entrega atrasada ainda é uma entrega; recusar o registro esconderia o atraso em vez de medi-lo | | |
| D7 | Deduplicação por impressão digital do conteúdo (plataforma + número + hora + descrição) | id da fonte/webhook | o mesmo evento pode chegar duas vezes num retry do agregador, com ids de entrega diferentes | | |
| D8 | Lock por restaurante (não por pedido) | lock global; lock por pedido | paralelismo entre restaurantes sem complicar invariantes | | |
| D9 | Ordem de locks por `entregador_id` no redespacho | `tryLock` + retry | elimina espera circular sem risco de livelock | | |
| D10 | Trânsito imutável + RWLock com preferência a escritor | lock comum; copiar sem versão | leitores em paralelo, sem starvation, com versão rastreável | | |
| D11 | Status do pedido derivado do relógio | thread que marca ATRASADO | elimina a corrida monitor × confirmação | | |
| D12 | Auditoria com oráculo sequencial + checagem de capacidade | só testes unitários | prova de correção sob carga real, inclusive da invariante nova (capacidade) | | |
| D13 | Dashboard estático (HTML/CSS/JS) servido pelo próprio `http_api.py`, sem framework novo | Flask + Jinja; app separado em Node | zero dependência nova; reaproveita o servidor e o pool já existentes | | |

## 5.3 Erros encontrados e corrigidos durante a revisão (registro real desta sessão)

| # | Problema | Como apareceu | Correção |
|---|---|---|---|
| E1 | Teste de deadlock do redespacho **não detectava** a mutação (lock sem ordenar) | ao testar a própria suíte de mutação: com só 1 restaurante, o lock do restaurante (L2) já serializava tudo antes de chegar nos locks de entregador, escondendo a corrida que a ordenação deveria resolver | pedidos do teste espalhados em 8 restaurantes diferentes (locks L2 independentes); a mutação passou a ser detectada em 3 de 3 execuções |
| E2 | `Alertas.publicar("TRANSITO_ATUALIZADO", tipo=tipo, ...)` — `TypeError: got multiple values for argument 'tipo'` | execução manual de `declarar_janela` logo após escrever o núcleo | parâmetro renomeado para `tipo_janela` na chamada (o primeiro `tipo` já é o nome do evento) |
| E3 | Helper de teste `notif(descricao="")` não conseguia testar descrição vazia | `test_validacoes` falhou: caso "descrição vazia" não levantava `ErroValidacao` | o helper usava `descricao or texto_padrao`; string vazia é *falsy* em Python e caía no padrão. Trocado por checagem explícita `is None` |
| E4 | Script de carga quase não exercitava `confirmar`/`redespachar` | métricas da carga mostravam 0 chamadas nessas operações | thread de entregador filtrava pedidos `EM_RISCO` (estado raro logo após a criação); trocado para `NO_PRAZO` (estado inicial, disponível desde o primeiro pedido) |
| E5 | `python scripts/carga.py` deu "servidor não respondeu em /health" | usuário rodou sem o servidor de pé em outro terminal | não era bug — reforçado no doc 04 que são **dois** terminais (servidor + carga) |
| E6 | Demo interativa quebrava com `UnicodeEncodeError` no console do Windows | execução real de `scripts/demo.py` no PowerShell (codepage `cp1252`) | `sys.stdout.reconfigure(encoding="utf-8")` no início do script |
| E7 | Capacidade de entregador aceitando valores absurdos nos primeiros rascunhos de teste (`capacidade: 50`) | `cadastrar_entregador` rejeitou com `ErroValidacao` (limite real é 1–10) | não era bug do núcleo — a validação estava certa; os testes foram ajustados para usar valores dentro do limite |
| E8 | Ao limpar servidores `rota` esquecidos na porta 8080 durante a sessão 2, a IA encerrou **todos** os processos que escutavam nela, inclusive `wslrelay` (WSL) e `com.docker.backend` (Docker Desktop), que não eram do projeto | a IA listou os donos da porta 8080 e os finalizou sem checar o nome de cada um | a IA avisou a equipe na hora; Docker Desktop e WSL precisam ser reabertos se estiverem em uso. Depois disso, só processos `python` são encerrados. Nenhum arquivo do projeto foi afetado |
| E9 | A vaga liberada por uma entrega ia para um pedido qualquer da fila de espera, não para o mais urgente (`list(self._aguardando)[:3]`: ordem arbitrária de um conjunto) | revisão do código + reprodução: com 30 pedidos esperando, a vaga foi para um com prazo 19 min depois do mais urgente | o despacho passou a escolher o pedido em espera de menor hora limite (`_mais_urgente_em_espera`); a fila de despacho virou um sinal. Testes `test_vaga_liberada_vai_para_o_pedido_mais_urgente` e `test_varias_vagas_...` (falhavam antes). Risco R17 no doc 02 |
| E10 | Cada pedido sem vaga fazia o worker de despacho travar o restaurante e tentar os 4 entregadores, mesmo com todos cheios | leitura do código; efeito medido no `carga.py`: ~213 req/s e p50 de ~256 ms em `notificar` | o despacho olha antes se existe vaga (leitura otimista, sem lock) e só então procura o pedido. Mesma carga depois: 410 req/s e p50 de ~130 ms. Não medimos com profiler; a causa é a explicação provável |
| E11 | O desligamento enfileirava as pílulas do despacho e do recálculo junto com as da ingestão; a ingestão ainda gerava trabalho para o despacho depois de ele ter encerrado, contradizendo a promessa "drena as três filas" do doc 02 (R13) | reprodução: 1 000 notificações e `parar()`; em 5 rodadas ficaram 169 a 831 itens sem processar | `parar()` espera a ingestão terminar antes de enviar as pílulas do recálculo e do despacho. Teste `test_desligamento_drena_tambem_o_despacho` (falhava antes) |
| E12 | Os alertas eram carimbados com o horário de parede (sem fuso) e não com o relógio do sistema | visto nos screenshots do dashboard: alertas às 19:26 com o relógio simulado em 12:25; reprodução: carimbo 20:02 contra 11:00 | `Alertas` recebe o relógio injetado e carimba com ele (lido antes do lock, porque Alertas e Relogio são folhas). Teste `test_alerta_e_carimbado_com_o_relogio_do_sistema` |
| E13 | Instante com `Z` (UTC, comum em webhook) era rejeitado no Python 3.10 (`fromisoformat` só aceita `Z` do 3.11 em diante), e o mesmo instante em fusos diferentes gerava notificações diferentes | revisão do código: o README promete Python 3.10+. Não reproduzimos no 3.10 localmente; o job 3.10 do CI exercita o teste | `_parse_datetime` trata `Z` e converte todo instante para o horário de Brasília. Teste `test_instante_com_z_ou_outro_fuso_e_o_mesmo_evento` |
| E14 | `PUT`, `PATCH`, `DELETE` e `OPTIONS` recebiam `501` com uma página HTML da biblioteca padrão, e não o `405` em JSON que o doc 03 promete | reprodução com `http.client` | handlers desses métodos passam pelo mesmo despachante e o corpo pendente é descartado antes do erro (evita RST no Windows). Casos acrescentados a `test_erros` |
| E15 | **A suíte não detectava 4 dos bugs que o doc 02 dizia prevenir**: lock de leitura do trânsito esquecido, lock do restaurante esquecido na confirmação, lock do entregador esquecido na atribuição e RWLock sem preferência ao escritor. Os testes de estresse dependiam de a troca de thread cair por acaso no meio do "verificar-e-agir", o que quase nunca acontece sob o GIL; e o teste do RWLock provava exclusão, não a preferência ao escritor | teste de mutação rodado sobre uma cópia do código (`scripts/mutacoes.py`): 4 mutações "NÃO DETECTADAS" em 3 rodadas | `disparar()` passou a trocar de thread a cada ~1 µs; nova classe `TestJanelasAlargadas` força a intercalação ruim de propósito (cálculo segurado 0,3 s, confirmação congelada, `len` da agenda lento); novo teste de starvation do escritor. As 12 mutações passaram a ser detectadas |
| E16 | `demo_corrida.py` mostrava "rota (com lock)", mas essa linha rodava uma **cópia didática** do padrão, não o núcleo | releitura do script | a linha do rota passou a chamar o `Nucleo.receber_notificacao` real com 50 threads e contar os pedidos criados (1). O padrão ingênuo continua como exemplo do bug e está identificado como tal |
| E17 | `scripts/carga.py` só reprovava resposta 5xx: um 400 (corpo inválido) ou outro status inesperado passaria com "OK" | leitura do script | tabela de status esperados por operação (409 em confirmar e redespachar, 503 em notificar); qualquer outro reprova, inclusive no CI |
| E18 | O teste HTTP do relógio simulado avançava o relógio do núcleo **compartilhado** por todos os testes da classe; só a ordem alfabética escondia o efeito. Faltavam também testes do cálculo de trânsito para pico cobrindo o trajeto, bloqueio no meio da viagem e janela inclusiva | leitura dos testes | `TestHttpRelogio` com núcleo próprio (mais o caso do relógio real, que responde 409); 3 testes novos em `test_transito.py`, com os valores conferidos à mão |

## 5.4 Checklist de domínio (cada membro deve conseguir explicar sem olhar)

Cada responsável abre o código indicado, lê, e escreve na última coluna, **com as próprias palavras e sem
copiar dos docs**, duas ou três frases respondendo à pergunta-teste. É essa coluna que mostra que a
equipe entende o trecho, e não só que o código funciona.

| Tema | Onde no código | Responsável | Pergunta-teste | Explicação com as próprias palavras |
|---|---|---|---|---|
| Arquitetura e threads | `rota/__main__.py`, `Nucleo.iniciar`, `ServidorComPool` em `http_api.py` | | Quantas threads existem e o que cada uma faz? | |
| Deduplicação (R1) | `Nucleo.receber_notificacao`, `impressao_digital` | | Por que verificar e inserir precisam estar na mesma seção crítica? | |
| RWLock (R3/R4) | `rota/rwlock.py`, `Nucleo._processar`, `Nucleo.declarar_janela` | | Por que o worker segura a leitura até gravar o pedido? O que é preferência para escritor? | |
| Capacidade do entregador (R5) | `Nucleo._tentar_atribuir` | | Por que o ranking pode ser feito sem lock, mas a atribuição não? | |
| Deadlock (R6) | `Nucleo.redespachar_pedido` | | Quais são as 4 condições de Coffman e qual quebramos? | |
| Fila de espera e despacho | `Nucleo._tentar_despachar`, `_mais_urgente_em_espera`, `_acordar_fila_espera` | | O que acontece quando todos os entregadores estão cheios? Como um pedido em espera é atendido depois? | |
| Protocolo | rotas em `rota/http_api.py`, doc 03 | | Por que 202 e não 201? Por que REST aqui e gRPC depois? | |
| Cálculo da hora limite | `calcular_hora_limite` em `rota/transito.py` | | Como preparo + distância + pico viram uma hora limite? | |
| Verificação | `Nucleo.auditoria`, `tests/test_concorrencia.py`, `scripts/mutacoes.py` | | O que a auditoria confere e o que é o "oráculo sequencial"? Por que os testes de mutação importam? | |
