# QueryShield

Pergunta aos teus dados em linguagem natural, com validação AST (SQLGlot) e protecções aplicadas
pelo próprio PostgreSQL (role só de leitura, RLS por vendedor, timeouts e limites).

Domínio fictício: marketplace **Kianda Market** (3 vendedores, dados 100% sintéticos).
Estado do projecto: ver `openspec/changes/bootstrap-queryshield/tasks.md`.

## Requisitos

- Windows 10/11 com PowerShell (ou Git Bash), Python 3.12 (`python`) e Node.js 20+.
- **Não é preciso Docker nem instalar o PostgreSQL.** O PostgreSQL real vem do pacote `pgserver`
  (binários PostgreSQL 16 empacotados, arranque local, sem privilégios de administrador).

## Instalação (Windows)

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Versões fixadas em `pyproject.toml` (exactas). Verificação: `.\.venv\Scripts\python.exe -m pip list`.

## Base de dados local (PostgreSQL real, sem Docker)

1. Arrancar o PostgreSQL local persistente (dados em `.pgdata-dev/`, ignorado pelo git):

   ```powershell
   .\.venv\Scripts\python.exe scripts\dev_postgres.py
   ```

   O script imprime `QS_ADMIN_DSN=...`. A porta muda quando o servidor reinicia: volte a correr o script.

2. Definir as variáveis na sessão (nunca num ficheiro commitado; ver `.env.example`):

   ```powershell
   $env:QS_ADMIN_DSN = "<valor impresso no passo 1>"
   $env:QS_READER_PASSWORD = "<password local escolhida para qs_reader>"
   ```

3. Migrações e seed determinístico:

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

Para correr só os testes rápidos (sem PostgreSQL): `python -m pytest -m "not postgres"`.
