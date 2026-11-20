# 05 — Row-Level Security por vendedor

## O problema

O Kianda Market é multi-vendedor: cada `seller_id` é um tenant e um vendedor não pode ver as encomendas de outro. Um LLM que gera SQL pode, por erro ou por injecção, escrever `WHERE seller_id = 2`, ou simplesmente esquecer o filtro. Se o isolamento depender de o SQL gerado incluir o filtro certo, **o isolamento é uma sugestão**.

Queremos que o isolamento seja uma garantia da base de dados, aplicada a cada linha, independentemente do SQL.

## O que entra e o que sai

Entra: o SQL gerado e o tenant autenticado, definido pelo servidor com `set_config('app.seller_id', ..., true)`. Sai: apenas as linhas desse tenant.

Saída real (ligação `qs_reader`, mesma base de desenvolvimento):

```
2 orders sem tenant: [(0,)]
3 orders com tenant 1: [(700, 1, 1)]
4 orders WHERE seller_id=2: [(0,)]
```

- Sem tenant definido, a consulta devolve **zero** linhas (fail-closed). Não há erro e não há fuga.
- Com tenant 1, o `min` e o `max` de `seller_id` são ambos 1. O filtro `seller_id = 2` escrito pelo SQL gerado não mostra nada que não seja do tenant 1.

## Como funciona por dentro

- `db/migrations/003_rls.sql:14-17` define `qs_private.current_seller_id()`: lê `app.seller_id` com `current_setting(..., true)` (missing_ok) e devolve `NULL` quando não está definido ou é vazio. `NULL` nunca é igual a um `seller_id`, por isso a política dá falso sem erro.
- `003_rls.sql:20-21` activa RLS e **`FORCE ROW LEVEL SECURITY`** em cada tabela de negócio. A política é `USING (seller_id = qs_private.current_seller_id())` e o mesmo predicado em `WITH CHECK`, para que escritas (que não existem para o reader) também fiquem limitadas ao tenant.
- O executor (tarefa 4.2) faz `SELECT set_config('app.seller_id', %s, true)` **dentro** da transacção. O terceiro argumento `true` torna a definição local à transacção: no commit ou rollback volta a `''`. Esta é a propriedade que torna o pool de ligações seguro (ver teste abaixo).
- O `SET LOCAL app.seller_id = %s` não serve, porque `SET` não aceita parâmetros ligados. `set_config` é a forma parametrizada.

### Porque é que `FORCE` é necessário

Sem `FORCE`, o dono de uma tabela contorna RLS. As vistas de `qs_api` pertencem a `qs_app`, que é dono das tabelas base. Sem `FORCE`, uma consulta a `qs_api.orders` executada por `qs_reader` seria avaliada com os privilégios do dono e **não aplicaria a política**. O teste `test_owner_role_is_subject_to_rls_because_of_force` prova o contrário: com `SET LOCAL ROLE qs_app`, sem tenant, a contagem é 0.

Os superusers continuam a contornar RLS. Por isso `db/seed.py` e `db/migrate.py` correm com a ligação administrativa, e o executor **nunca** usa uma ligação de superuser.

## Porquê esta escolha

- **Garantia na base de dados.** A política é avaliada em cada linha, para qualquer SQL, incluindo subqueries, CTEs e joins. O SQL não precisa de cooperar.
- **Fail-closed.** Sem tenant, nada. Um bug que esqueça de definir o tenant falha de forma visível (zero linhas) e não expõe dados.
- **`set_config(..., true)` com pool.** O tenant é local à transacção, por isso não vaza para o próximo pedido que reutiliza a mesma ligação.
- **`WITH CHECK` mesmo sem escrita.** Se um dia o reader ganhar escrita por engano, a política continua a limitar as linhas escritas.

## Alternativas

- **Filtrar `seller_id` na aplicação** (acrescentar `WHERE seller_id = ...` ao SQL). Frágil: depende do validador ou de uma reescrita de AST, e falha com subqueries e joins mal feitos.
- **Uma base de dados por vendedor.** Isolamento forte, mas custo operacional alto e não escala para um marketplace.
- **Views por vendedor** (`WHERE seller_id = current_setting(...)` na própria vista). Funciona, mas cada alteração de schema obriga a recriar vistas e a RLS já expressa o mesmo predicado de forma centralizada.

## Como falha

Testes em `tests/postgres/test_roles_rls.py`:

- Sem tenant, zero linhas: `test_reader_without_tenant_sees_no_rows`.
- Apenas o tenant autenticado é visível, comparado com a contagem calculada pelo superuser: `test_reader_sees_only_the_authenticated_tenant`.
- Filtro manual para outro tenant devolve zero: `test_sql_that_filters_another_tenant_returns_nothing`.
- Tenant não vaza entre transacções da mesma ligação: `test_tenant_does_not_leak_to_the_next_transaction`.
- Dono sujeito a RLS por causa de `FORCE`: `test_owner_role_is_subject_to_rls_because_of_force`.

Modo de falha conhecido: se um dia uma tabela for criada **sem** `ENABLE` e `FORCE`, o isolamento não existe para essa tabela. Por isso o teste `test_every_business_table_has_rls_enabled_and_forced` verifica no catálogo que as 10 tabelas têm RLS activa, forçada e com uma política.

## Perguntas de entrevista

**1. Porque é que RLS é mais forte do que um filtro no SQL?**
Porque é aplicada pelo motor a cada linha, depois de o planeador ter decidido o plano, e não depende do texto SQL. Um `OR 1=1`, uma subquery ou um `UNION` não a contornam.

**2. O que é `FORCE ROW LEVEL SECURITY` e quando é que o dono importa?**
Por omissão, o dono da tabela não é afectado por RLS. `FORCE` aplica a política também ao dono. Importa quando as vistas são do dono e o reader lê através delas.

**3. Porque é que `set_config(..., true)` e não `SET`?**
`SET` não aceita parâmetros ligados em PostgreSQL, por isso não é seguro concatenar o `seller_id` (injecção). `set_config` é uma função e aceita parâmetros. O terceiro argumento `true` torna-o local à transacção.

**4. O que acontece ao tenant se a transacção falhar?**
É revertido junto com a transacção. Não é preciso limpar nada.

**5. Porque é que o teste de não-vazamento usa a mesma ligação?**
Porque é o cenário real de um pool: as ligações são reutilizadas. Um teste com ligações novas não prova nada sobre reutilização.

**6. Porque é que `current_seller_id()` é `STABLE` e não `IMMUTABLE`?**
Porque lê uma definição de sessão. `IMMUTABLE` permitiria ao planeador reutilizar o resultado entre tenants, o que seria incorrecto.

**7. O superuser está sujeito a RLS?**
Não. Por isso o executor nunca usa uma ligação de superuser, e o seed e as migrações (que precisam de escrever em todos os tenants) usam a ligação administrativa separadamente.

**8. Como provaria que o isolamento não depende do SQL gerado?**
Com um teste de pedido explícito de outro tenant (`WHERE seller_id = 2`) e com o validador desligado: o resultado continua a ser só o do tenant autenticado. Esse teste é o da tarefa 4.2 (executor com validador desligado), ainda por implementar.
