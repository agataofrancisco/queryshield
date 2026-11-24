# Revisão de segurança (auto-revisão)

> **Registo histórico:** esta revisão antecede a migração 006 e descreve o antigo tenant de sessão
> (`app.seller_id`). Para os controlos e achados actuais, usar `docs/security-review-independent.md`.

> **Estado:** auto-revisão histórica; não substitui a revisão independente da tarefa 8.4.

## Âmbito e método

Áreas pedidas: credenciais, RLS, validador, exposição do endpoint. Para cada área: o que se afirma, como se
verificou (teste, grep ou execução real) e o que ficou por verificar. Achados com severidade e estado
(**resolvido**, **aberto** ou **documentado**).

## Verificações feitas

| Área | Afirmação | Como se verificou | Resultado |
|---|---|---|---|
| Credenciais | Nenhuma palavra-passe de desenvolvimento nos ficheiros do repositório | pesquisa na árvore de trabalho, excluindo `.env*`, `.venv`, `node_modules`, `dist` e dados locais | sem resultados |
| Credenciais | O código não lê `.env` | `backend/app/config.py` lê só o ambiente; nenhum `load_dotenv` | verificado por leitura |
| Credenciais | Mensagens de erro sem host, utilizador ou palavra-passe | teste `test_unreachable_database_error_has_no_credentials_or_host` | passa |
| Credenciais | Bundle do frontend sem ligações, papéis nem segredos | pesquisa no `dist/` após build | 0 ocorrências |
| Frontend | Sem `innerHTML`, `eval` ou armazenamento do navegador | pesquisa em `frontend/src` | sem resultados (um comentário menciona `localStorage`) |
| Endpoints | Tudo menos `/health` exige token | `test_validate_endpoint_requires_authentication`, `test_semantic_endpoint_without_token_is_401`, `test_generate_endpoint_requires_auth_and_returns_validated_proposal` | passa |
| Endpoints | Login demo desactivado por omissão | `test_demo_login_is_disabled_by_default` (404) | passa |
| Endpoints | Histórico isolado por utilizador e sem linhas | `test_history_is_isolated_per_user_and_has_no_rows` | passa |
| JWT | Issuer, audience, expiração e claims tipados; `alg` fixo HS256 | testes de claims forjados (`test_forged_or_malformed_claims_are_rejected`) | passa |
| Validador | Escrita, multi-statement, funções perigosas, tabelas fora do papel | `tests/unit/test_validator.py` (lista de ataques da spec) | passa |
| Validador | Código de laboratório não é alcançável pela API | `grep` de `from eval` / `import eval` em `backend/` | sem resultados |
| RLS | Sem tenant, zero linhas (fail-closed) | `test_reader_without_tenant_sees_no_rows` | passa |
| RLS | Dono sujeito a RLS (`FORCE`) | `test_owner_role_is_subject_to_rls_because_of_force` | passa |
| RLS | Tabela secreta e tabelas base inacessíveis ao reader | `test_reader_has_no_privileges_on_base_tables_or_secret_table` | passa |
| RLS | Tenant não vaza entre pedidos no pool | `test_tenant_does_not_leak_to_the_next_transaction` | passa |
| Execução | `set_config` e segunda chamada a `begin_request` recusados | `test_sql_cannot_change_the_tenant_inside_the_transaction`, `test_sql_cannot_start_a_second_request_scope` | passa |
| Execução | Escrita dentro de CTE não altera dados | `test_write_inside_cte_is_refused_and_changes_nothing` | passa |

## Achados

### A1 — O tenant é uma definição de sessão (aberto, severidade média)

**Facto verificado.** Dentro da mesma transacção, `SET app.seller_id = '2'` muda o que a RLS devolve: após
`begin_request(1)`, a consulta passa a devolver as 700 linhas do vendedor 2 (teste xfail
`test_plain_set_of_the_tenant_setting_cannot_change_what_rls_shows`). Uma tentativa de corrigir isto com uma
tabela privada (migração 006) foi revertida: `begin_request` escreve, e as transacções do reader são
`READ ONLY`, por isso a escrita é recusada. A correcção exige duas transacções por pedido e um token de pedido.

**Alcance real.** No caminho da API o SQL é embrulhado (`SELECT * FROM (...)`), por isso um `SET` não é
sintaxe válida, e o validador também o recusa. O achado só é explorável por quem já controla instruções de
topo na sessão do reader, ou por um escape do embrulho que o validador não detecte.

**Recomendação.** Duas transacções por pedido (escrita do âmbito em `READ WRITE`, leitura em `READ ONLY`), com
um token de pedido gerado pelo executor e lido por `current_seller_id` a partir de uma tabela sem privilégios
para o reader. Alternativa mais forte: um role de base de dados por tenant.

### A2 — `begin_request` pode ser chamado por quem controla instruções de topo (aberto, severidade média)

Pelo mesmo motivo de A1: quem executa instruções de topo na sessão do reader pode iniciar uma transacção
própria e chamar `begin_request` com outro vendedor. A barreira actual é o embrulho e o validador, não a base
de dados. A mesma correcção de A1 resolve este caso.

### A3 — Divergência entre SQLGlot e PostgreSQL (aberto, documentado)

O validador analisa com SQLGlot. Uma construção que o SQLGlot leia de forma diferente do PostgreSQL pode
passar o validador. A base de dados continua a limitar linhas e operações, mas não a forma da consulta
(produtos cartesianos com `LIMIT`, funções lentas). Mitigação actual: testes de ataque, a experiência de laboratório da avaliação
(`eval/run_eval.py`, que executa cada ataque com o validador ignorado), e a lista explícita de funções permitidas.

### A4 — Sem limitação de taxa nos endpoints (aberto, severidade baixa)

`/query/generate` e `/query/execute` não têm limite por utilizador. O timeout (3 s), o máximo de linhas
(500) e o tamanho do resultado limitam cada pedido, não o volume de pedidos. Recomendação: limite por
utilizador e por minuto ao nível do proxy ou da aplicação.

### A5 — Login demo sem palavra-passe (documentado, severidade baixa com a configuração por omissão)

Com `QS_DEMO_AUTH=true`, `POST /auth/demo-login` emite um token para qualquer persona conhecida, sem
verificação. Está desactivado por omissão, no código e no `docker-compose.yml`. Risco: alguém activar a
opção num ambiente real. Recomendação: recusar o arranque quando o ambiente não for de desenvolvimento.

### A6 — Estado em memória (documentado, severidade baixa)

O histórico e o registo de hashes validados vivem no processo. Com várias instâncias, `validated_hash` e o
histórico não são partilhados. Não há fuga entre utilizadores (verificado), mas há perda de dados ao reiniciar.

### A7 — `statement_timeout` pode ser alterado pelo SQL da sessão (aberto, severidade baixa)

**Verificado:** com acesso às instruções de topo, `SET statement_timeout = '60s'` dentro da transacção
faz `SHOW statement_timeout` devolver `1min`. Afecta apenas o
limite de recursos (não o isolamento). Mesmo mecanismo de A1.

### A8 — Visibilidade de SQL de outras sessões do mesmo role (não verificado)

`pg_stat_activity` pode mostrar o texto de consultas de outras sessões do mesmo role. O texto contém SQL
gerado, não dados. Não foi testado; fica como `não verificado`.

## Achados resolvidos durante o trabalho

- **`set_config` acessível ao reader** (migração 005): retirado do `PUBLIC` e concedido só ao dono; teste
  `test_reader_cannot_change_tenant_with_set_config`.
- **Escrita em CTE** e **multi-statement**: travados pelo validador e pela base de dados (ver avaliação,
  `docs/learn/09`).
- **`%` em literais** podia partir a execução com parâmetros: recusado pelo validador.

## Pontos que não estão no escopo desta revisão

- Autenticação de produção (o projecto usa tokens demo).
- Infraestrutura real de deployment (Docker e CI não foram executados).
- Conformidade legal (RGPD) e retenção de dados.
- Revisão do código do frontend além das pesquisas acima.

## Conclusão

Os controlos pedidos (credenciais, RLS, validador e exposição de endpoints) foram verificados por testes ou
pesquisas. Dois achados de severidade média (A1 e A2) são reais e **não estão resolvidos**: afectam a
defesa em profundidade da base de dados, não o caminho actual da API. Recomenda-se que o supervisor corrija
A1/A2 antes de qualquer uso com dados reais, e que peça a revisão independente.
