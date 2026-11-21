# 06 — Timeouts, limites e o caminho de execução

## O problema

Mesmo com SQL validado, uma consulta pode ser cara: um produto cartesiano escondido, uma agregação sobre a base toda, ou uma função lenta. Sem limites, um pedido de um utilizador pode bloquear a base de dados para os outros. E um resultado enorme pode esgotar memória e rede.

O QueryShield aplica limites em três sítios, e cada um falha de forma diferente.

## O que entra e o que sai

Entra: SQL já validado, o tenant e os parâmetros. Sai: linhas (no máximo `max_rows`, com indicação de truncagem), ou um erro com código genérico.

Saída real do executor, com o validador **desligado** (cada linha é um SQL que o validador teria bloqueado; é a camada da base de dados a travar sozinha):

```
1 pg_sleep 5s com timeout 200ms (validador desligado): ERRO code=query_timeout msg=A consulta excedeu o tempo limite.  (0.39s)
2 linhas limitadas a 3: rows=3 truncated=True cols=['id'] sample=[[1], [2]]  (0.02s)
3 escrita dentro de WITH: ERRO code=execution_failed msg=Não foi possível executar a consulta.  (0.0s)
4 set_config para mudar tenant: ERRO code=permission_denied msg=Sem permissão para esta consulta.  (0.0s)
5 begin_request duplicado: ERRO code=permission_denied msg=Sem permissão para esta consulta.  (0.0s)
6 tabela secreta: ERRO code=permission_denied msg=Sem permissão para esta consulta.  (0.0s)
ping: True
7 resultado acima de 100 bytes: ERRO code=result_too_large msg=O resultado excede o tamanho máximo.  (0.08s)
8 base de dados inacessivel: ERRO code=database_unavailable msg=Base de dados indisponível.  (5.01s)
```

Notas sobre a saída: a linha 3 é `execution_failed` e não `read_only_violation`, porque o PostgreSQL recusa uma CTE de escrita dentro de uma subquery ("must be at the top level"). A escrita não acontece (o teste verifica a contagem de encomendas canceladas antes e depois). A linha 8 demora 5 s porque o pool tenta ligar até ao `timeout` configurado; o erro não revela host, utilizador nem password.

## Como funciona por dentro

Caminho de uma execução (`backend/app/execution/executor.py`):

1. **Ligação do pool.** `ConnectionPool` com `qs_reader` (`QueryExecutor.__init__`). A ligação nunca é de superuser.
2. **Transacção explícita** (`execute`, `with conn.transaction()`), para que nada corra fora dela.
3. **`SET TRANSACTION READ ONLY`** como primeira instrução (`_enter_read_only`, linha ~118).
4. **`qs_api.begin_request(seller, timeout_ms)`**: define o tenant e o `statement_timeout` **locais à transacção** e só pode ser chamada uma vez (migração 005).
5. **Limite de linhas por embrulho.** O SQL validado é embrulhado: `SELECT * FROM (<sql>) AS qs_result LIMIT <max_rows + 1>`. Pedir mais uma linha permite saber se houve truncagem sem contar tudo.
6. **Tamanho do resultado.** Depois de converter os valores, a soma do tamanho do texto é comparada com `max_result_bytes`; acima disso, `result_too_large`.
7. **Tradução de erros** (`_translate`, linha ~142). Cada classe de erro do driver vira um código: `QueryCanceled` → `query_timeout`, `InsufficientPrivilege` → `permission_denied`, `ReadOnlySqlTransaction` → `read_only_violation`, falha de ligação → `database_unavailable`, outros → `execution_failed`. A mensagem do driver **nunca** é devolvida.

Para `EXPLAIN` (`explain`), o caminho é o mesmo sem o embrulho e sem `ANALYZE`. A linha `Filter: (seller_id = ... current_setting('app.seller_id'))` no plano mostra que a RLS é aplicada mesmo no plano, o que se verificou na execução real.

## Porquê esta escolha

- **Três camadas de tempo e tamanho.** O `statement_timeout` por transacção (3 s por omissão, configurável entre 100 ms e 10 s), o padrão `ALTER ROLE ... SET statement_timeout = '3s'` como backstop (migração 001), e o `idle_in_transaction_session_timeout` de 10 s para não deixar transacções abertas.
- **`LIMIT max_rows + 1` em vez de contar.** Contar o resultado todo custaria uma segunda execução. Pedir uma linha a mais é barato e responde à pergunta "houve mais?".
- **Embrulho em subquery.** O SQL validado não é reescrito pelo executor: o embrulho é externo. Isto evita que um `LIMIT` interno do utilizador conflite com o limite do sistema.
- **Erros genéricos.** Uma mensagem como "could not connect to host X as user Y" revelaria a infra a quem está a testar o sistema. O código (`database_unavailable`) é suficiente para a API e para o frontend.

## Alternativas

- **Cancelar por processo** (matar a ligação ao fim de N segundos a partir da aplicação). Funciona, mas é mais lento de reagir e deixa a base de dados num estado menos previsível. O `statement_timeout` é aplicado pelo próprio servidor.
- **Quota por utilizador** (contar consultas por minuto). Complementar, não substitui os limites por consulta. Fica fora desta fase.
- **Ler tudo e cortar em Python.** Desperdiça largura de banda e memória do servidor.

## Como falha

Testes em `tests/postgres/test_executor.py` (com validador desligado, para provar a camada da base de dados):

- Timeout real: `test_slow_query_is_cancelled_by_statement_timeout` (usa `pg_sleep` com 200 ms e confirma `query_timeout` em menos de 4 s).
- Truncagem: `test_result_is_truncated_at_max_rows`.
- Tamanho: `test_result_size_limit_is_enforced`.
- Escrita dentro de CTE sem alteração de dados: `test_write_inside_cte_is_refused_and_changes_nothing`.
- Tenant não pode ser mudado pelo SQL: `test_sql_cannot_change_the_tenant_inside_the_transaction`.
- Sem credenciais na mensagem de erro: `test_unreachable_database_error_has_no_credentials_or_host`.
- `EXPLAIN` não executa: `test_explain_does_not_execute_the_query`.

**Limite conhecido.** A medição de latência para a avaliação ainda não existe (tarefa 7.2): os números acima são de um teste de funcionamento, não uma medida de desempenho. Qualquer tempo de consulta na avaliação fica `TODO: medir` até correr o runner.

## Perguntas de entrevista

**1. Porque é que o timeout é `SET LOCAL`/local e não global?**
Porque um timeout de sessão global afectaria outros pedidos que reutilizam a ligação do pool. O valor local à transacção acaba no commit ou rollback.

**2. Como é que sabes que houve truncagem sem contar todas as linhas?**
Pedimos `max_rows + 1`. Se vier a linha extra, há mais, e devolvemos só `max_rows`. É uma técnica barata e exacta.

**3. Porque é que o embrulho usa subquery e não reescreve o `LIMIT`?**
Reescrever o SQL exige parsing completo e mexer em `LIMIT` existentes. O embrulho é externo, não toca no SQL validado, e funciona com `UNION`, CTEs e `ORDER BY`.

**4. Porque é que a mensagem de erro é genérica?**
Porque a mensagem do driver contém host, utilizador e por vezes o SQL. Quem consegue ver a resposta de erro não deve aprender nada sobre a infra. O código estruturado chega para a aplicação.

**5. Porque é que o `pg_sleep` não é bloqueado pela base de dados?**
Porque é uma função de sistema que o role de leitura pode executar. A protecção é o validador (`function_not_allowed`) e o `statement_timeout`. Este facto está documentado no doc 04.

**6. O que acontece a uma ligação que fica "idle in transaction"?**
Bloqueia recursos e pode segurar locks. O `idle_in_transaction_session_timeout` de 10 s termina essas ligações.

**7. Um limite de tamanho por bytes é exacto?**
Não é: é uma aproximação pela soma do texto dos valores. Serve para proteger a memória e a rede, não para facturação. Documentado como aproximação.

**8. Porque é que o pool usa `open=False` e depois `open(wait=False)`?**
Para que o arranque da API não falhe se a base de dados estiver temporariamente indisponível. A primeira consulta trata o erro e `/health` reporta `degraded`.
