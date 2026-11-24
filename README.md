# QueryShield

Pergunta aos teus dados em linguagem natural, com validação AST (SQLGlot) e protecções aplicadas
pelo próprio PostgreSQL (role só de leitura, RLS por vendedor, timeouts e limites).

Domínio fictício: marketplace **Kianda Market** (3 vendedores, dados 100% sintéticos).
Estado e tarefas: `openspec/changes/bootstrap-queryshield/tasks.md`.

## O que está pronto e o que não está

- **Implementado:** semantic layer, autenticação JWT demo, validador AST, geração (mock e provider
  compatível com OpenAI), executor read-only com um role por vendedor, verificação semântica, API,
  frontend, avaliação com 164 perguntas e baseline insegura em sandbox.
- **Não feito:** avaliação com um LLM real (não há chave neste ambiente: `TODO: medir`).
- **Não testado localmente:** Docker, docker-compose e o workflow de CI (validados só como YAML).
- **Pendente:** verificação do gráfico e de três bloqueios no browser (tarefa 6.1). A revisão de
  segurança independente está em `docs/security-review-independent.md`; faltam confirmações de
  runtime indicadas nesse relatório.

Resultados medidos: `docs/learn/08-execution-accuracy.md` e `docs/learn/09-defesa-em-profundidade.md`.

## Requisitos

- Windows 10/11 com PowerShell (ou Git Bash), Python 3.12 (`python`) e Node.js 24.
- **Não é preciso Docker nem instalar o PostgreSQL.** O PostgreSQL 16 real vem do pacote `pgserver`
  (binários empacotados, arranque local, sem privilégios de administrador).

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
cd frontend
npm ci
cd ..
```

As versões Python estão fixadas em `pyproject.toml` (exactas) e as do frontend em
`frontend/package.json` e `frontend/package-lock.json`.

## Portas de desenvolvimento

| Serviço | Porta | Variável de configuração |
|---|---|---|
| API (FastAPI) | `18200` | `VITE_API_URL` no frontend (por defeito `http://127.0.0.1:18200`) |
| Frontend (Vite) | `13200` | origem permitida no backend: `QS_CORS_ORIGINS` (por defeito `http://localhost:13200`) |
| PostgreSQL local | porta dinâmica | `scripts/dev_postgres.py` imprime a ligação |

## Base de dados local (PostgreSQL real, sem Docker)

1. Arrancar o PostgreSQL local persistente (dados em `.pgdata-dev/`, ignorado pelo git):

   ```powershell
   .\.venv\Scripts\python.exe scripts\dev_postgres.py
   ```

   O script imprime `QS_ADMIN_DSN=...`. A porta muda quando o servidor reinicia.

2. Definir as variáveis na sessão (nunca num ficheiro commitado; ver `.env.example`):

   ```powershell
   $env:QS_ADMIN_DSN = "<valor impresso no passo 1>"
   $env:QS_READER_PASSWORD_S1 = "<segredo único com 24+ caracteres>"
   $env:QS_READER_PASSWORD_S2 = "<outro segredo único com 24+ caracteres>"
   $env:QS_READER_PASSWORD_S3 = "<terceiro segredo único com 24+ caracteres>"
   $env:QS_READER_DSN_TEMPLATE = "postgresql://{role}:{password}@127.0.0.1:<porta>/queryshield"
   ```

3. Migrações e seed determinístico (2 100 encomendas, 10 tabelas):

   ```powershell
   .\.venv\Scripts\python.exe -m db.migrate
   .\.venv\Scripts\python.exe -m db.seed
   ```

4. Verificação com o `psql` que vem com o pgserver:

   ```powershell
   .\.venv\Lib\site-packages\pgserver\pginstall\bin\psql.exe -c "select version()" $env:QS_ADMIN_DSN
   ```

Os testes `-m postgres` **não** precisam deste passo: arrancam um PostgreSQL temporário próprio
(`tests/postgres/conftest.py`) e apagam-no no fim.

## Correr a aplicação

Com as variáveis do passo anterior, mais:

```powershell
$env:QS_DEMO_AUTH = "true"                     # login demo por persona (só desenvolvimento)
$env:QS_JWT_SECRET = "<segredo com 32+ caracteres>"
$env:QS_LLM_PROVIDER = "mock"                  # gerador determinístico, sem rede
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 18200
```

Noutro terminal:

```powershell
cd frontend
npm run dev          # http://localhost:13200
```

Personas demo (só com `QS_DEMO_AUTH=true`): `analista.ngola`, `financas.ngola`,
`analista.benguela`, `admin.plataforma`.

Exemplos de perguntas que o gerador mock responde: "qual foi a receita de março de 2026?",
"quantas encomendas válidas houve em janeiro de 2025?", "quanto foi devolvido em abril de 2025?"
(este último **não** é reconhecido pelo mock: ver `docs/learn/08`).

## Testes

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m pytest -m "not postgres" -q     # rápidos, sem PostgreSQL
.\.venv\Scripts\python.exe -m pytest -m postgres -q           # PostgreSQL real (pgserver)
.\.venv\Scripts\python.exe -m pytest -q                       # tudo
cd frontend; npm run build                                    # build + varredura do bundle
```

## Avaliação

```powershell
$env:QS_READER_DSN_TEMPLATE = "postgresql://{role}:{password}@127.0.0.1:<porta>/queryshield"
.\.venv\Scripts\python.exe -m eval.build_questions            # 164 perguntas (determinístico)
.\.venv\Scripts\python.exe -m eval.build_expected             # 140 resultados golden (valida cada golden)
.\.venv\Scripts\python.exe -m eval.run_eval                   # gera eval/reports/report-mock.json
```

Baseline insegura, **só em sandbox descartável** (cria `qs_sandbox_insecure_baseline`; nunca usa a
base de desenvolvimento):

```powershell
$env:QS_SANDBOX_ADMIN_DSN = "<ligação superuser ao servidor local>"
.\.venv\Scripts\python.exe -m eval.run_baseline
```

## Docker e CI (não testados localmente)

- `Dockerfile.backend`, `Dockerfile.frontend` e `docker-compose.yml`: sem Docker neste ambiente.
  O compose exige `POSTGRES_PASSWORD`, `QS_READER_PASSWORD_S1`, `QS_READER_PASSWORD_S2`,
  `QS_READER_PASSWORD_S3` e `QS_JWT_SECRET` num `.env` local e
  deixa `QS_DEMO_AUTH=false` (sem login demo). Para usar a interface demo, altere-o explicitamente.
- `.github/workflows/ci.yml`: Ruff, migrações e seed num serviço PostgreSQL, testes (unitários e
  `-m postgres`), avaliação mock e build do frontend com varredura do bundle. Validado como YAML;
  ainda não correu no GitHub.

## Variáveis de ambiente

| Variável | Obrigatória | Função |
|---|---|---|
| `QS_READER_DSN_TEMPLATE` | para executar consultas | ligação com `{role}` e `{password}`, preenchidos com o role e segredo do vendedor |
| `QS_SELLER_IDS` | não (`1,2,3`) | vendedores com pool configurada |
| `QS_DEADLINE_MARGIN_MS` | não (`1000`) | margem do prazo da aplicação sobre o timeout da base de dados |
| `QS_ADMIN_DSN` | só migrações e seed | superuser local; nunca usada pela API |
| `QS_READER_PASSWORD_S<N>` | migrações e API | segredo individual e único de cada role `qs_reader_s<N>` (mínimo 24 caracteres) |
| `QS_JWT_SECRET` | sim (32+ caracteres) | assina os tokens |
| `QS_DEMO_AUTH` | não (`false`) | activa `POST /auth/demo-login` |
| `QS_LLM_PROVIDER` | não (`mock`) | `mock` ou `openai` |
| `QS_LLM_API_KEY`, `QS_LLM_MODEL`, `QS_LLM_BASE_URL` | só com `openai` | provider compatível |
| `QS_CORS_ORIGINS` | não | origens do frontend (`http://localhost:13200`) |
| `QS_STATEMENT_TIMEOUT_MS`, `QS_MAX_ROWS`, `QS_MAX_RESULT_BYTES` | não | limites do executor |

Nenhum `.env` é lido pelo código: as variáveis vêm do ambiente. `.env.example` documenta-as.

## Limitações conhecidas

- O gerador mock cobre um conjunto fixo de intenções; não é um LLM.
- `scripts/dev_postgres.py` pode falhar a reanexar a um servidor já arrancado (`postmaster.pid`
  com estado inesperado): nesse caso usar a ligação directa do servidor em execução ou reiniciar.
- No Windows, o pgserver escuta sempre em `127.0.0.1`; "sem portas de rede" é verdade para o código,
  não para o sistema operativo.
- Os testes com `pgserver` podem falhar com `WinError 10055` quando a pilha de sockets do sistema
  está saturada por outros programas; repetir após algum tempo.

Decisões tomadas durante a implementação: `docs/decisions.md`. Arquitectura: `docs/architecture.md`.
