# 5. Registro de uso de IA

## 5.1 Registro individual por integrante

**Projeto:** Rota — Núcleo de Despacho de Pedidos  
**Disciplina:** Fundamentos de Computação Concorrente, Paralela e Distribuída — CESAR School  
**Equipe:** Gabriel França · Caio Leimig · Fernando Soares · Ramsés Cordeiro  

Durante o desenvolvimento do projeto **Rota**, ferramentas de Inteligência Artificial generativa foram utilizadas como apoio para compreender problemas de concorrência, discutir decisões de arquitetura, revisar regras do domínio, analisar riscos de sincronização, estruturar testes e apoiar a documentação técnica. A IA foi utilizada como copiloto: as decisões de projeto, integração entre os módulos, execução dos testes e validação final do comportamento ficaram sob responsabilidade da equipe.

A divisão abaixo segue as áreas de responsabilidade adotadas pela equipe no projeto e na apresentação. Como o código foi integrado em um único protótipo, existem pontos de contato entre as partes; por isso, a separação representa principalmente o foco de estudo, implementação, revisão e defesa de cada integrante.

### Gabriel França

Durante o desenvolvimento do Rota, fiquei responsável principalmente pela **definição do problema, escopo, regras de negócio do despacho e entendimento do fluxo principal do sistema**. Meu foco foi compreender como uma central de delivery poderia receber pedidos vindos de várias plataformas, transformar notificações em pedidos, calcular o prazo de entrega e acompanhar o estado desses pedidos sem perder as regras do domínio.

Utilizei a IA inicialmente para discutir o recorte do projeto e verificar se o tema possuía problemas reais de concorrência suficientes para a disciplina. A partir disso, trabalhei na definição das entidades principais — restaurante, entregador, notificação e pedido — e nas regras relacionadas a deduplicação, capacidade dos entregadores, fila de espera, confirmação de entrega, atraso e recálculo após mudanças no trânsito.

Também utilizei a IA para entender e revisar o cálculo da **hora limite de entrega**, que considera tempo de preparo, distância, prioridade do pedido e condições de trânsito. Outro ponto estudado foi a decisão de manter o status do pedido derivado do relógio, evitando uma thread separada apenas para alterar pedidos para atrasados.

Alguns prompts utilizados/registrados nessa frente foram:

- "Quero criar um projeto de Computação Concorrente usando uma central de delivery. Analise se receber pedidos em rajada, despachar entregadores e recalcular prazos quando o trânsito muda gera problemas de concorrência suficientes para a disciplina."
- "Me ajude a definir o escopo da Entrega 1 do Rota. Quero um protótipo single-node com concorrência local, mas já deixando claro como ele poderia evoluir para uma arquitetura distribuída."
- "Analise as entidades Restaurante, Entregador, Notificacao e Pedido e me diga quais invariantes de negócio precisam ser preservadas mesmo quando várias threads trabalham ao mesmo tempo."
- "Quero que uma mesma notificação recebida duas vezes gere somente um pedido. Explique como a deduplicação por impressão digital pode funcionar e qual regra precisa ser atômica."
- "No Rota, um entregador tem capacidade máxima de pedidos simultâneos. Como garantir que ele nunca receba mais pedidos do que a capacidade, mesmo com vários workers tentando despachar ao mesmo tempo?"
- "Quando todos os entregadores estiverem ocupados, quero manter o pedido em uma fila de espera e tentar despachar novamente quando surgir uma vaga. Analise essa regra e os riscos de concorrência envolvidos."
- "Explique como calcular a hora limite de uma entrega usando tempo de preparo, distância, velocidade, entrega expressa, horário de pico e bloqueio de via. Quero que o cálculo seja determinístico e fácil de testar."
- "Por que faz sentido manter o cálculo de SLA em uma função pura, sem acessar diretamente o estado compartilhado do núcleo?"
- "Quero que o status NO_PRAZO, EM_RISCO e ATRASADO seja derivado do relógio em vez de ter uma thread atualizando o campo de status. Quais corridas essa decisão evita?"
- "Uma entrega confirmada depois do horário limite ainda deve ser aceita, mas marcada como entregue com atraso. Analise se essa regra está correta e como garantir o instante exato dessa decisão."
- "Revise as regras de negócio do Rota e verifique se existe algum caso em que um pedido pode ser perdido, duplicado, ficar sem entregador indevidamente ou aparecer em duas agendas ao mesmo tempo."
- "Analise os testes do núcleo e me diga quais regras de negócio estão sendo protegidas por cada teste: criação, duplicata, fila de espera, capacidade, confirmação, redespacho, trânsito e alertas."

A IA também foi utilizada na revisão final do projeto para relacionar o problema apresentado com o comportamento observado nos testes e na carga. Essa revisão ajudou a preparar a explicação de por que milhares de pedidos podem ficar aguardando entregador sem que isso seja considerado uma falha de concorrência: nesse cenário, a capacidade física da frota é menor que a demanda, e o sistema mantém a invariante ao colocar os pedidos na fila em vez de ultrapassar a capacidade dos entregadores.

Minha participação também envolveu revisar a documentação de escopo e arquitetura, conferir os resultados finais e preparar a explicação do projeto, do uso de IA e dos próximos passos da arquitetura distribuída.

---

### Caio Leimig

Durante o desenvolvimento do Rota, fiquei responsável principalmente pela **arquitetura do protótipo, organização das threads e entendimento da evolução do sistema de uma implementação local para uma arquitetura distribuída**.

Utilizei a IA para analisar como dividir as responsabilidades do sistema sem depender de frameworks externos e mantendo visível o funcionamento da concorrência. O protótipo foi organizado em torno de um núcleo compartilhado, filas limitadas e diferentes famílias de threads, incluindo workers de ingestão, despacho, recálculo, monitoramento e atendimento HTTP.

Também usei a IA para estudar o ciclo de vida do sistema, principalmente inicialização, desligamento gracioso, drenagem das filas e rejeição de novas notificações durante o encerramento. Outro ponto importante foi avaliar por que Python com biblioteca padrão e threads era adequado para a Entrega 1, mesmo com a existência do GIL.

Alguns prompts utilizados/registrados nessa frente foram:

- "Analise a arquitetura do Rota e proponha uma organização single-node onde seja possível enxergar claramente as filas, workers, locks e o estado compartilhado."
- "Quero usar somente Python e biblioteca padrão nesta entrega. Compare threads, asyncio e multiprocessing para esse projeto e explique qual abordagem deixa os problemas de sincronização mais visíveis."
- "Me explique como organizar as famílias de threads do Rota: requisições HTTP, workers de ingestão, worker de despacho, worker de recálculo e monitor de pedidos."
- "Quais dados do Rota realmente são compartilhados entre threads e quais podem ser locais ou imutáveis? Monte um mapa de estado compartilhado."
- "Analise a relação entre o Nucleo, as filas internas, o Transito, o Relogio e o servidor HTTP. Quero evitar responsabilidades duplicadas entre essas partes."
- "Por que o cálculo da hora limite pode ficar fora do objeto Nucleo e ser tratado como uma função pura? O que isso melhora na arquitetura e nos testes?"
- "Quero que o sistema tenha filas limitadas em vez de crescer memória sem controle. Explique como aplicar backpressure e quando retornar sobrecarga para a API."
- "Como implementar um desligamento gracioso em um sistema com filas e vários workers, garantindo que o trabalho já aceito seja processado antes das threads terminarem?"
- "Explique o uso de poison pills em filas FIFO e quais cuidados são necessários para não aceitar novas notificações depois que o desligamento começou."
- "O Python tem GIL. Ainda assim posso ter condição de corrida no Rota? Use o padrão verificar-e-agir para mostrar por que um lock continua necessário."
- "Quero evoluir o Rota no futuro para serviços distribuídos. Mostre como restaurante pode virar uma unidade de particionamento e como o cálculo de SLA poderia virar um RPC gRPC."
- "Se a ingestão passar a usar uma fila distribuída at-least-once, quais partes do protótipo atual já ajudam a lidar com reentrega de mensagens?"
- "Revise a arquitetura atual e aponte acoplamentos que dificultariam uma futura separação em serviços."
- "Analise se o protótipo atual cumpre o objetivo da Entrega 1: concorrência local observável, sincronização explícita, testes e caminho de evolução para uma solução distribuída."

A IA também foi utilizada para discutir decisões como o uso de um **pool limitado de threads no servidor HTTP**, filas de tamanho limitado e separação entre regras de domínio, cálculo de trânsito e camada de comunicação. A revisão buscou garantir que a arquitetura não escondesse os problemas de concorrência que a disciplina queria avaliar.

Minha participação incluiu ainda a preparação da explicação da arquitetura na apresentação, com destaque para as famílias de threads, as decisões de tecnologia e a forma como o protótipo pode evoluir para comunicação entre serviços nas próximas entregas.

---

### Fernando Soares

Durante o desenvolvimento do Rota, fiquei responsável principalmente pela **análise dos riscos de concorrência, estratégia de sincronização, prevenção de deadlock e testes de estresse relacionados ao acesso simultâneo ao estado compartilhado**.

Utilizei a IA para identificar operações do sistema que possuem o padrão clássico de corrida "verificar e depois agir", como deduplicação de notificações e atribuição de pedidos a entregadores. Também analisei situações em que duas ou mais estruturas precisam ser alteradas de forma consistente, como no redespacho entre entregadores e na atualização das agendas.

Uma parte importante do trabalho foi estudar a hierarquia de locks utilizada pelo projeto. A IA foi usada para revisar a escolha de lock por restaurante, locks por entregador e RWLock para o trânsito, além de analisar a regra de adquirir múltiplos locks de entregador em ordem determinística para eliminar espera circular e prevenir deadlock.

Alguns prompts utilizados/registrados nessa frente foram:

- "Analise o Rota como um sistema concorrente e liste todas as condições de corrida possíveis envolvendo notificações, pedidos, restaurantes, entregadores, trânsito, monitor e desligamento."
- "Na deduplicação, várias threads podem verificar que uma impressão digital ainda não existe e depois inserir. Explique por que verificar e inserir precisam ficar na mesma seção crítica."
- "Compare um lock global, lock por restaurante e lock por pedido para o Rota. Quero manter correção sem serializar operações de restaurantes diferentes."
- "No despacho, eu posso ordenar os entregadores pela menor carga sem lock e só travar na hora de verificar capacidade e inserir? Analise se essa estratégia continua correta."
- "Mostre uma corrida em que dois workers escolhem o mesmo entregador com uma vaga restante e acabam ultrapassando a capacidade. Como o lock resolve isso?"
- "Tenho um redespacho entre dois entregadores. Crie um cenário em que duas threads fazem A para B e B para A ao mesmo tempo e entram em deadlock."
- "Explique as quatro condições de Coffman usando o redespacho do Rota e diga qual condição é quebrada quando os locks são sempre adquiridos em ordem de entregador_id."
- "Analise a hierarquia de locks do Rota e verifique se existe algum caminho que possa adquirir os mesmos locks em ordem inversa."
- "Quero usar um RWLock no trânsito. Explique por que vários cálculos podem ler ao mesmo tempo, mas uma atualização precisa de exclusividade."
- "Por que o RWLock precisa dar preferência a escritor? Monte um cenário em que o recálculo ficaria esperando indefinidamente se novos leitores nunca fossem bloqueados."
- "O trânsito pode mudar enquanto um pedido está sendo calculado. Analise como manter a leitura da versão do trânsito consistente até o pedido ser gravado."
- "Crie testes de estresse usando várias threads e Barrier para provar que 100 notificações iguais geram exatamente um pedido."
- "Crie um teste para confirmar entrega e redespachar o mesmo pedido ao mesmo tempo. Quais invariantes precisam continuar verdadeiras ao final?"
- "Analise test_concorrencia.py e me diga se os testes realmente exercitam concorrência ou se algum lock anterior pode estar serializando o cenário e escondendo um bug."
- "Quero demonstrar condição de corrida e deadlock durante a apresentação. Como criar demos pequenas em que a versão incorreta falha e a versão sincronizada funciona?"
- "Revise os testes de mutação do projeto: introduza mentalmente a remoção da deduplicação atômica, da ordenação dos locks e da proteção de capacidade e diga qual teste deveria falhar."

Durante a revisão, a IA também ajudou a identificar um problema no próprio cenário de teste de deadlock: quando todos os pedidos do teste estavam no mesmo restaurante, o lock do restaurante serializava as operações antes que elas chegassem aos locks de entregador, escondendo justamente o problema que o teste deveria detectar. O cenário foi então reorganizado para utilizar restaurantes diferentes e expor corretamente o redespacho concorrente.

Minha participação incluiu ainda a revisão do documento de concorrência, a preparação das demonstrações `demo_corrida.py` e `demo_deadlock.py` e a defesa das escolhas de sincronização durante a apresentação.

---

### Ramsés Cordeiro

Durante o desenvolvimento do Rota, fiquei responsável principalmente pela **camada de comunicação HTTP/REST, formato dos dados, dashboard, demonstração do sistema e validação integrada por meio de testes HTTP, scripts de demo e teste de carga**.

Utilizei a IA para estruturar uma API simples usando a biblioteca padrão do Python, sem adicionar dependências externas. O objetivo foi manter a comunicação separada das regras de negócio: os endpoints recebem e validam a requisição HTTP, enquanto o comportamento do sistema permanece concentrado no núcleo.

Também trabalhei na semântica das respostas, incluindo o uso de `202 Accepted` para notificações processadas de forma assíncrona, `200` para duplicatas já conhecidas, `409` para conflitos de estado, `422` para validações e `503` para situações de sobrecarga. A IA foi usada para revisar um formato consistente de erro e a estratégia de consulta posterior do estado das notificações.

Alguns prompts utilizados/registrados nessa frente foram:

- "Quero expor o Rota por REST usando apenas http.server da biblioteca padrão. Como separar a camada HTTP do Nucleo sem colocar regra de negócio nos handlers?"
- "Uma notificação é aceita agora e processada depois por um worker. Qual status HTTP faz mais sentido: 201 ou 202? Explique a semântica."
- "Se a mesma notificação for enviada novamente e já estiver registrada, devo retornar erro ou a representação existente? Analise isso considerando idempotência."
- "Me ajude a definir um formato único de erro JSON para validação, recurso não encontrado, conflito e sobrecarga."
- "Quais endpoints o protótipo precisa ter para entregadores, restaurantes, notificações, pedidos, trânsito, alertas, métricas e auditoria?"
- "Como validar corpo JSON, query parameters e identificadores sem espalhar lógica de validação por todos os endpoints?"
- "Quero um servidor HTTP com pool limitado de threads. Explique por que criar uma thread sem limite por conexão seria perigoso durante uma rajada."
- "Analise por que HTTP/1.0 sem keep-alive pode ser uma escolha aceitável neste protótipo com pool limitado."
- "Quero servir um dashboard HTML/CSS/JS no mesmo servidor sem Flask. Como carregar arquivos estáticos com segurança e evitar path traversal?"
- "Crie um dashboard para acompanhar pedidos, entregadores, trânsito, alertas e métricas usando os endpoints existentes, sem alterar a regra de negócio."
- "Quero um script de demo que crie uma notificação, mostre o processamento assíncrono, altere o trânsito, avance o relógio e confirme uma entrega. Como organizar esses passos para a apresentação?"
- "Crie um teste HTTP de fluxo completo que suba o servidor real, envie requisições e valide criação, consulta, trânsito, erros e confirmação de entrega."
- "Quero testar uma rajada de requisições HTTP concorrentes. Como garantir que o teste mede a camada HTTP e também preserva as invariantes do núcleo?"
- "Analise scripts/carga.py e monte uma carga com milhares de notificações, consultas, confirmações, redespachos e mudanças de trânsito no mesmo período."
- "Depois do teste de carga, quais invariantes a auditoria deve verificar para eu poder afirmar que o sistema continuou consistente?"
- "Explique o que significa usar um oráculo sequencial para recalcular os pedidos e comparar o resultado com o estado produzido durante a execução concorrente."
- "No teste de carga apareceram respostas 409 no redespacho e milhares de pedidos aguardando entregador. Analise por que isso pode ser comportamento esperado e não falha do sistema."
- "Revise a demo e o dashboard pensando na apresentação de 10 minutos. O que precisa ficar visível para provar concorrência, idempotência, alteração de trânsito e auditoria?"

A IA também foi utilizada durante a execução real dos scripts para analisar problemas encontrados no ambiente, como a necessidade de manter o servidor em um terminal separado durante o teste de carga e uma incompatibilidade de encoding da demonstração no PowerShell do Windows. Esses pontos foram corrigidos ou documentados antes da apresentação.

Minha participação incluiu a preparação da documentação de protocolos e resultados, a revisão do dashboard, a execução dos testes integrados e a apresentação da API, da demonstração ao vivo e dos resultados de carga/auditoria.

---

### Revisão e integração da equipe

Embora cada integrante tenha um foco principal, o Rota foi desenvolvido e revisado como um único sistema. As decisões de concorrência afetam diretamente o domínio; a arquitetura define onde os locks e filas existem; a API precisa respeitar a semântica assíncrona do núcleo; e os testes de carga somente são úteis se verificarem as mesmas invariantes definidas nas regras de negócio.

Durante a revisão integrada, a IA foi utilizada como apoio para:

- conferir se os documentos de escopo, concorrência, protocolos, protótipo e apresentação estavam coerentes entre si;
- executar e interpretar testes unitários, de concorrência e HTTP;
- revisar os scripts de demonstração de corrida e deadlock;
- executar o teste de carga e interpretar suas métricas;
- analisar a auditoria das invariantes e o oráculo sequencial;
- identificar riscos de deadlock, sobrecarga, starvation e atualização perdida;
- revisar o desligamento gracioso e a drenagem das filas;
- melhorar a apresentação visual do dashboard;
- preparar perguntas prováveis de banca e revisar as justificativas das decisões técnicas.

Entre os problemas encontrados durante a revisão estavam um teste de deadlock que inicialmente não expunha a mutação por causa da serialização anterior pelo lock de restaurante, uma colisão de nome de parâmetro ao publicar uma atualização de trânsito, um helper de teste que tratava string vazia como valor padrão, pouca cobertura de confirmações/redespachos no primeiro formato do teste de carga e uma incompatibilidade de encoding na demo executada pelo PowerShell. A equipe revisou esses pontos, alterou o projeto quando necessário e executou novamente os testes.

A utilização da Inteligência Artificial serviu como ferramenta de apoio para estudo, discussão de alternativas, revisão de implementação, criação e análise de testes, depuração e documentação. O entendimento das soluções, a escolha das decisões adotadas, a validação dos resultados e a responsabilidade pelo código entregue permaneceram com os integrantes da equipe.

## 5.2 Decisões propostas pela IA

As decisões abaixo foram revistas pela equipe. **Aceita** significa que a proposta foi mantida; **Modificada** significa que a ideia-base permaneceu, mas sua implementação foi ajustada após revisão ou testes.

| # | Proposta da IA | Alternativas consideradas | Justificativa dada pela IA | Decisão da equipe | Justificativa da equipe |
|---|---|---|---|---|---|
| D1 | Domínio = despacho de pedidos de delivery (Rota) | central de emergência, monitoramento IoT, motor de leilão | oferece rajada de eventos, deduplicação, recálculo e recurso limitado | **Aceita** | o domínio permite demonstrar concorrência de forma concreta e fácil de explicar, com invariantes observáveis em testes e na demo |
| D2 | Python + biblioteca padrão | Go, Java, Flask/FastAPI | reduz dependências e deixa threads/locks explícitos | **Aceita** | o professor confirmou que Python era permitido; a biblioteca padrão manteve o foco na concorrência e evitou complexidade de framework |
| D3 | Threads | asyncio, multiprocessing | expõe locks, corridas e deadlocks, alinhando-se ao objetivo da disciplina | **Aceita** | a equipe precisava demonstrar sincronização explícita; threads permitem que os problemas de verificar-e-agir e ordem de locks apareçam no próprio protótipo |
| D4 | Capacidade por entregador + fila de espera com redespacho automático | atribuição manual; fila global sem limite por entregador | modela um recurso físico limitado e cria uma invariante relevante | **Modificada** | a ideia foi mantida, mas após a revisão E9 o despacho passou a escolher o pedido em espera mais urgente, em vez de depender da ordem arbitrária do conjunto |
| D5 | Trânsito simulado minuto a minuto | modelo binário de disponibilidade | representa um SLA contínuo sem exigir roteirizador real | **Aceita** | o modelo foi suficiente para demonstrar pico, bloqueio, recálculo e consistência de versão sem aumentar demais o escopo |
| D6 | Confirmação atrasada continua válida e registra `entregue_atrasado` | recusar confirmação após o limite | uma entrega atrasada ainda aconteceu e precisa ser registrada | **Aceita** | rejeitar a confirmação esconderia o atraso; a equipe preferiu registrar a entrega e preservar a informação de descumprimento do SLA |
| D7 | Deduplicação por impressão digital do conteúdo | confiar apenas em ID externo/webhook | retries podem representar o mesmo evento com identificadores diferentes | **Aceita** | a impressão digital permite idempotência dentro do protótipo e é protegida por seção crítica para impedir criação duplicada sob concorrência |
| D8 | Lock por restaurante | lock global; lock por pedido | mantém paralelismo entre restaurantes sem complicar demais as invariantes | **Aceita** | operações de restaurantes diferentes podem avançar em paralelo; um lock global reduziria desnecessariamente a concorrência |
| D9 | Ordem de locks por `entregador_id` no redespacho | `tryLock` + retry | elimina espera circular de maneira determinística | **Aceita** | a ordenação quebra a condição de espera circular de Coffman e foi validada por testes/demos de deadlock |
| D10 | Trânsito imutável + RWLock com preferência a escritor | lock comum; cópia sem versão | permite leitores paralelos e evita starvation da atualização | **Aceita** | cálculos podem ler em paralelo, mas alterações de trânsito precisam exclusividade e não podem ficar indefinidamente atrás de novos leitores |
| D11 | Status do pedido derivado do relógio | thread separada marcando ATRASADO | evita disputa entre monitor e confirmação | **Aceita** | derivar o status reduz estado mutável e elimina uma fonte de corrida sem perder informação de negócio |
| D12 | Auditoria com oráculo sequencial + checagem de capacidade | somente testes unitários | valida invariantes após carga concorrente real | **Modificada** | a auditoria foi mantida e ampliada com testes HTTP, estresse e mutação; a revisão E15 mostrou que apenas ter testes não bastava, eles precisavam detectar as falhas esperadas |
| D13 | Dashboard estático servido pelo próprio `http_api.py` | Flask/Jinja; app Node separado | evita nova dependência e reaproveita o servidor existente | **Aceita** | o dashboard precisava apenas observar o protótipo; HTML/CSS/JS estático foi suficiente e manteve a camada visual separada das regras do núcleo |

## 5.3 Erros encontrados e corrigidos durante a revisão

| # | Problema | Como apareceu | Correção |
|---|---|---|---|
| E1 | Teste de deadlock do redespacho ****não detectava**** a mutação (lock sem ordenar) | ao testar a própria suíte de mutação: com só 1 restaurante, o lock do restaurante (L2) já serializava tudo antes de chegar nos locks de entregador, escondendo a corrida que a ordenação deveria resolver | pedidos do teste espalhados em 8 restaurantes diferentes (locks L2 independentes); a mutação passou a ser detectada em 3 de 3 execuções |
| E2 | `Alertas.publicar("TRANSITO_ATUALIZADO", tipo=tipo, ...)` — `TypeError: got multiple values for argument 'tipo'` | execução manual de `declarar_janela` logo após escrever o núcleo | parâmetro renomeado para `tipo_janela` na chamada (o primeiro `tipo` já é o nome do evento) |
| E3 | Helper de teste `notif(descricao="")` não conseguia testar descrição vazia | `test_validacoes` falhou: caso "descrição vazia" não levantava `ErroValidacao` | o helper usava `descricao or texto_padrao`; string vazia é **falsy** em Python e caía no padrão. Trocado por checagem explícita `is None` |
| E4 | Script de carga quase não exercitava `confirmar`/`redespachar` | métricas da carga mostravam 0 chamadas nessas operações | thread de entregador filtrava pedidos `EM_RISCO` (estado raro logo após a criação); trocado para `NO_PRAZO` (estado inicial, disponível desde o primeiro pedido) |
| E5 | `python scripts/carga.py` deu "servidor não respondeu em /health" | usuário rodou sem o servidor de pé em outro terminal | não era bug — reforçado no doc 04 que são ****dois**** terminais (servidor + carga) |
| E6 | Demo interativa quebrava com `UnicodeEncodeError` no console do Windows | execução real de `scripts/demo.py` no PowerShell (codepage `cp1252`) | `sys.stdout.reconfigure(encoding="utf-8")` no início do script |
| E7 | Capacidade de entregador aceitando valores absurdos nos primeiros rascunhos de teste (`capacidade: 50`) | `cadastrar_entregador` rejeitou com `ErroValidacao` (limite real é 1–10) | não era bug do núcleo — a validação estava certa; os testes foram ajustados para usar valores dentro do limite |
| E8 | Ao limpar servidores `rota` esquecidos na porta 8080 durante a sessão 2, a IA encerrou ****todos**** os processos que escutavam nela, inclusive `wslrelay` (WSL) e `com.docker.backend` (Docker Desktop), que não eram do projeto | a IA listou os donos da porta 8080 e os finalizou sem checar o nome de cada um | a IA avisou a equipe na hora; Docker Desktop e WSL precisam ser reabertos se estiverem em uso. Depois disso, só processos `python` são encerrados. Nenhum arquivo do projeto foi afetado |
| E9 | A vaga liberada por uma entrega ia para um pedido qualquer da fila de espera, não para o mais urgente (`list(self._aguardando)[:3]`: ordem arbitrária de um conjunto) | revisão do código + reprodução: com 30 pedidos esperando, a vaga foi para um com prazo 19 min depois do mais urgente | o despacho passou a escolher o pedido em espera de menor hora limite (`_mais_urgente_em_espera`); a fila de despacho virou um sinal. Testes `test_vaga_liberada_vai_para_o_pedido_mais_urgente` e `test_varias_vagas_...` (falhavam antes). Risco R17 no doc 02 |
| E10 | Cada pedido sem vaga fazia o worker de despacho travar o restaurante e tentar os 4 entregadores, mesmo com todos cheios | leitura do código; efeito medido no `carga.py`: \~213 req/s e p50 de \~256 ms em `notificar` | o despacho olha antes se existe vaga (leitura otimista, sem lock) e só então procura o pedido. Mesma carga depois: 410 req/s e p50 de \~130 ms. Não medimos com profiler; a causa é a explicação provável |
| E11 | O desligamento enfileirava as pílulas do despacho e do recálculo junto com as da ingestão; a ingestão ainda gerava trabalho para o despacho depois de ele ter encerrado, contradizendo a promessa "drena as três filas" do doc 02 (R13) | reprodução: 1 000 notificações e `parar()`; em 5 rodadas ficaram 169 a 831 itens sem processar | `parar()` espera a ingestão terminar antes de enviar as pílulas do recálculo e do despacho. Teste `test_desligamento_drena_tambem_o_despacho` (falhava antes) |
| E12 | Os alertas eram carimbados com o horário de parede (sem fuso) e não com o relógio do sistema | visto nos screenshots do dashboard: alertas às 19:26 com o relógio simulado em 12:25; reprodução: carimbo 20:02 contra 11:00 | `Alertas` recebe o relógio injetado e carimba com ele (lido antes do lock, porque Alertas e Relogio são folhas). Teste `test_alerta_e_carimbado_com_o_relogio_do_sistema` |
| E13 | Instante com `Z` (UTC, comum em webhook) era rejeitado no Python 3.10 (`fromisoformat` só aceita `Z` do 3.11 em diante), e o mesmo instante em fusos diferentes gerava notificações diferentes | revisão do código: o README promete Python 3.10+. Não reproduzimos no 3.10 localmente; o job 3.10 do CI exercita o teste | `_parse_datetime` trata `Z` e converte todo instante para o horário de Brasília. Teste `test_instante_com_z_ou_outro_fuso_e_o_mesmo_evento` |
| E14 | `PUT`, `PATCH`, `DELETE` e `OPTIONS` recebiam `501` com uma página HTML da biblioteca padrão, e não o `405` em JSON que o doc 03 promete | reprodução com `http.client` | handlers desses métodos passam pelo mesmo despachante e o corpo pendente é descartado antes do erro (evita RST no Windows). Casos acrescentados a `test_erros` |
| E15 | ****A suíte não detectava 4 dos bugs que o doc 02 dizia prevenir****: lock de leitura do trânsito esquecido, lock do restaurante esquecido na confirmação, lock do entregador esquecido na atribuição e RWLock sem preferência ao escritor. Os testes de estresse dependiam de a troca de thread cair por acaso no meio do "verificar-e-agir", o que quase nunca acontece sob o GIL; e o teste do RWLock provava exclusão, não a preferência ao escritor | teste de mutação rodado sobre uma cópia do código (`scripts/mutacoes.py`): 4 mutações "NÃO DETECTADAS" em 3 rodadas | `disparar()` passou a trocar de thread a cada \~1 µs; nova classe `TestJanelasAlargadas` força a intercalação ruim de propósito (cálculo segurado 0,3 s, confirmação congelada, `len` da agenda lento); novo teste de starvation do escritor. As 12 mutações passaram a ser detectadas |
| E16 | `demo_corrida.py` mostrava "rota (com lock)", mas essa linha rodava uma ****cópia didática**** do padrão, não o núcleo | releitura do script | a linha do rota passou a chamar o `Nucleo.receber_notificacao` real com 50 threads e contar os pedidos criados (1). O padrão ingênuo continua como exemplo do bug e está identificado como tal |
| E17 | `scripts/carga.py` só reprovava resposta 5xx: um 400 (corpo inválido) ou outro status inesperado passaria com "OK" | leitura do script | tabela de status esperados por operação (409 em confirmar e redespachar, 503 em notificar); qualquer outro reprova, inclusive no CI |
| E18 | O teste HTTP do relógio simulado avançava o relógio do núcleo ****compartilhado**** por todos os testes da classe; só a ordem alfabética escondia o efeito. Faltavam também testes do cálculo de trânsito para pico cobrindo o trajeto, bloqueio no meio da viagem e janela inclusiva | leitura dos testes | `TestHttpRelogio` com núcleo próprio (mais o caso do relógio real, que responde 409); 3 testes novos em `test_transito.py`, com os valores conferidos à mão |

## 5.4 Checklist de domínio por responsável

A última coluna já contém uma explicação-base coerente com a divisão do projeto. Antes da apresentação, cada integrante deve reler o código indicado e garantir que consegue explicar o trecho **sem decorar o texto**.

| Tema | Onde no código | Responsável | Pergunta-teste | Explicação com as próprias palavras |
|---|---|---|---|---|
| Arquitetura e threads | `rota/__main__.py`, `Nucleo.iniciar`, `ServidorComPool` em `http_api.py` | **Caio Leimig** | Quantas threads existem e o que cada uma faz? | O sistema separa atendimento HTTP e trabalho interno. O núcleo cria workers para ingestão, despacho e recálculo/monitoramento, enquanto o servidor usa um pool limitado; essa separação evita que uma rajada crie threads sem controle e deixa claro qual fila alimenta cada tipo de trabalho. |
| Ciclo de vida, filas e backpressure | `Nucleo.iniciar`, `Nucleo.parar`, filas internas | **Caio Leimig** | Como o sistema evita crescer sem limite e como encerra sem perder trabalho aceito? | As filas têm capacidade definida, então o sistema pode sinalizar sobrecarga em vez de consumir memória indefinidamente. No encerramento, novas entradas deixam de ser aceitas e a ordem das poison pills respeita as dependências entre os workers para que o trabalho já aceito seja drenado. |
| Deduplicação (R1) | `Nucleo.receber_notificacao`, `impressao_digital` | **Gabriel França** | Por que verificar e inserir precisam estar na mesma seção crítica? | A regra é que a mesma notificação só pode gerar um pedido. Se duas threads verificarem separadamente que a impressão ainda não existe, ambas podem criar o mesmo pedido; por isso a checagem e o registro da impressão precisam acontecer atomicamente. |
| Capacidade do entregador (R5) | `Nucleo._tentar_atribuir` | **Gabriel França** | Por que o ranking pode ser feito sem lock, mas a atribuição não? | O ranking é apenas uma escolha preliminar e pode ficar desatualizado. Na hora de realmente atribuir, é obrigatório travar o entregador, conferir novamente a capacidade e inserir o pedido na mesma seção crítica para nunca ultrapassar o limite. |
| Fila de espera e despacho | `Nucleo._tentar_despachar`, `_mais_urgente_em_espera`, `_acordar_fila_espera` | **Gabriel França** | O que acontece quando todos os entregadores estão cheios? Como um pedido em espera é atendido depois? | O pedido continua registrado e entra na espera, em vez de violar a capacidade de alguém. Quando uma vaga é liberada, o despacho é acordado e tenta primeiro o pedido com hora limite mais urgente, correção introduzida após a revisão E9. |
| Cálculo da hora limite | `calcular_hora_limite` em `rota/transito.py` | **Gabriel França** | Como preparo + distância + pico viram uma hora limite? | O cálculo parte do tempo de preparo e soma o tempo estimado de deslocamento. A velocidade efetiva muda conforme as janelas de trânsito; pico aumenta o tempo e bloqueio pode impedir o avanço naquele intervalo, mantendo o cálculo determinístico para o mesmo snapshot. |
| RWLock (R3/R4) | `rota/rwlock.py`, `Nucleo._processar`, `Nucleo.declarar_janela` | **Fernando Soares** | Por que o worker segura a leitura até gravar o pedido? O que é preferência para escritor? | O pedido precisa ser calculado e gravado usando uma visão coerente do trânsito; liberar a leitura antes permitiria uma atualização no meio da operação. A preferência ao escritor impede que uma atualização fique esperando para sempre enquanto novos leitores continuam entrando. |
| Deadlock (R6) | `Nucleo.redespachar_pedido` | **Fernando Soares** | Quais são as quatro condições de Coffman e qual quebramos? | Deadlock exige exclusão mútua, posse e espera, não-preempção e espera circular. O Rota mantém as três primeiras, mas quebra a espera circular ao adquirir múltiplos locks de entregador sempre na mesma ordem de `entregador_id`. |
| Testes concorrentes e mutação | `tests/test_concorrencia.py`, `scripts/mutacoes.py`, `scripts/demo_corrida.py`, `scripts/demo_deadlock.py` | **Fernando Soares** | Por que um teste concorrente pode passar mesmo com um lock removido? | Uma corrida só aparece se a intercalação ruim acontecer; sob o GIL, isso pode não ocorrer por acaso. Por isso os testes passaram a forçar janelas de concorrência e as mutações verificam se remover uma proteção realmente faz algum teste falhar. |
| Protocolo HTTP/REST | rotas em `rota/http_api.py`, doc 03 | **Ramsés Cordeiro** | Por que 202 e não 201? Por que REST aqui e gRPC depois? | A notificação é aceita pela API antes de o processamento assíncrono terminar, então `202 Accepted` representa melhor o estado naquele instante. REST simplifica o protótipo e a demo; numa evolução distribuída, gRPC pode ser usado em comunicação interna entre serviços com contratos tipados. |
| Dashboard, demo e carga | `static/`, `scripts/demo.py`, `scripts/carga.py` | **Ramsés Cordeiro** | O que a demonstração e a carga provam além de “o servidor respondeu”? | A demo mostra o fluxo observável do sistema, enquanto a carga força várias operações concorrentes e mede respostas/latências. Depois, a auditoria verifica se o estado final continua respeitando deduplicação, capacidade e consistência, então desempenho não é avaliado isolado da correção. |
| Verificação e auditoria | `Nucleo.auditoria`, testes HTTP e `scripts/carga.py` | **Ramsés Cordeiro** | O que a auditoria confere e o que é o oráculo sequencial? | A auditoria procura violações das invariantes no estado produzido pelas threads, como excesso de capacidade ou resultados inconsistentes. O oráculo recalcula de forma sequencial aquilo que pode ser comparado e serve como referência determinística para conferir a execução concorrente. |

## 5.5 Síntese da divisão da equipe

- **Gabriel França:** domínio, escopo, regras do despacho, fila de espera, capacidade e cálculo da hora limite.
- **Caio Leimig:** arquitetura, threads, filas, backpressure, inicialização/desligamento e evolução distribuída.
- **Fernando Soares:** sincronização, RWLock, condições de corrida, deadlock, estresse e testes de mutação.
- **Ramsés Cordeiro:** API REST, dashboard, demonstração, carga, métricas e auditoria integrada.

A IA foi utilizada como ferramenta de apoio para estudo, discussão de alternativas, revisão de implementação, testes, depuração e documentação. As decisões finais, a validação das alterações e a responsabilidade pelo código entregue permaneceram com a equipe.
