# Proposal

## Why

"Pergunta aos teus dados em linguagem natural" é das demos de IA mais comuns e das mais perigosas. Um LLM que gera SQL pode escrever `DROP TABLE`, ler colunas com dados pessoais, juntar dados de clientes diferentes ou simplesmente calcular "receita" de forma errada com SQL perfeitamente válido. O QueryShield prova duas coisas: **correcção de execução** (o resultado está certo face a respostas golden) e **autorização real**, aplicada pela base de dados e não por instruções ao modelo. A validação AST com SQLGlot é uma camada; as protecções do PostgreSQL (role só de leitura, RLS, timeouts) são outra; e nenhuma substitui a outra.

Domínio fictício: o marketplace **Kianda Market**, uma loja online multi-vendedor. Cada vendedor é um tenant (`seller_id`) e só vê os seus dados. Os papéis são `seller_analyst` (sem colunas de PII de clientes), `seller_finance` (inclui receitas e comissões) e `platform_admin`. Todos os dados são sintéticos.

## What Changes

- Projecto novo `projects/queryshield`: FastAPI, PostgreSQL com seed sintético (7-10 tabelas com integridade referencial), SQLGlot, provider compatível com OpenAI + mock e frontend React.
- Semantic layer explícita com as definições de `venda`, `receita`, `devolução`, `encomenda válida`, `período` e os joins permitidos.
- Pipeline seguro em 7 passos e por esta ordem: autenticar → contextualizar o schema permitido → gerar SQL estruturado (sem executar) → validar AST → executar numa ligação só de leitura com RLS, timeout e limite de linhas → mostrar o preview e a explicação → verificar alucinações e consistência.
- API: `POST /query/generate`, `POST /query/validate`, `POST /query/execute`, `GET /schema/semantic`, `GET /query/history`, `GET /health`.
- Frontend com chat, SQL com syntax highlight, explain plan seguro (sem `ANALYZE`), tabela, gráfico, avisos e feedback.
- Avaliação com ≥100 perguntas com SQL golden e resultados calculados do seed, incluindo ataques.
- Comparação AST vs privilégios do Postgres e baseline insegura só em sandbox offline.
- Documentação de aprendizagem.

## Capabilities

### New Capabilities
- `semantic-layer`: definições de métricas, glossário, joins permitidos e o schema visível por papel.
- `sql-generation`: produção de SQL parametrizado e justificação estruturada a partir da pergunta, sem execução.
- `sql-validation`: análise AST, allowlists e rejeição de construções perigosas ou ambíguas.
- `safe-execution`: execução isolada com role só de leitura, RLS por tenant, timeouts e limites.
- `answer-verification`: detecção de alucinação de schema, joins e métricas e comparação com resultados golden.
- `query-interface`: API, histórico, explicação, explain seguro e frontend.
- `text2sql-evaluation`: perguntas golden, execution accuracy, testes de ataque e relatório.

### Modified Capabilities
<!-- Nenhuma: projecto novo. -->

## Impact

- **Código novo**: `backend/`, `db/` (schema, seed, roles, RLS), `frontend/`, `eval/` e `docs/`.
- **Dependências** (confirmar versões): FastAPI, Pydantic v2, SQLGlot, psycopg 3, httpx, pytest e Ruff.
- **Infraestrutura**: PostgreSQL real é **obrigatório** para provar RLS, roles e timeouts. Sem Docker local é preciso instalar o Postgres nativamente ou usar CI com service. Os testes de segurança de base de dados não correm sobre SQLite.
- **Fora de âmbito**: dialectos que não sejam PostgreSQL, escrita na base de dados e exposição pública do endpoint de execução.
