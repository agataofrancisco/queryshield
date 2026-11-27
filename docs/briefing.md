# PROMPT 10 — QueryShield: Text-to-SQL seguro e verificável

## Missão
Implementa uma interface analítica para uma base de dados PostgreSQL fictícia de bilhetes de autocarro (rotas, viagens, vendas, tarifas e operadores). O utilizador pergunta em português e o sistema propõe SQL de leitura, valida contra schema/permissões, executa com limites e explica a resposta com evidências. O objectivo principal é comprovar **SQL execution correctness + autorização**, não apenas gerar SQL sintacticamente válido.

## Arquitectura
FastAPI, PostgreSQL seed sintético com 7-10 tabelas e integridade referencial, SQLGlot para parse/validação AST; provider abstraction OpenRouter/OpenAI-compatible e mock offline; React dashboard. Criar semantic layer explícita com definições de `venda`, `receita`, `cancelamento`, `bilhete válido`, `período` e joins permitidos. Catálogo de schema indexável opcional, mas não expor colunas sensíveis ao LLM fora da role.

## Pipeline seguro (ordem obrigatória)
1. Autenticar utilizador e autorizar tenant/escopo de negócio.
2. Contextualizar schema estritamente permitido e glossário de métricas.
3. Modelo produz `sql`, parâmetros e justificativa estruturada; sem executar nada diretamente.
4. SQLGlot parse com dialect PostgreSQL; proibir múltiplos statements, comandos de escrita, DDL, transações, execução de função perigosa, tabelas/colunas não permitidas e CTEs com side effects; aplicar allowlist das formas suportadas; rejeitar ambiguidades.
5. Executor em ligação PostgreSQL separada, credencial read-only sem privilégios de escrita nem de tabelas privadas; RLS quando aplicável, `statement_timeout` pequeno, read-only transaction, limite de linhas e isolamento por tenant feito no DB, não por instrução ao LLM. Validação AST NÃO substitui estas protecções.
6. Query preview e explicação dos filtros; executar somente se a política permitir. Mostrar SQL, resultado tabular/gráfico, número de linhas, source tables, warnings e opção de feedback.
7. Detector de alucinação verifica schema, joins, unidades, consistência da definição da métrica e, quando possível, compara resultado contra queries golden; quando houver dúvida, pedir esclarecimento ou rejeitar.

## UI e API
`POST /query/generate`, `POST /query/validate`, `POST /query/execute`, `GET /schema/semantic`, `GET /query/history`, `GET /health`. Frontend com interface chat, SQL syntax-highlight, explain plan seguro sem `ANALYZE`, tabela de resultados, gráficos e avisos de segurança.

## Avaliação
Cria >=100 perguntas com SQL goldens e resultados calculados a partir do seed; misturar aggregations, date filters, multi-table joins, perguntas ambíguas e ataques de prompt injection. Mede execução exacta (comparando resultados normalizados), taxa de SQL válido, erros de interpretação de métricas, latência, custo e rejeição de queries proibidas. Testes de `DROP`, `UPDATE`, `SELECT` sobre tabela secreta, `WITH` malicioso, SQL comments, multi-statement, CROSS JOIN explosivo, tabelas cross-tenant e consultas longas. Não publicar connection string, dados reais ou endpoint de execução aberto ao público.

## Evidências
Publica screenshot/GIF pergunta→SQL validado→gráfico e 3 casos bloqueados, relatório de benchmark e avaliação do SQLGlot AST vs privilégios do Postgres. Se possível, compara uma baseline de geração directa insegura APENAS sobre sandbox offline, sem exposição.

## Regras de execução (obrigatórias)
És um agente sénior de software engineering e AI engineering. A tua missão é IMPLEMENTAR código funcional neste repositório, não apenas escrever um plano ou pseudocódigo. Primeiro inspecciona o repositório; depois propõe em `IMPLEMENTATION_PLAN.md` um plano curto e segue-o por fases até teres uma versão executável. Não pares após criar ficheiros vazios. Usa documentação oficial actual das bibliotecas e fixa versões compatíveis; não inventes APIs nem dependências. Caso não tenhas acesso a rede/credenciais, implementa adaptadores, mocks determinísticos e testes locais, mas distingue explicitamente o que foi testado de verdade do que foi apenas preparado.

Normas comuns: Python 3.11+ (salvo indicação explícita), tipagem, Pydantic v2, configuração por `.env.example`, FastAPI com OpenAPI, Ruff, pytest, logging estruturado sem secrets/PII, Dockerfile, `docker-compose.yml` quando fizer sentido, healthcheck e README claro (arranque, decisões de arquitectura, ameaças, limitações, custos, credenciais e deploy). Não coloques chaves no cliente ou no Git; valida entradas, implementa timeouts/retries limitados e autenticacao para operações administrativas. Inclui modo DEMO com dados sintéticos e sem pagamento; implementa testes unitários e testes de integração determinísticos em CI, mais uma suite de integração real opcional. Escreve `docs/architecture.md`, `docs/decisions.md`, `docs/case-study.md` com métricas REAIS ou campos `TODO: medir` (nunca inventes resultados). Entrega exactamente os comandos de execução e testes e lista limitações.

Para deployment, prepara backend persistente numa VM/serviço de containers e frontend estático quando possível; não assumes que Vercel Functions suporta Redis, workers long-running, volumes persistentes ou treino GPU. Se houver persistência, usa serviço gerido/volume externo e documenta credenciais, migrações e backups. Antes de concluir, executa testes, corrige falhas, regista o output e documenta o que não foi possível executar.
