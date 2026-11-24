# 05 — Row-Level Security por vendedor

## O problema

O Kianda Market é multi-vendedor: cada `seller_id` é um tenant e um vendedor não pode ver as encomendas de
outro. Um LLM que gera SQL pode, por erro ou por injecção, escrever `WHERE seller_id = 2`, ou simplesmente
esquecer o filtro. Se o isolamento depender do SQL gerado, **o isolamento é uma sugestão**.

Queremos que o isolamento seja uma garantia da base de dados, aplicada a cada linha, **e** que nenhum SQL da
sessão consiga mudar de vendedor.

## O que entra e o que sai

Entra: o SQL gerado, e a ligação do executor, que é um role de login por vendedor (`qs_reader_s1`, `_s2`, `_s3`).
Sai: apenas as linhas desse vendedor.

Saída real registada depois da migração 006 (antes da 007):

```
user: [('qs_reader_s1',)]
orders seller visibility: [(700, 1, 1)]
mapping: [('qs_reader_s1', 1), ('qs_reader_s2', 2), ('qs_reader_s3', 3)]
SET app.seller_id = '2'                    -> ok
SET ROLE qs_app                            -> ERR InsufficientPrivilege: permission denied to set role "qs_app"
RESET ROLE                                 -> ok
SET SESSION AUTHORIZATION postgres         -> ERR InsufficientPrivilege: permission denied to set session authorization
SET ROLE qs_reader_s2                      -> ERR InsufficientPrivilege: permission denied to set role "qs_reader_s2"
SELECT set_config('app.seller_id','2',true) -> ERR InsufficientPrivilege: permission denied for function set_config
SELECT count(*) FROM qs_private.internal_fraud_flags -> ERR InsufficientPrivilege: permission denied for table internal_fraud_flags
after attacks, visibility: [(700, 1, 1)] user: [('qs_reader_s1',)]
insert: ERR ReadOnlySqlTransaction: cannot execute INSERT in a read-only transaction
```

Leitura: `SET app.seller_id = '2'` executa, mas não muda nada. A visibilidade continua nas 700 linhas do
vendedor 1 depois de todos os ataques.

## Como funciona por dentro

**Identidade = role.** Cada vendedor tem um role de login, `qs_reader_s<N>`, criado em
`db/migrations/006_per_seller_roles.sql`. Estes roles são `NOINHERIT` e não são membros de nenhum outro role.
Por isso `SET ROLE`, `SET SESSION AUTHORIZATION` e `RESET ROLE` não lhes dão outra identidade.

**Mapeamento.** `qs_private.seller_roles(role_name, seller_id)` diz qual é o vendedor de cada role. Os roles de
vendedor têm `SELECT` nesta tabela (e `USAGE` no schema), e nada mais em `qs_private`.

**Política.** Cada tabela de negócio tem uma política que compara o `seller_id` da linha com o vendedor do
role corrente, lido do mapeamento:

```sql
USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m
                    WHERE m.role_name = session_user))
```

`session_user` é a identidade de login original. É usada deliberadamente porque as políticas RLS de
tabelas subjacentes a uma vista normal são aplicadas com os privilégios do dono da vista; a identidade
de login mantém-se a do vendedor. Assim a política funciona também ao ler pelas vistas `qs_api`.
**Limite da evidência:** a migração 007 aplica esta alteração final, mas ainda não foi executada contra
PostgreSQL nesta revisão; a saída acima não confirma o estado pós-007.

**`FORCE ROW LEVEL SECURITY`.** Sem `FORCE`, o dono das tabelas (`qs_app`, dono das vistas) contornaria a
política. O teste `test_owner_role_is_subject_to_rls_because_of_force` verifica que, como `qs_app`, sem mapeamento
o resultado é zero linhas.

**Superusers.** Contornam RLS. Por isso as migrações e o seed correm com a ligação administrativa, e o executor
nunca usa uma ligação de superuser.

**Âmbito de pedido.** `qs_api.begin_request(timeout_ms)` só define o `statement_timeout` local à transacção.
Já não recebe nem define o tenant. A identidade vem do role, e não de uma definição de sessão.

## Porquê esta escolha

- **A base de dados decide, com um critério que o SQL não controla.** `session_user` é definido pela
  autenticação da ligação, não pelo texto do SQL nem pelo contexto do dono da vista.
- **Sem definições de sessão que o SQL possa alterar.** Antes (migrações 003 a 005) o tenant era `app.seller_id`,
  e qualquer `SET` no mesmo transacção o mudava. Esse caminho foi removido (achado A1 de `docs/security-review.md`).
- **Fail-closed.** Um role sem linha no mapeamento não vê nada.
- **Um pool por vendedor no executor.** Cada pool só tem as credenciais de um role. Um bug que escolha o pool
  errado dá um vendedor errado, mas não consegue mudar a identidade de uma ligação já aberta.

## Alternativas

- **Definição de sessão com `set_config`** (a versão anterior). Qualquer SQL na mesma sessão a muda. Descartada.
- **Tenant guardado numa tabela privada, escrita por função** (tentativa exploratória anterior). A escrita
  falha em transacções só de leitura. Exigiria duas transacções por pedido e um token. Descartada em favor dos roles.
- **Uma base de dados por vendedor.** Isolamento forte, custo operacional alto.
- **Filtrar `seller_id` no SQL gerado.** Depende do SQL. Não é uma garantia.

## Como falha (e o que ficou por resolver)

Testes em `tests/postgres/test_roles_rls.py`:

- Roles de login, sem superuser, sem bypass de RLS, sem herança e sem membership:
  `test_seller_roles_are_login_roles_that_inherit_nothing`.
- Cada vendedor vê só as suas linhas: `test_seller_sees_only_its_own_rows`,
  `test_each_seller_role_sees_only_its_own_rows`.
- Ataques de sessão com o validador desligado (`SET`, `SET ROLE`, `RESET ROLE`, `SET SESSION AUTHORIZATION`,
  `set_config`, `begin_request`): `test_raw_session_attacks_cannot_change_visibility`.
- Cada tabela de negócio tem RLS activa, forçada e uma política: `test_every_business_table_has_rls_enabled_and_forced`.

**Residual.** Quem já executa instruções de topo como `qs_reader_s1` continua a ver as 700 linhas do vendedor 1 e
nenhuma de outro, porque o role não muda. Não há caminho, por SQL, para a identidade de outro vendedor. O que
continua a depender do executor e do validador é a *forma* da consulta (produtos cartesianos, funções lentas);
ver `docs/learn/09-defesa-em-profundidade.md`.

## Perguntas de entrevista

**1. Porque é que RLS é mais forte do que um filtro no SQL?**
Porque é aplicada pelo motor a cada linha, depois de o planeador decidir o plano, e não depende do texto SQL.

**2. Porque é que a identidade é um role e não uma variável de sessão?**
Porque uma variável de sessão pode ser alterada por qualquer `SET` na mesma sessão. Um role só muda por
`SET ROLE`, que exige membership, e os roles de vendedor não têm nenhuma.

**3. O que é `FORCE ROW LEVEL SECURITY` e quando é que o dono importa?**
Aplica a política também ao dono da tabela. Importa quando as vistas são do dono e o reader lê através delas.

**4. Porque é que a RLS usa `session_user`?**
O acesso às tabelas por uma vista normal avalia as políticas no contexto do dono da vista. `session_user`
continua a identificar o login original do vendedor; `current_user` pode reflectir o papel efectivo. A
migração 007 torna explícita esta escolha.

**5. O que acontece a um role sem linha no mapeamento?**
Não vê nenhuma linha: a comparação com `NULL` é falsa. É fail-closed.

**6. Como é que o tenant não vaza entre pedidos no pool?**
Cada pool só tem as credenciais de um role, e o role de uma ligação não muda. Não há estado de tenant na sessão.

**7. Porque é que os superusers não são usados pelo executor?**
Porque contornam RLS. As migrações e o seed precisam de escrever em todos os vendedores, e por isso usam a ligação
administrativa, separada do executor.

**8. Qual é o limite residual deste desenho?**
A base de dados garante a identidade, não a forma da consulta. Um SQL que escape ao validador e aos limites
continua a ver só as linhas do seu vendedor, mas pode ser caro. Para isso existem o `statement_timeout`, o prazo da
aplicação e o limite de linhas.
