# Estudo de caso: QueryShield

## O problema

"Pergunta aos teus dados em linguagem natural" é uma demo comum e perigosa. Um modelo que escreve SQL pode
escrever `DROP TABLE`, ler dados pessoais, juntar dados de vendedores diferentes, ou calcular "receita" de
forma errada com SQL perfeitamente válido. O QueryShield tenta provar duas coisas: que o resultado está
correcto e que a autorização é aplicada pela base de dados, não por instruções ao modelo.

## O que foi construído

Um pipeline de 7 passos sobre um marketplace fictício (Kianda Market, 3 vendedores):

1. autenticação por token com tenant e papel;
2. contexto do schema permitido ao papel (semantic layer em YAML);
3. geração de SQL estruturado, sem execução;
4. validação AST com SQLGlot (multi-statement, escrita, allowlists, joins, produtos cartesianos, limites);
5. execução com um role e credencial distintos por vendedor, RLS por `session_user`, timeout e limite de linhas;
6. preview, explicação e plano de execução sem `ANALYZE`;
7. verificação semântica (definição de métricas e fan-out).

Há uma API FastAPI, um frontend React com chat, SQL realçado, tabela, gráfico e avisos, migrações SQL,
seed determinístico, 164 perguntas de avaliação e uma baseline insegura medida apenas num sandbox.

## Resultados medidos

Todos os números vêm de `eval/reports/` e dos testes. O gerador é um **mock determinístico**, não um LLM.

- **Testes:** 223 no total: 51 com PostgreSQL real (RLS, roles, executor com validador desligado, API de
  ponta a ponta, avaliação) e 172 unitários. Resultado: 222 passam e 1 falha esperada (`xfail`) que documenta
  o achado A1 de `docs/security-review.md`. Ruff sem erros.
- **Execution accuracy:** 0,514 (72 de 140 perguntas com resultado esperado). As categorias de receita e de
  encomendas válidas acertam 100%; as restantes ficam sem resposta ou falham (ver a seguir).
- **Respostas erradas não recusadas:** 8. Quatro perguntas de "receita por categoria" receberam a receita
  total, e quatro de "encomendas canceladas" receberam a contagem de encomendas válidas. Cada SQL é válido
  e canónico; o validador e a verificação não as recusaram. É o modo de falha mais importante do sistema.
- **Validade do SQL gerado:** 0,964 (80 de 83).
- **Ataques:** 15 de 15 travados. O validador trava 14; a base de dados, sem validador, trava 12. Os
  cruzamentos de vendedores são filtrados pela RLS.
- **Baseline insegura (sandbox):** 8 de 15 ataques executados sem qualquer protecção, incluindo a leitura da
  tabela secreta e uma fuga entre vendedores.
- **Latência (mock, base local):** mediana 9,7 ms, p95 75 ms. Não representa produção.
- **Custo:** não medido (`TODO: medir com LLM real`).

## O que correu mal e como foi tratado

- **Falha de segurança encontrada em revisão:** o role comum podia mudar o tenant com `set_config` no
  SQL gerado. A migração 006 substitui a identidade de sessão por um role de login por vendedor, e a
  API agora exige segredos distintos. A configuração estática está implementada; a verificação da
  migrações 006–007 e do cancelamento de consultas ainda depende de execução PostgreSQL em runtime.
- **Golden não determinístico:** `ORDER BY ... LIMIT` com empates. A regeneração byte a byte detectou-o.
- **Baseline inútil à primeira execução:** quase todos os ataques falhavam por nomes não resolvidos, o que
  não mediria segurança. Corrigido: a sessão resolve os nomes como a app e a sandbox não tem RLS. Os sete
  ataques que continuaram "bloqueados" por motivos alheios à segurança (integridade referencial, vistas,
  colunas inexistentes, timeout do runner) são identificados como tal.
- **Bug do mock escondido pela média:** a accuracy de receita parecia boa, mas o mock respondia a outras
  perguntas com a receita total. O relatório passou a contar esses casos à parte.
- **Dev DB inacessível a meio:** o servidor local entrou em recuperação após um encerramento interrompido;
  esperou-se a recuperação em vez de o reinicializar, e o resultado foi revalidado.

## Limitações honestas

- Não há avaliação com um modelo de linguagem real. A accuracy descreve um gerador de regras.
- A revisão independente está em `docs/security-review-independent.md`. O desenho de roles por vendedor
  corrige A1/A2 no código; o estado só deve ser encerrado após verificação integrada em PostgreSQL.
- O processo da API recebe os três segredos de vendedor; uma intrusão na API pode aceder a todos. Para
  reduzir esse raio de impacto, separar a implantação e o armazenamento de segredos por vendedor.
- O validador é mais estrito do que a base de dados: recusa consultas legítimas sem `LIMIT` e pesquisas com
  `LIKE`. São escolhas conscientes, documentadas em `docs/decisions.md`.
- Docker e compose verificados em 2026-11-27; o CI no GitHub não correu (conta bloqueada por faturação).
- O gráfico e três bloqueios não foram verificados no browser (o mock não os produz).

## O que faria a seguir

1. Medir com um LLM real (provider OpenAI-compatível já implementado), com a mesma avaliação.
2. Separar papéis na base de dados (`SET LOCAL ROLE`) em vez de depender só do validador.
3. Persistir histórico e registo de hashes, com um limite de tempo de validade.
4. Substituir a heurística de métricas por testes de consistência com consultas de referência.
