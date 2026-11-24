# 04 — Roles, grants e vistas

## Fronteira de confiança

O SQL gerado é entrada não confiável. O executor nunca usa o utilizador administrativo nem o dono
`qs_app`; usa um role de login só de leitura para cada vendedor. A separação por role complementa o
validador AST e é aplicada pelo PostgreSQL mesmo quando a validação da aplicação é contornada.

## Roles actuais

- `qs_app` é `NOLOGIN` e dono dos objectos.
- `qs_reader_s1`, `qs_reader_s2` e `qs_reader_s3` são roles independentes, `LOGIN`, sem superuser,
  criação de roles/base de dados, `BYPASSRLS` ou memberships entre si.
- Cada role recebe um segredo distinto (`QS_READER_PASSWORD_S1..S3`). A migração define a password
  através de `db/migrate.py`; nenhum segredo fica no SQL versionado.
- `qs_reader` é histórico e fica `NOLOGIN` pela migração 006.

## Superfície de leitura

As tabelas ficam em `qs_private`; as vistas com colunas explícitas ficam em `qs_api`. Os roles de
vendedor só recebem `USAGE` necessário e `SELECT` nas vistas públicas. A tabela
`internal_fraud_flags` não tem vista nem grant. A vista `customers` não expõe email nem telefone.

A migração 006 cria `qs_private.seller_roles`, que associa cada role ao respectivo `seller_id`. A
migração 007 faz as políticas RLS comparar essa associação com `session_user`, a identidade de login
original que se mantém através das vistas e funções. A identidade do tenant não vem de uma variável
de sessão controlável pelo SQL. `qs_api.begin_request(timeout_ms)` apenas define o timeout local à
transacção.

## Configuração das credenciais

`QS_READER_DSN_TEMPLATE` tem de conter `{role}` e `{password}`. A aplicação valida que existem três
segredos com pelo menos 24 caracteres, distintos entre si, e codifica a password ao materializar o
DSN. `QS_ADMIN_DSN` fica reservado às migrações e ao seed; a API não o recebe.

A aplicação ainda recebe os três segredos no mesmo processo. Separar os serviços por vendedor e
usar armazenamento de segredos independente reduziria o impacto de um comprometimento da API.

## Verificação no código

- `db/migrations/001_roles.sql` cria os roles de base; `006_per_seller_roles.sql` cria os logins e
  privilégios; `007_rls_login_identity.sql` fixa a identidade RLS à sessão de login.
- `backend/app/config.py` rejeita DSNs sem os dois tokens e passwords partilhadas ou demasiado curtas.
- `backend/app/execution/executor.py` cria uma pool por vendedor e encaminha cada pedido para a pool
  seleccionada pela identidade autenticada.
- `tests/postgres/test_roles_rls.py` cobre a associação role/vendedor, os privilégios e tentativas
  de mudar a identidade dentro da sessão. A suite PostgreSQL tem de ser executada para confirmar o
  comportamento no runtime; não inferimos isso apenas da configuração.

## Alternativas

- **Um único role de leitura.** Rejeitado porque uma credencial comprometida permitiria autenticar
  como qualquer vendedor se as sessões partilhassem o mesmo login.
- **Filtro de tenant só no SQL da aplicação.** Rejeitado porque SQL gerado ou uma falha no validador
  poderia omitir ou alterar o filtro.
- **Confiar apenas no validador.** Rejeitado: o PostgreSQL deve continuar a limitar escrita, tabelas
  e linhas mesmo quando outra camada falha.
