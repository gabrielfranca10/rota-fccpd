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
| 2 | 21/09/2026 | *(preencher)* | "como que roda o projeto" · "eu vou te mandar os requisitos do projeto, e vc verifica se esta faltando alguma coisa" (com a rubrica da Entrega 1 em imagem) · "rode vc o carga.py e veja se esta tudo certo" · "rode TUDO que tiver que rodar para ver se esta tudo certo" · "tem como deixar esse dashboard mais bonito ai nao mano, ta feioso" · "so falta ajeitar o doc 5 ne" | explicou como executar o projeto; conferiu os docs 01–06 contra a rubrica e apontou o doc 05 incompleto; rodou testes (3 vezes), `carga.py`, `demo_corrida.py`, `demo_deadlock.py`, `demo.py` e um teste de fumaça da API, todos sem falha; redesenhou o dashboard (`static/dashboard.html`, `.css` e `.js`); registrou esta sessão e o erro E8 neste documento | *(preencher)* |

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

## 5.4 Checklist de domínio (cada membro deve conseguir explicar sem olhar)

| Tema | Responsável | Pergunta-teste |
|---|---|---|
| Arquitetura e threads | | Quantas threads existem e o que cada uma faz? |
| Deduplicação (R1) | | Por que verificar e inserir precisam estar na mesma seção crítica? |
| RWLock (R3/R4) | | Por que o worker segura a leitura até gravar o pedido? O que é preferência para escritor? |
| Capacidade do entregador (R5) | | Por que o ranking pode ser feito sem lock, mas a atribuição não? |
| Deadlock (R6) | | Quais são as 4 condições de Coffman e qual quebramos? |
| Fila de espera e despacho | | O que acontece quando todos os entregadores estão cheios? Como um pedido em espera é atendido depois? |
| Protocolo | | Por que 202 e não 201? Por que REST aqui e gRPC depois? |
| Cálculo da hora limite | | Como preparo + distância + pico viram uma hora limite? |
| Verificação | | O que a auditoria confere e o que é o "oráculo sequencial"? |
