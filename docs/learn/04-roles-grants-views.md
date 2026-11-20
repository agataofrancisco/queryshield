# 04 — Roles, grants e vistas

## O problema

Um LLM que escreve SQL é um utilizador não confiável. Mesmo que o validador AST falhe, a base de dados tem de recusar o que não deve. A pergunta é: **que privilégios tem a ligação que executa o SQL gerado?**

Se a aplicação ligasse à base de dados com o utilizador dono das tabelas (ou com um superuser), qualquer `DROP`, `UPDATE` ou leitura de `internal_fraud_flags` que passasse o validador seria executado. A resposta do QueryShield é uma ligação dedicada, com o menor privilégio possível, cujo único poder é ler um conjunto pequeno de vistas.

## O que entra e o que sai

Entra: um pedido SQL gerado e um tenant (`app.seller_id`) definido pelo servidor. Sai: linhas, ou um erro de privilégio **da base de dados**, independente do validador.

Saída real (executada contra a base de desenvolvimento, ligação `qs_reader`):

```
1 utilizador/ro/search_path: [('qs_reader', 'on', 'qs_api')]
2 orders sem tenant: [(0,)]
3 orders com tenant 1: [(700, 1, 1)]
4 orders WHERE seller_id=2: [(0,)]
5 tabela secreta: ERRO InsufficientPrivilege: permission denied for schema qs_private
6 email em customers: ERRO UndefinedColumn: column "email" does not exist
7 colunas customers: [('id',), ('seller_id',), ('full_name',)]
8 UPDATE: ERRO ReadOnlySqlTransaction: cannot execute UPDATE in a read-only transaction
9 DROP: ERRO ReadOnlySqlTransaction: cannot execute DROP TABLE in a read-only transaction
10 pg_sleep (DB nao bloqueia; validador bloqueia): [('',)]
```

Repare na linha 10: a base de dados **não** bloqueia `pg_sleep`. Essa protecção é do validador. Cada camada tem o seu papel; nenhuma substitui a outra.

## Como funciona por dentro

Três ficheiros de migração definem o modelo:

- `db/migrations/001_roles.sql:12-15` cria `qs_app` (NOLOGIN, dono de todos os objectos) e `qs_reader` (LOGIN, NOINHERIT, NOBYPASSRLS, NOSUPERUSER).
- `db/migrations/001_roles.sql:22-26` define, **por role**, `default_transaction_read_only = on`, `search_path = qs_api` e `statement_timeout = '3s'`. Estas definições aplicam-se a cada nova ligação, mesmo que o código da aplicação se esqueça de as pedir.
- `db/migrations/002_schema.sql` põe as 10 tabelas no schema `qs_private`. Este schema não tem `USAGE` para `qs_reader` (`004_views.sql`, `REVOKE ALL ON SCHEMA qs_private FROM PUBLIC`). Por isso `qs_reader` nem sequer consegue escrever `qs_private.orders`: a resposta do PostgreSQL é "permission denied for schema qs_private" (linha 5 acima).
- `db/migrations/004_views.sql:14-41` cria as vistas em `qs_api` com **colunas explícitas**. `customers` (linha 20) não tem `email` nem `phone`: a coluna não existe para o reader, por isso nem uma sintaxe criativa a revela (linha 6 acima).
- `db/migrations/004_views.sql` termina com `GRANT SELECT ... TO qs_reader` apenas sobre as vistas. `internal_fraud_flags` não tem vista e não tem grant.

Porque é que o `search_path = qs_api` importa: o SQL gerado escreve `FROM orders`. Esse nome resolve para `qs_api.orders` (a vista), não para o `qs_private.orders` (a tabela base). A semantic layer e o SQL usam os mesmos nomes amigáveis e o acesso real fica limitado pela base de dados.

## Porquê esta escolha

- **Menor privilégio por construção.** O reader só recebe `SELECT` em vistas. Não há `GRANT` em tabelas base. Mesmo com um bug no validador, não há tabela para ler além das vistas.
- **PII fora do alcance do executor.** Um filtro de colunas na aplicação pode ser contornado por um `SELECT *` mal pensado ou por uma vista antiga. Uma coluna que não existe na vista não pode ser lida por nenhum SQL. Esta é a camada mais forte.
- **Defesa em profundidade com role-level defaults.** `default_transaction_read_only` no role significa que uma transacção esquecida continua em leitura.
- **`security_barrier = true` nas vistas.** Impede que uma função ou operador escolhido pelo SQL gerado observe linhas antes do filtro da vista/RLS (um vector clássico de fuga com funções não-leakproof).

## Alternativas

- **Grants por coluna nas tabelas base** (`GRANT SELECT (id, city) ON customers`). Funciona, mas a regra fica espalhada pelo catálogo e é difícil de rever. As vistas tornam a superfície visível num ficheiro (`004_views.sql`).
- **Um role de leitura por persona** (`qs_analyst`, `qs_finance`). Dá separação de papéis também na base de dados. Não foi escolhida: o `qs_reader` único com vistas PII-free reduz a superfície, e a diferença de papéis (payouts só para finance) fica no validador. Esta limitação está documentada em `docs/decisions.md`.
- **Usar apenas o validador.** Já vimos (linha 10) que o SQL pode chamar funções com efeitos. A base de dados é a última linha.

## Como falha

Cada afirmação tem um teste em `tests/postgres/test_roles_rls.py`:

- Role não superuser, sem bypass de RLS, read-only por omissão, `search_path = qs_api`: `test_reader_is_a_non_superuser_read_only_role`.
- Sem grants em tabelas base nem na tabela secreta: `test_reader_has_no_privileges_on_base_tables_or_secret_table`.
- Sem vista pública para a tabela secreta: `test_secret_table_has_no_public_view`.
- `customers` sem PII (verificado em `information_schema`): `test_customers_view_has_no_pii_columns`.
- Escrita recusada em transacção read-only: `test_writes_are_refused_in_a_read_only_transaction`.
- Mesmo com `READ WRITE` pedido, não há privilégio: `test_writes_are_refused_even_when_read_write_is_requested`.
- `qs_app` não pode fazer login: `test_qs_app_cannot_log_in`.

Modo de falha que **não** é coberto pela base de dados: uma função de sistema que não exige privilégios (ex.: `pg_sleep`). Essa coberta pelo validador (`function_not_allowed`, tarefa 3.1) e pelo `statement_timeout`.

## Perguntas de entrevista

**1. Porque é que o executor não usa o utilizador da aplicação?**
Porque o utilizador da aplicação tem privilégios de escrita para a gestão de dados. A ligação do executor é um role separado, sem escrita e sem tabelas base. Se o SQL gerado escapar do validador, o máximo que consegue é ler as vistas do seu tenant.

**2. Porque é que as vistas são de `qs_app` e não de `qs_reader`?**
Porque uma vista de `qs_app` é executada com os privilégios do dono. Assim o `qs_reader` não precisa de nenhum privilégio nas tabelas base, só na vista. Isto é também a razão pela qual a RLS tem de ter `FORCE` (ver doc 05).

**3. O que é `security_barrier` e porque o usamos?**
É uma opção de vista que impede o planeador de empurrar funções ou operadores do utilizador para antes dos filtros da vista. Sem ela, uma função não-leakproof pode observar linhas de outro tenant em casos de erro. Com ela, a ordem de avaliação respeita a barreira de segurança.

**4. Porque é que `ALTER ROLE ... SET` é melhor do que definir o `search_path` na ligação?**
Porque a definição fica no catálogo e aplica-se a qualquer ligação desse role, incluindo ligações de outros programas ou ferramentas. Um esquecimento no código da aplicação não abre o schema privado.

**5. Um SQL gerado pode fazer `SET ROLE` para subir de privilégio?**
Não, porque o `qs_reader` não é membro de nenhum role com privilégios: não há `GRANT qs_app TO qs_reader`. Isto é verificável em `pg_auth_members`. Além disso, o validador rejeita `SET` (ver doc 03).

**6. Porque é que a password não está nas migrações?**
Porque as migrações ficam no git. A password é definida por `db/migrate.py` a partir de `QS_READER_PASSWORD` (`db/migrate.py`, função `apply_migrations`). Assim um repositório público não contém credenciais.

**7. Qual é a diferença entre `REVOKE ALL ... FROM PUBLIC` e não dar grants?**
Por omissão o `PUBLIC` tem alguns privilégios (por exemplo `CONNECT` e `EXECUTE` em funções). Para schemas não-public o `PUBLIC` não tem `USAGE`, mas o `REVOKE` explícito torna a intenção visível e protege contra alterações futuras de defaults.

**8. Se tivesse de separar `seller_analyst` e `seller_finance` na base de dados, o que faria?**
Criaria roles `NOLOGIN` de grupo (`qs_analyst`, `qs_finance`) com grants diferentes sobre as vistas, e o executor faria `SET LOCAL ROLE` com o papel do token. Teria de garantir que `qs_reader` não pode trocar de role por SQL, o que implica validar `SET` e `RESET` no validador e manter o role sem `GRANT` a outros roles.
