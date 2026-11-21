# 07 — Alucinações de SQL, métricas erradas e fan-out

## O problema

Há três tipos de erro que o SQL "passa" sem dar erro de base de dados:

1. **Alucinação de schema.** O modelo usa `orders.total_value`, que não existe. Isto é fácil de detectar (é um erro), mas a mensagem bruta do PostgreSQL não ajuda o modelo a corrigir-se.
2. **Métrica errada com SQL válido.** "Receita" sem subtrair devoluções é uma soma correcta de outra coisa.
3. **Fan-out.** Somar um valor do lado "1" de uma relação "1-N" depois de um join duplica o valor uma vez por linha filha. O número sai inflacionado e nenhum erro aparece.

O primeiro é tratado pelo validador (doc 03). Os dois últimos precisam de verificação semântica.

## O que entra e o que sai

Entra: SQL já validado, a semantic layer e os parâmetros. Sai: uma lista de avisos `{code, message}` e o campo `verified` (verdadeiro só se não houver avisos). **Os avisos não bloqueiam a execução**: o resultado é apresentado como não verificado.

Saída real (mesma função que os endpoints usam):

```
receita sem devolucoes | validation ok= True []
   warnings: [('metric_definition_mismatch', 'receita: falta a tabela returns.')]
fanout total_amount | validation ok= True []
   warnings: [('possible_fanout', 'SUM sobre orders.total_amount com join a order_items: valores podem ser duplicados. Pré-agregue o lado N antes de somar.')]
typo total_value | validation ok= False [('unknown_column', 'orders.total_amount')]
```

A última linha mostra a sugestão de correcção: a validação já devolve `orders.total_amount` para `total_value`, por distância de edição (`difflib`).

## Como funciona por dentro

Ficheiro: `backend/app/verification/checks.py`.

- **Métrica.** Para cada métrica com `signature` em `semantic/metrics.yaml` (por exemplo, `SUM(order_items.line_total)` para `receita`), verifica se o SQL usa essa agregação sobre essa coluna (`_metric_warnings`). Se usar, confirma que as `requires_tables` estão no SQL e que as `requires_filter_columns` aparecem no `WHERE` (`where_refs`). Falta algo → `metric_definition_mismatch`.
- **Fan-out.** Para cada `SUM`, `AVG` ou `COUNT` não `DISTINCT` (`_fanout_warnings`), vê a tabela da coluna agregada. Se essa tabela for o lado "1" de uma aresta do schema (`order_items.order_id → orders.id`) **e** a tabela filha estiver no mesmo `SELECT`, emite `possible_fanout`.
- **Âmbito por `SELECT`.** A comparação de tabelas é feita por `SELECT` (`scope_tables`). Isto é necessário: sem ela, a receita correcta do doc 06 seria marcada como fan-out, porque `returns` aparece na subquery pré-agregada. Esse falso positivo foi evitado de propósito e está testado (`test_fanout_is_judged_per_query_scope`).
- **Resolução de colunas.** `_Analysis.resolve` resolve `alias.coluna` para `tabela.coluna` pelo mapa de aliases. Colunas sem qualificador só se resolvem se existirem numa única tabela da consulta; caso contrário ficam sem resolução e não geram aviso (preferimos silêncio a adivinhar).
- **Explicação.** `backend/app/verification/explain.py:build_explanation` junta SQL, filtros do `WHERE` em SQL, parâmetros, tabelas, suposições, avisos e número de linhas. Usado em `POST /query/execute`.

A resposta de `POST /query/execute` inclui `verified`, `warnings` e `explanation`. O `EXPLAIN` (`explain: true`) também devolve avisos, mas **nunca** executa a consulta (ver abaixo).

## Porquê esta escolha

- **Heurística explícita, não mágica.** Cada regra tem uma mensagem legível e um teste. Quem lê o aviso percebe o que falhou.
- **Não bloquear.** Um aviso pode ser falso positivo. Bloquear um resultado correcto seria pior para o utilizador. O sinal correcto é `verified: false`.
- **Definição vem do YAML.** As métricas e o que elas exigem estão em `semantic/metrics.yaml`, para que a verificação e o prompt usem a mesma definição.
- **Fan-out por scope e não global.** Uma regra global daria falsos positivos em qualquer SQL com subqueries pré-agregadas, que é precisamente o padrão recomendado.

## Alternativas

- **Bloquear quando há aviso.** Mais seguro para números, mas impede consultas válidas. Pode ser uma opção para métricas críticas no futuro.
- **Comparar resultados com uma consulta de referência** (execution accuracy, tarefa 7). Mede o efeito real; não serve para verificar uma pergunta nova em tempo real, porque não há referência. Os dois são complementares.
- **Análise de cardinalidade real** (`EXPLAIN ANALYZE` ou estatísticas). Mais exacta, mas executa a consulta. Por isso não é usada aqui: o `EXPLAIN` do sistema é sempre sem `ANALYZE`.

## Como falha

Testes em `tests/unit/test_verification.py`:

- Receita correcta não gera avisos: `test_correct_revenue_query_has_no_warnings`.
- Receita sem devoluções: `test_revenue_without_returns_is_a_metric_mismatch`.
- Receita sem filtro de estado: `test_revenue_without_status_filter_is_a_metric_mismatch`.
- Soma do total da encomenda com join às linhas: `test_sum_of_parent_total_joined_to_children_is_possible_fanout`.
- Falsos positivos evitados: `test_count_distinct_is_not_fanout`, `test_fanout_is_judged_per_query_scope`.
- Endpoint: `verified: false` com aviso, `verified: true` para a consulta correcta (`test_validate_endpoint_reports_verified_*`).

Falha conhecida e documentada:

- **Joins em cadeia com aliases repetidos** ou colunas sem qualificador em várias tabelas não são resolvidos. Nesses casos a heurística fica em silêncio, o que é um falso negativo.
- **Aviso de métrica por assinatura.** Uma consulta que use `SUM(order_items.line_total)` com outro significado (por exemplo, sem o objectivo de receita) recebe o aviso de receita. É aceitável porque o aviso diz exactamente o que falta.

**Medição.** Os números de falsos positivos e negativos destas regras ainda não existem: a avaliação (tarefa 7.2) é que os mede. Até lá, qualquer taxa fica `TODO: medir`.

## Perguntas de entrevista

**1. O que é fan-out e como se previne?**
Quando um join 1-N duplica as linhas do lado 1 antes de uma soma, o valor do lado 1 é somado várias vezes. Previne-se pré-agregando o lado N numa subquery antes do join, ou usando `DISTINCT` quando o objectivo é contar entidades.

**2. Porque é que o aviso de fan-out não bloqueia a execução?**
Porque é uma heurística com falsos positivos. O sistema diz claramente que o resultado não está verificado; quem decide é o utilizador. Bloquear seria mais seguro para números, mas impediria consultas correctas.

**3. Como evitas que a verificação marque a receita correcta como fan-out?**
Analisando as tabelas por `SELECT` (scope), e não em todo o SQL. A subquery que pré-agrega `returns` é outro `SELECT`, por isso não conta como filha no mesmo nível.

**4. Qual é a diferença entre `metric_definition_mismatch` e um erro de validação?**
A validação decide o que pode ser executado (segurança e existência). A verificação decide se a resposta corresponde à definição de negócio. Um SQL pode passar a validação e falhar a verificação.

**5. Porque é que a sugestão de coluna (`orders.total_amount`) não é executada?**
Porque é uma sugestão para o utilizador ou para o modelo corrigir. Qualquer correcção automática teria de passar de novo pela validação e pelo executor; por isso o sistema só mostra a sugestão.

**6. Como medirias a precisão destas regras?**
Com as perguntas golden da avaliação (tarefa 7): para cada consulta sabemos se tem fan-out ou se a métrica está errada, por isso contamos falsos positivos e negativos por categoria.
