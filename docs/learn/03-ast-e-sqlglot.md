# 03 — Validação AST com SQLGlot

## O problema

O SQL gerado por um LLM é texto não confiável. Antes de chegar à base de dados, precisamos de decidir: é uma leitura simples, permitida e inequívoca?

A tentação é usar expressões regulares ("não pode conter `DROP`", "tem de começar por `SELECT`"). Os exemplos abaixo mostram porque isso não funciona.

## O que entra e o que sai

Entra: uma string SQL, o papel do utilizador, o modelo semântico e os parâmetros nomeados. Sai: um `ValidationResult` com `ok`, uma lista de `Issue` (código, mensagem, sugestão), o SQL canónico, o hash SHA-256 e as tabelas, funções e joins usados.

Saída real do validador, com a mesma biblioteca e o mesmo papel (`seller_finance`):

```
SELECT 1; DROP TABLE orders -> False ['multiple_statements']
SELECT 1; TRUNCATE orders -> False ['multiple_statements']
SELECT 'DROP TABLE' AS aviso FROM orders LIMIT 1 -> True []
```

E a resposta HTTP real de `POST /query/validate` para um erro de digitação, com sugestão:

```json
{"ok":false,"issues":[{"code":"unknown_column","message":"Coluna inexistente: total_value.","suggestion":"orders.total_amount"}],"tables_used":["orders"]}
```

## Como funciona por dentro

1. **Normalização.** `normalize_sql` (`backend/app/validation/ast_validator.py:68`) remove espaços e `;` finais. Não reescreve o SQL.
2. **Parse PostgreSQL.** `sqlglot.parse(canonical, read="postgres")`. Um erro de parse vira `parse_error`. Um resultado com mais de uma instrução vira `multiple_statements` (`validate_sql`, linha ~110).
3. **Raiz.** Só `Select` ou `Union`. Qualquer outra raiz (`Insert`, `Command` de `SET` ou `EXPLAIN`) vira `statement_not_allowed`.
4. **Nós proibidos** (`_check_forbidden`, linha ~218). Percorre **todos** os nós da árvore com a lista `FORBIDDEN_NODES` de `backend/app/validation/policy.py`. Comparação por tipo exacto (`type(node) in ...`), não por herança. Um nó de escrita dentro de um `CTE` é `write_in_cte`; fora, `forbidden_operation`.
5. **Tabelas** (`_check_tables`, linha ~227). Cada `exp.Table` tem de estar na lista visível ao papel. Nomes qualificados por schema (`qs_private.orders`, `pg_catalog.pg_user`) são recusados. Nomes de `CTE` são referências internas e passam (o conteúdo do CTE é verificado à parte).
6. **Colunas** (`_check_columns`, linha ~256). Colunas qualificadas são resolvidas por alias. Colunas não qualificadas têm de existir numa das tabelas da consulta. Se a coluna existe mas não é visível ao papel, é `column_not_allowed`; se não existe, `unknown_column` com sugestão por `difflib.get_close_matches` (linha ~419).
7. **Funções** (`_check_functions`, linha ~303). Deny-by-default: `exp.Anonymous` (funções que o sqlglot não conhece, como `pg_sleep`) são recusadas. Outras `exp.Func` só passam se estiverem em `ALLOWED_FUNCTIONS`. Operadores (`AND`, `OR`, `EQ`) são também `Func` em sqlglot, por isso há uma lista separada `OPERATOR_NODES`.
8. **Joins** (`_check_joins` e `_check_on`, linhas ~331 e ~350). Um join sem condição (`CROSS JOIN`, lista `FROM a, b`) é `cartesian_product`. Uma condição ON só é aceite se for uma **conjunção** (`AND`) de igualdades entre colunas, cada uma existente em `semantic/schema.yaml`. Uma igualdade com literal é um filtro e passa. Qualquer outra coisa, incluindo `OR`, é `join_not_allowed`.
9. **Limite.** `_check_limit_or_aggregation` (linha ~390): a consulta externa tem de ter `LIMIT`, `FETCH`, `GROUP BY` ou uma agregação.
10. **Parâmetros** (`_check_placeholders`, linha ~404). `%s` e `?` são posicionais e recusados. `%(nome)s` tem de ter o valor correspondente.

## Porquê esta escolha

Os exemplos reais abaixo estão em `tests/unit/test_regex_vs_ast.py` e são executados em cada teste.

| Caso | Regra A: "começa por SELECT" | Regra B: lista negra de palavras | AST |
|---|---|---|---|
| `SELECT 1; DROP TABLE orders` | deixa passar | bloqueia | bloqueia (`multiple_statements`) |
| `SELECT 1; TRUNCATE orders` | deixa passar | **deixa passar** (`TRUNCATE` não está na lista) | bloqueia |
| `WITH t AS (...) SELECT ...` (legítimo) | **bloqueia** | deixa passar | deixa passar |
| `SELECT 'DROP TABLE' AS aviso ...` | deixa passar | **bloqueia** (falso positivo: é texto) | deixa passar |
| `SELECT ... /* DROP TABLE orders */` | deixa passar | **bloqueia** (falso positivo: comentário) | deixa passar |

Conclusão: uma regra textual erra nos dois sentidos. Uma lista negra nunca está completa, e bloqueia texto que não é código. O AST responde à pergunta certa: "que operações esta árvore faz?".

- **Comentários, maiúsculas e strings não enganam.** `/* ; DROP */` é um comentário no parse, não uma segunda instrução.
- **Enumeração por tipo de nó, não por palavra.** `TRUNCATE` vira um nó que não é `Select`, por isso cai em `statement_not_allowed` sem estar em nenhuma lista de palavras.

## Alternativas

- **Regex / lista negra.** Ver tabela acima.
- **`sqlparse`.** Tokeniza, mas não dá uma árvore semântica confiável para resolver colunas e joins.
- **Só `EXPLAIN` na base de dados.** Dá o plano, mas não diz se a consulta usa colunas proibidas nem se o join é permitido, e não sugere correcções.
- **Escrever um parser próprio.** Não se justifica: o SQLGlot já tem um dialecto PostgreSQL com testes extensos.

## Como falha

Limites conhecidos, cada um com teste ou nota:

- **O SQLGlot pode analisar diferente do PostgreSQL** em casos raros. Por isso a base de dados é a última barreira (doc 04, doc 05) e os testes de ataque (`test_validator.py`) correm contra o validador.
- **Subqueries derivadas em joins**: a condição ON com uma subquery só é aceite se a coluna real participar numa aresta permitida. A subquery interna é validada, mas não se prova que a sua saída é uma relação permitida. É um limite conhecido.
- **Falso positivo de limite**: `SELECT name FROM sellers WHERE id = 1` é recusado (sem `LIMIT`), e `SELECT x.n FROM (SELECT COUNT(*) AS n FROM orders) x` também, porque a consulta externa não agrega. É uma escolha de segurança, documentada.
- **Cruzamentos por lista `FROM a, b` com `WHERE`** são recusados, mesmo quando o `WHERE` os torna um join interno. Preferimos recusar a aceitar um produto cartesiano por engano.

Testes: `tests/unit/test_validator.py` (cada ataque da spec com o código esperado, consultas válidas, endpoint e registo) e `tests/unit/test_regex_vs_ast.py`.

## Perguntas de entrevista

**1. Porque não basta uma regex com `DROP|DELETE|UPDATE`?**
Porque é uma lista finita (esquece `TRUNCATE`), não distingue código de texto (bloqueia `'DROP'` num literal) e não vê comentários. Ver a tabela acima.

**2. O que é um AST e porque é que o validador o usa?**
É a árvore sintáctica do SQL: cada operação, tabela, coluna e função é um nó com tipo. Validar um AST é perguntar "que nós existem?" e não "que palavras aparecem?".

**3. Porque é que `OR` e `AND` aparecem como `Func`?**
Porque no sqlglot os operadores são subclasses de `Func`. Se a allowlist de funções fosse aplicada sem excepção, `AND` seria recusado. Por isso há uma lista separada (`OPERATOR_NODES`).

**4. Porque é que a comparação de tipos é exacta e não por `isinstance`?**
Porque algumas classes do sqlglot herdam de outras (`Union` não é `Set`, mas isso podia mudar). Com `type(node) in FORBIDDEN_NODES`, uma alteração de hierarquia não cria falhas de bloqueio inesperadas. Um teste confirma a hierarquia actual.

**5. O que acontece com uma função que o sqlglot não conhece?**
Vira `exp.Anonymous` e é recusada por omissão. É deny-by-default: só o que está explicitamente permitido passa.

**6. Porque se executa o SQL original validado e não a versão reescrita pelo sqlglot?**
O sqlglot reescreve `%(nome)s` como `:nome`. O que se valida tem de ser exactamente o que se executa. O hash regista o texto canónico validado.

**7. Porque é que o validador devolve sugestões (`orders.total_amount`)?**
Porque o modelo erra nomes de colunas com frequência. Uma sugestão baseada em distância de edição melhora a correcção em retry sem aumentar a superfície: a sugestão nunca é executada, só mostrada.

**8. Qual é o limite mais importante do validador?**
A divergência entre o parser do SQLGlot e o do PostgreSQL. Por isso a validação é uma camada, não a garantia final: a RLS e o role de leitura continuam a proteger quando o parser se engana.
