# QueryShield

**Ask your data in plain language, safely. The LLM writes SQL, but the database decides what
anyone is allowed to see.**

"Chat with your database" demos are easy to build and easy to break. A model that writes SQL can
also write `DROP TABLE`, read personal data, join across tenants, or compute "revenue" wrongly with
perfectly valid SQL. QueryShield is a text-to-SQL system built on defence in depth:

- an AST validator rejects dangerous queries before they run,
- PostgreSQL itself enforces read-only access, row-level security per seller, timeouts and row
  limits,
- a semantic check flags metric-definition mistakes and join fan-out.

> Fictional domain: the **Kianda Market** marketplace (3 sellers, 100% synthetic data).

## Highlights

- **Validation on the AST, not with regex.** SQLGlot parses every query. The validator rejects:
  - multiple statements and any write,
  - disallowed tables, columns and functions,
  - cartesian products,
  - queries without limits.
- **The database is the last line of defence.** Each seller has its own login role and credential,
  and row-level security keys on `session_user`. Transactions are read-only, with statement
  timeouts and forced `LIMIT`s. Even with the validator switched off, the database blocks 12 of 15
  attacks.
- **A semantic layer per role.** YAML metric and schema definitions decide what each role sees. An
  analyst never even sees customer emails in the prompt.
- **Measured against an insecure baseline.** The same 15 attacks run against an unprotected setup
  in a throwaway sandbox, so the protection is quantified, not claimed.
- **A security bug found and fixed.** Review showed that a shared role could switch tenant with
  `set_config` from generated SQL. The fix moved identity to per-seller login roles (migrations
  006–007) and is covered by real-Postgres tests.

## The 7-step pipeline

```mermaid
flowchart LR
    Q[Question] --> A[1. JWT auth<br/>tenant + role]
    A --> S[2. Semantic layer<br/>allowed schema]
    S --> G[3. LLM generates SQL<br/>structured, not executed]
    G --> V{4. AST validator<br/>SQLGlot}
    V -->|rejected| X[Blocked, nothing runs]
    V -->|ok| E[5. Execute as seller role<br/>RLS, read-only, timeout]
    E --> P[6. Preview, explain<br/>no ANALYZE]
    P --> C[7. Semantic check<br/>metric definition, fan-out]
    C --> R[Table, chart, warnings]
```

## Results

The generator here is a **deterministic mock, not an LLM**. Numbers come from
[`eval/reports/`](eval/reports/) and the test suite.

| Metric | Result |
|---|---|
| Attacks blocked (15 total) | **15/15**: validator blocks 14; the database alone, with the validator off, blocks 12 |
| Insecure baseline, same 15 attacks | **8/15 executed**, including reading the secret table and a cross-seller leak |
| Execution accuracy | 0.514 (72/140 questions with an expected result) |
| Valid SQL rate | 0.964 (80/83) |
| Wrong answers not refused | **8**, reported separately (see below) |
| Latency (mock, local DB) | p50 9.7 ms, p95 75 ms |
| Tests | 236 passing, 64 of them against a real PostgreSQL 16 |

**The number that matters most is the 8.** Four "revenue by category" questions got total revenue,
and four "cancelled orders" questions got the valid-order count. The SQL is valid and canonical,
so neither the validator nor the semantic check refused it. A plausible number for the wrong
question is the most dangerous failure mode, so the report counts it separately instead of hiding
it in an average. Details in
[`docs/learn/08-execution-accuracy.md`](docs/learn/08-execution-accuracy.md) and
[`docs/learn/09-defesa-em-profundidade.md`](docs/learn/09-defesa-em-profundidade.md).

Verified in the browser on 2026-11-27:

- **Valid question:** "revenue per month in 2025" passed validation, ran, and returned 12 rows with
  a chart.
- **Blocked requests:** a delete, a query on an internal fraud table, and a customer-email lookup
  were each blocked with a specific reason.

## Tech stack

Python 3.12 · FastAPI · SQLGlot · PostgreSQL 16 (roles, RLS, views, grants) · psycopg 3 + pool ·
PyJWT · Pydantic v2 · React 19 + Vite · Recharts · CodeMirror · pytest · pgserver ·
Ruff · Docker Compose

## Run it locally (no Docker, no Postgres install)

A real PostgreSQL 16 comes from the `pgserver` package. It needs no admin rights and no Docker.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\dev_postgres.py        # prints QS_ADMIN_DSN
```

```powershell
$env:QS_ADMIN_DSN = "<printed above>"
$env:QS_READER_PASSWORD_S1 = "<unique secret, 24+ chars>"   # also S2 and S3
$env:QS_READER_DSN_TEMPLATE = "postgresql://{role}:{password}@127.0.0.1:<port>/queryshield"
.\.venv\Scripts\python.exe -m db.migrate
.\.venv\Scripts\python.exe -m db.seed
$env:QS_DEMO_AUTH = "true"; $env:QS_LLM_PROVIDER = "mock"; $env:QS_JWT_SECRET = "<32+ chars>"
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --port 18200
```

```powershell
cd frontend; npm ci; npm run dev     # http://localhost:13200
```

Demo personas: `analista.ngola`, `financas.ngola`, `analista.benguela`, `admin.plataforma`.

Try these questions (the demo UI is in Portuguese):

- "receita por mês de 2025" (revenue per month in 2025) produces a chart.
- "apaga as encomendas canceladas" (delete the cancelled orders) is blocked.
- "lista o email dos clientes" (list customer emails) is blocked.

**Docker:** PostgreSQL 16, migrations, API and an Nginx-served UI. Verified on 2026-11-27: the db is
healthy, migrations ran, API `/health` returns 200 and the UI is served. The compose file refuses
to start without secrets, so set `POSTGRES_PASSWORD`, `QS_JWT_SECRET` and `QS_READER_PASSWORD_S1`
through `QS_READER_PASSWORD_S3` in your shell first:

```powershell
docker compose up --build --wait     # UI http://localhost:13200 · API http://localhost:18200/health
```

The full walkthrough, including the provider settings for an OpenAI-compatible endpoint, is in
[`docs/architecture.md`](docs/architecture.md) and the comments in `backend/app/config.py`.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m pytest -m "not postgres" -q    # fast
.\.venv\Scripts\python.exe -m pytest -m postgres -q          # real PostgreSQL, RLS, roles, executor, baseline sandbox
.\.venv\Scripts\python.exe -m eval.run_eval                  # 164-question evaluation
```

## Known limitations

- **No real LLM:** there's no evaluation with a real model yet. The provider is implemented, but
  without a key the score is `TODO: measure`.
- **Shared API process:** the API process holds all three seller secrets, so compromising the API
  reaches every seller. Separate deployments would shrink that blast radius.
- **Strict by design:** the validator rejects some legitimate queries, such as those without
  `LIMIT` or using `LIKE` ([`docs/decisions.md`](docs/decisions.md)).
- **Windows sandbox:** pgserver listens on `127.0.0.1`. The baseline runner opens no sockets of its
  own (tested), but the sandbox database still has a loopback port.

## Documentation

- [`docs/architecture.md`](docs/architecture.md), [`docs/decisions.md`](docs/decisions.md),
  [`docs/case-study.md`](docs/case-study.md),
  [`docs/security-review-independent.md`](docs/security-review-independent.md)
- [`docs/learn/`](docs/learn/) (Portuguese): semantic layers, text-to-SQL with LLMs, ASTs and
  SQLGlot, roles, grants and views, row-level security, timeouts, SQL hallucinations and fan-out,
  execution accuracy, and defence in depth, plus interview questions.
