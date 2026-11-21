# Tasks

## 1. Fundações e base de dados

- [x] 1.1 Criar `backend/app/{api,auth,semantic,generation,validation,execution,verification}`, `db/`, `frontend/`, `eval/` e `docs/learn/`; verificar com `git status`
- [x] 1.2 Confirmar e fixar versões (FastAPI, Pydantic v2, SQLGlot, psycopg 3, httpx, pytest, Ruff); verificar a instalação
- [x] 1.3 Instalar ou ligar o PostgreSQL e documentar o procedimento no Windows; verificar com `psql -c "select version()"`
- [x] 1.4 Criar as migrações SQL: schema (10 tabelas com FKs), roles `qs_app`/`qs_reader`, views por papel, RLS e grants; verificar com testes `-m postgres` de que o `qs_reader` não escreve, não lê a tabela secreta e só vê o seu vendedor
- [x] 1.5 Criar o seed determinístico com os casos difíceis; verificar que dois seeds com a mesma seed produzem contagens idênticas
- [x] 1.6 Escrever `docs/learn/04-roles-grants-views.md` e `05-row-level-security.md`; verificar que cada afirmação tem um teste

## 2. Semantic layer e autenticação

- [x] 2.1 Criar `metrics.yaml` e `schema.yaml` (papéis, colunas, joins permitidos), o loader validado e `GET /schema/semantic` por papel; verificar com teste de analista sem email/telefone
- [x] 2.2 Implementar JWT demo com `seller_id` e papel; verificar com testes de 401 e de papéis
- [ ] 2.3 Escrever `docs/learn/00-visao-geral.md` e `01-semantic-layer.md`; verificar o diagrama do pipeline de 7 passos

## 3. Validação

- [ ] 3.1 Implementar o validador AST (statement único, nós proibidos, allowlists de tabelas/colunas/funções, CTEs, joins, produto cartesiano, LIMIT/agregação); verificar com testes de cada ataque da spec
- [ ] 3.2 Expor `POST /query/validate` com o registo do hash validado; verificar com testes de API
- [ ] 3.3 Escrever `docs/learn/03-ast-e-sqlglot.md` (porquê não regex, com exemplos de bypass de regex); verificar os exemplos com testes

## 4. Geração e execução

- [ ] 4.1 Implementar o provider compatível com OpenAI e o mock determinístico, o prompt com schema por papel e o parsing estruturado com `needs_clarification`; verificar com testes de pergunta simples, ambígua e injecção
- [ ] 4.2 Implementar o executor (pool `qs_reader`, transacção READ ONLY, `SET LOCAL` de timeout e seller, LIMIT forçado, `not_validated`, erros sem credenciais); verificar com testes `-m postgres` de timeout, cross-tenant e escrita com validador desligado
- [ ] 4.3 Expor `POST /query/generate`, `POST /query/execute`, `GET /query/history` e `GET /health`; verificar com testes de API e isolamento de histórico
- [ ] 4.4 Escrever `docs/learn/02-text-to-sql-com-llms.md` e `06-timeouts-e-limites.md`; verificar a consistência com o código

## 5. Verificação

- [ ] 5.1 Implementar `metric_definition_mismatch`, `unknown_column` com sugestão, `possible_fanout` e a explicação ao utilizador; verificar com testes de receita sem devoluções, coluna inexistente e fan-out
- [ ] 5.2 Implementar o explain seguro (sem ANALYZE); verificar que não executa a query
- [ ] 5.3 Escrever `docs/learn/07-alucinacoes-sql-e-fanout.md`; verificar os exemplos com testes

## 6. Frontend

- [ ] 6.1 Criar a app React com login por persona, chat, SQL com highlight, tabela, gráfico, avisos, explain e feedback; verificar no browser: uma pergunta → SQL validado → gráfico, e 3 casos bloqueados
- [ ] 6.2 Verificar que não há credenciais nem connection strings no bundle (`npm run build` + pesquisa)

## 7. Avaliação

- [ ] 7.1 Criar ≥100 perguntas golden (todas as categorias e ataques) e o gerador de resultados esperados; verificar a regeneração idêntica
- [ ] 7.2 Implementar o runner (execution accuracy normalizada, SQL válido, erros de métrica, latência, custo, camada que travou cada ataque); verificar as funções de normalização com testes
- [ ] 7.3 Implementar a baseline insegura apenas em sandbox offline e a comparação de segurança; verificar que não abre portas de rede
- [ ] 7.4 Correr a avaliação e gravar o relatório; verificar os metadados e o `TODO: medir` para o que faltar
- [ ] 7.5 Escrever `docs/learn/08-execution-accuracy.md` e `09-defesa-em-profundidade.md` com os resultados obtidos; verificar que os números vêm do relatório

## 8. Entrega

- [ ] 8.1 Dockerfiles, `docker-compose.yml` (marcado como não testado localmente) e CI com o Postgres service (Ruff, pytest incluindo `-m postgres`, avaliação mock, build do frontend); verificar a validade do workflow
- [ ] 8.2 `README.md`, `docs/architecture.md`, `docs/decisions.md` e `docs/case-study.md`; verificar os comandos
- [ ] 8.3 `docs/learn/10-perguntas-de-entrevista.md` (≥25); verificar a consistência
- [ ] 8.4 Revisão de segurança independente (credenciais, RLS, validador, exposição do endpoint); verificar que os achados estão resolvidos ou documentados

## Workflow follow-up

- Avaliação real com um LLM e gravação do GIF da demo.
- Arquivar após revisão.
