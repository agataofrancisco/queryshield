# Design

## Context

O repositório está vazio. Motivação: ver `proposal.md`. Requisitos: ver `specs/`. Este projecto **exige PostgreSQL real**: RLS, roles, `statement_timeout` e transacções só de leitura não têm equivalente fiel em SQLite. Sem Docker, instala-se o Postgres nativamente (ou portable) no Windows, e no CI usa-se um service container.

## Goals / Non-Goals

**Goals:**
- Defesa em profundidade com camadas independentes e testadas individualmente: autorização da aplicação → schema mínimo no prompt → AST → role/RLS/timeout na base de dados.
- Correcção medida por resultado executado (execution accuracy), não por igualdade textual do SQL.

**Non-Goals:**
- Fine-tuning de modelos Text-to-SQL, ou benchmarks públicos completos (BIRD/Spider). O BIRD é citado como referência de metodologia.
- Escrita, escalonamento de queries pesadas e caching de resultados.

## Decisions

### D1 — Modelo de dados do seed
Tabelas: `sellers`, `customers`, `products`, `categories`, `orders`, `order_items`, `returns`, `payments`, `payouts` e `internal_fraud_flags` (secreta). Todas as tabelas de negócio têm `seller_id`. Há FKs e constraints. O seed é determinístico (seed fixa) com ~3 vendedores, ~2 000 encomendas e 12 meses, e inclui casos difíceis: devoluções parciais, encomendas canceladas e moeda.

### D2 — Roles e RLS
- `qs_app` é dono das tabelas e faz a gestão (migrações, seed).
- `qs_reader` tem `SELECT` só nas views/colunas permitidas, sem acesso a `internal_fraud_flags`, e `default_transaction_read_only = on`.
- Uma policy RLS em cada tabela: `USING (seller_id = current_setting('app.seller_id'))`. O executor faz `SET LOCAL app.seller_id = $1` numa transacção com o valor da sessão autenticada.
- As colunas de PII são removidas por **views por papel** (`v_customers_analyst` sem email/telefone) e `GRANT` só nas views, porque os grants por coluna mais RLS ficam difíceis de explicar. A semantic layer expõe as views com nomes amigáveis.
- Tema de entrevista: porque é que `SET LOCAL` dentro da transacção é importante com pools de ligações.

### D3 — Semantic layer em YAML
`semantic/metrics.yaml` (nome, SQL canónico, filtros, unidade, descrição) e `semantic/schema.yaml` (tabelas/colunas por papel, joins permitidos). Serve para o prompt, a validação, a verificação e o `GET /schema/semantic`. Uma só fonte de verdade.

### D4 — Geração
O LLM recebe o schema por papel + as métricas + exemplos few-shot e devolve JSON `{sql, parameters, metrics_used, tables_used, assumptions, rationale, needs_clarification?}`. Os parâmetros usam placeholders `%(name)s`, ligados pelo psycopg (sem interpolação de strings).

### D5 — Validação SQLGlot
`sqlglot.parse(sql, read="postgres")`: exactamente 1 expressão, raiz `Select` (ou `Union` de Selects). Percorre a árvore: os nós proibidos (`Insert`, `Update`, `Delete`, `Merge`, `Create`, `Drop`, `Alter`, `Command`, `Transaction`, `Set`…) rejeitam. `exp.Table` tem de estar na allowlist, `exp.Column` é resolvida contra as tabelas (com aliases), `exp.Func`/`Anonymous` tem de estar na allowlist de funções, e os joins são comparados com os caminhos permitidos. Há também detecção de produto cartesiano e a exigência de LIMIT/agregação.
- *Porquê AST e não regex:* comentários, maiúsculas e strings enganam regex. É uma boa pergunta de entrevista.
- *Limitação:* o SQLGlot pode fazer parse de forma diferente do Postgres em casos raros. Por isso a base de dados é a última barreira.

### D6 — Verificação
- `metric_definition_mismatch`: compara os filtros e a agregação do SQL com a definição canónica (presença de predicados obrigatórios na AST).
- `possible_fanout`: `SUM`/`COUNT` sobre uma tabela "1" juntada a uma "N" sem pré-agregação.
- `unknown_column`: resolução contra o schema, com sugestão por distância de edição.
- Comparação com golden: só na avaliação. Em runtime, os resultados de perguntas idênticas a golden são verificados.

### D7 — Execução
Um pool psycopg separado com `qs_reader`. Por pedido: `BEGIN READ ONLY; SET LOCAL statement_timeout = '3s'; SET LOCAL app.seller_id = ...; <query com LIMIT forçado>; COMMIT`. Um `hash(sql_normalizado)` validado é guardado na sessão/histórico para `not_validated`.

### D8 — Avaliação
`eval/questions.jsonl` (pergunta, papel, vendedor, SQL golden, categoria). Os resultados esperados são gerados executando o golden como o mesmo papel. A normalização de resultados: multiconjunto de linhas quando não há `ORDER BY` pedido, arredondamento a 2 casas e coerção numérica. O runner regista também a camada que travou cada ataque, executando com o validador ligado e desligado.

### D9 — Frontend
React (Vite) com chat, editor read-only com highlight (CodeMirror), tabela, gráfico (Recharts), cartões de aviso e explain.

### D10 — Documentação pedagógica
`docs/learn/` tem: `00-visao-geral`, `01-semantic-layer`, `02-text-to-sql-com-llms`, `03-ast-e-sqlglot`, `04-roles-grants-views`, `05-row-level-security`, `06-timeouts-e-limites`, `07-alucinacoes-sql-e-fanout`, `08-execution-accuracy`, `09-defesa-em-profundidade` e `10-perguntas-de-entrevista`.

## Risks / Trade-offs

- [Sem Postgres local, não há prova de RLS] → Instalação nativa documentada. Os testes `-m postgres` são obrigatórios em CI e o relatório indica se correram.
- [Views por papel duplicam a manutenção] → São geradas a partir de `schema.yaml`.
- [A verificação heurística falha em SQL complexo] → É reportada como aviso. A avaliação mede os falsos positivos e negativos.
- [O LLM gera SQL correcto mas diferente do golden] → A execution accuracy compara resultados, não texto.

## Migration Plan

Projecto novo. Migrações SQL versionadas (schema, roles, RLS, views) e seed determinístico. Deploy documentado: backend em containers, Postgres gerido com roles criados por migração, e o endpoint de execução **nunca** público sem autenticação.
