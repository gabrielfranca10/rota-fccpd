# 6. Apresentação (10 minutos) e perguntas prováveis

> Critério da rubrica: **Oral Presentation and Team Collaboration** — todos falam, todos respondem.

## 6.1 Roteiro com divisão (ajustem os nomes se quiserem trocar blocos)

| Tempo | Quem | Bloco | Pontos obrigatórios |
|---|---|---|---|
| 0:00–1:30 | **Gabriel França** | Problema e escopo | rota; pedido atrasado = nota baixa e reputação; notificações em rajada, duplicadas, trânsito que muda; o que entra e o que não entra na Entrega 1 |
| 1:30–3:30 | **Caio Leimig** | Arquitetura | diagrama do doc 01; as 7 famílias de threads; por que Python/threads/stdlib; como evolui para gRPC e serviços |
| 3:30–6:00 | **Fernando Soares** | Concorrência | R1 (tabela da corrida) + `demo_corrida.py`; R5 capacidade do entregador; R6 deadlock + `demo_deadlock.py`; hierarquia de locks |
| 6:00–8:00 | **Ramsés Cordeiro** | Protocolo + demo ao vivo | REST/JSON, 202 + consulta, idempotência, formato de erro; `scripts/demo.py` passos 1–4; dashboard ao vivo |
| 8:00–9:30 | **Ramsés → Gabriel** | Prova sob carga | `scripts/carga.py`: req/s, zero erros, auditoria `ok` com oráculo, o que os 409 e os "aguardando entregador" significam |
| 9:30–10:00 | **Gabriel França** | IA e próximos passos | como a IA foi usada, o que revisaram/rejeitaram; roadmap |

## 6.2 Roteiro da demo (ensaiar antes!)

Terminal 1:
```bash
python -m rota --relogio-simulado 2026-09-21T11:00
```
Abra `http://127.0.0.1:8080` no navegador — deixe o dashboard visível durante toda a apresentação.

Terminal 2:
```bash
python scripts/demo_corrida.py      # pedidos duplicados sem lock x 1 com lock
python scripts/demo_deadlock.py     # trava x não trava
python scripts/demo.py              # Enter a cada passo — acompanhe pelo dashboard
python scripts/carga.py             # ~5 mil requisições + auditoria
```
**Plano B:** se algo falhar ao vivo, mostrem a saída gravada no doc 04 (tirem prints no ensaio).

## 6.3 Perguntas prováveis e respostas

**1. Por que usar lock se o Python tem GIL?**
O GIL protege o interpretador, não a lógica do programa. A troca de thread pode ocorrer entre "verificar" e "agir"; a `demo_corrida.py` mostra dezenas de pedidos duplicados em Python puro.

**2. Onde exatamente pode haver deadlock no sistema?**
Onde uma thread segura um lock e pede outro: redespacho (duas agendas), ingestão (restaurante → entregador → índice) e auditoria (todos). Evitamos com uma hierarquia fixa e, entre locks do mesmo nível, ordem por id. Quebramos a condição de espera circular de Coffman.

**3. Por que não usar um único lock global?**
Seria correto, mas serializaria operações de restaurantes diferentes. Com lock por restaurante, restaurantes distintos andam em paralelo e o restaurante vira a unidade de particionamento da versão distribuída.

**4. Por que não um lock por pedido?**
Várias invariantes são do restaurante (lista de pedidos, vínculo). Lock por pedido exigiria pegar vários locks por operação — mais chance de erro sem ganho real.

**5. O que acontece se o trânsito mudar enquanto um pedido está sendo calculado?**
O worker segura a leitura do RWLock do cálculo até gravar. A troca pega a escrita e espera. Todo pedido antigo já está gravado quando o recálculo começa; todo pedido novo já usa a versão nova. A auditoria prova comparando com o recálculo sequencial.

**6. O escritor do trânsito pode esperar para sempre?**
Não: nosso RWLock dá preferência a escritor — com escritor esperando, novos leitores aguardam.

**7. Como garantem que um entregador nunca recebe pedido além da capacidade?**
O ranking de "quem tem menos pedidos" é feito sem lock (só pra ordenar candidatos — pode estar levemente desatualizado). A decisão real — checar `len(agenda) < capacidade` e inserir — acontece sob o lock daquele entregador especificamente, e a função nunca segura dois locks de entregador ao mesmo tempo nesse caminho. Se o candidato encheu entre o ranking e a checagem, ela tenta o próximo. A auditoria confere `len(agenda) <= capacidade` pra todo entregador.

**8. O que acontece com um pedido se nenhum entregador tem vaga?**
Ele entra numa fila de espera (`_aguardando`) e um alerta é emitido. Quando alguém confirma uma entrega e libera vaga, o despacho atribui a vaga ao pedido em espera **mais urgente** (menor hora limite, e não o primeiro da fila); o monitor também acorda o despacho periodicamente como rede de segurança, então nenhum pedido fica esquecido.

**9. E se chegarem mais notificações do que o sistema processa?**
Fila limitada a 1000. Cheia → `503` com `Retry-After: 1`; a notificação rejeitada não é registrada, então o reenvio funciona. Não bloqueamos a thread HTTP nem crescemos a memória sem limite.

**10. Por que 202 e não 201?**
201 diz "criei o recurso". Aqui só aceitamos; o pedido é calculado depois por um worker. O cliente acompanha pelo `GET /notificacoes/{id}`.

**11. Como garantem que a mesma notificação não gera dois pedidos?**
Impressão digital SHA-256 do conteúdo normalizado; verificar e inserir na mesma seção crítica; a auditoria confere 1:1.

**12. Um entregador confirma a entrega depois da hora limite. O que acontece?**
A confirmação **sempre** é aceita — uma entrega atrasada ainda é uma entrega. O campo `entregue_atrasado` é decidido no instante em que o lock do restaurante é obtido durante a confirmação: esse é o ponto de linearização.

**13. Como sabem que não há bugs de concorrência?**
Quatro camadas: testes de estresse com `Barrier`; testes de mutação (introduzimos os bugs e os testes falharam — inclusive um caso em que o primeiro teste de deadlock não detectava o bug até corrigirmos o próprio teste, ver doc 05); auditoria de invariantes; teste de carga terminando em auditoria com oráculo.

**14. Por que HTTP/1.0 sem keep-alive?**
Com pool limitado, uma conexão parada seguraria uma thread. Fechando por resposta, a thread só fica ocupada durante o atendimento.

**15. Como o desligamento evita perder notificações?**
Para o accept, espera requisições em curso, marca "não aceitando" sob o mesmo lock do enfileiramento e coloca pílulas de veneno no fim da fila de ingestão (FIFO: todo trabalho aceito é processado antes) e só depois que a ingestão termina manda as pílulas do despacho e do recálculo, porque a ingestão ainda gera trabalho para eles.

**16. O que muda quando for distribuído?**
Fila vira durável; ingestão vira *at-least-once* com consumidor idempotente (a impressão digital já resolve); restaurante vira partição com nó dono; `calcular_hora_limite` vira RPC gRPC; alertas viram stream `AcompanharPedidosEmRisco`.

**17. Por que o cálculo da hora limite é uma função pura?**
Não toca em estado compartilhado: pode rodar em qualquer thread sem lock, é trivial de testar e vira um RPC sem mudanças.

**18. Qual a diferença entre `PICO` e `BLOQUEIO`?**
Pico: o trajeto fica mais lento (fator de velocidade reduzido), mas o entregador continua andando. Bloqueio: a via está interditada, o avanço para completamente até a janela acabar, e a saída do pedido espera a via liberar.

**19. Os 409 do teste de carga são erros?**
Não. Um redespacho pediu um entregador que, entre o pedido chegar e a decisão ser tomada, já tinha ficado no limite de capacidade. O sistema detecta o estado mudado e recusa: é a concorrência sendo tratada corretamente.

**20. Onde a IA ajudou e o que vocês mudaram?**
Responder com o doc 05 — com as decisões que **vocês** registraram.
