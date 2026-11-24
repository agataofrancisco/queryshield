# Decisões

Registo das decisões tomadas durante a implementação. As que não estavam cobertas pelo plano
(OpenSpec) estão marcadas **[nova]** e foram escolhidas pelo caminho mais pequeno e seguro.

## Infra e base de dados

1. **PostgreSQL via pgserver (16.2), sem Docker.** O plano permitia-o. Os testes arrancam um servidor
   temporário; o desenvolvimento usa `scripts/dev_postgres.py`.
2. **Tabelas em `qs_private`, vistas em `qs_api`, `FORCE ROW LEVEL SECURITY`.** Sem `FORCE`, o dono
   das vistas (`qs_app`) contornaria a RLS quando o reader lê através delas.
3. **[nova] Nenhuma vista expõe email nem telefone.** O plano previa `v_customers_analyst` sem PII;
   não há vista com PII para papel nenhum. Mais restritivo do que o pedido, sem perda de funcionalidade.
4. **Um role de login por vendedor (migrações 006–007).** `qs_reader_s1..s3` têm credenciais próprias,
   não são membros uns dos outros e a RLS associa `session_user` ao vendedor. O validador continua a
   separar tabelas por papel funcional (`seller_analyst`/`seller_finance`). A API recebe os três
   segredos nesta implantação; comprometê-la expõe todos os vendedores, pelo que o isolamento forte
   exige serviços e cofres de segredo separados.
5. **Tenant derivado da identidade do role.** Uma falha antiga permitia mudar `app.seller_id` com
   SQL na sessão (`docs/security-review.md`, A1). A migração 006 remove esse caminho: os roles de
   vendedor não podem alterar o seu papel e a RLS consulta o mapeamento privado
   `qs_private.seller_roles` por `session_user`, incluindo ao aceder por vistas. `qs_api.begin_request(timeout_ms)` só define o
   `statement_timeout` local à transacção.
6. **Seed determinístico** com `random.Random(20261120)`, sem relógio nem `hash()`.

## Validação

7. **O validador analisa a árvore, não o texto** (SQLGlot, dialecto PostgreSQL). A alternativa regex
   foi demonstrada inferior em `tests/unit/test_regex_vs_ast.py`.
8. **Joins só por igualdades listadas.** Sem regra genérica de `seller_id`, para que `payouts` não se
   junte a `customers`.
9. **[nova] Função: deny-by-default.** Só as classes em `ALLOWED_FUNCTIONS` passam; qualquer função
   desconhecida (`exp.Anonymous`) é recusada, mesmo sem estar na lista de perigosas.
10. **[nova] `%` dentro de literais de texto é recusado** (`literal_percent_not_allowed`). Com parâmetros,
    o psycopg trata `%` como marcador; um `LIKE '%x%'` partiria a execução. Limitação: pesquisas com `LIKE`
    não funcionam nesta fase.
11. **[nova] Parâmetros posicionais (`%s`, `?`) recusados.** Só `%(nome)s`.
12. **[nova] `LIMIT` ou agregação obrigatórios na consulta externa.** Uma consulta sem nenhum dos dois é
    recusada, mesmo que seja segura. É uma escolha de segurança (linhas brutas ilimitadas).
13. **[nova] Joins com subquery** são aceites se a coluna real participar numa aresta permitida. A
    subquery interna é validada, mas a sua saída não é provada como relação permitida (limite conhecido).
14. **[nova] Comparação de tipos exacta** (`type(node) in FORBIDDEN_NODES`) em vez de `isinstance`.

## Execução

15. **[nova] O executor corre o SQL original validado, embrulhado** em `SELECT * FROM (...) LIMIT n+1`,
    e não a versão reescrita pelo SQLGlot (que troca `%(x)s` por `:x`). O hash regista o texto validado.
16. **[nova] Erros traduzidos para códigos genéricos.** A mensagem do driver nunca é devolvida (pode
    conter host, utilizador ou SQL).
17. **[nova] `EXPLAIN` sem `ANALYZE`, com a mesma transacção read-only.** Mostra o plano sem executar.
    O plano mostra o filtro de RLS, o que se verificou.

## API

18. **[nova] `POST /auth/demo-login`.** O plano não previa login. Desactivado por omissão
    (`QS_DEMO_AUTH=false`), sem palavra-passe; é só para demonstração.
19. **[nova] `POST /query/generate` devolve também a validação e a verificação.** Não executa nada.
20. **[nova] `POST /query/execute` valida sempre de novo.** O `validated_hash` do cliente só prova que o
    SQL não mudou (`409 not_validated` se mudou). Nunca substitui a validação.
21. **[nova] Histórico e registo de hashes em memória por processo.** Sem base de dados própria; reiniciar
    apaga-os. Limite conhecido.
22. **[nova] Erros com envelope único** `{"error": {"code", "message", ...}}`.
23. **[nova] `/health` reporta o estado da base de dados** (`ok`, `unavailable`, `not_configured`) sem detalhes.

## Verificação

24. **Avisos não bloqueiam; marcam `verified: false`.** A heurística tem falsos positivos e negativos.
25. **Fan-out avaliado por `SELECT`.** Uma regra global daria falso positivo na receita correcta (que usa
    uma subquery pré-agregada com `returns`).

## Gerador e frontend

26. **[nova] Mock determinístico rotulado** (`provider: mock`), com um conjunto fixo de intenções. Não é
    um LLM. O provider OpenAI-compatível está implementado e testado offline; não foi usado com chave real.
27. **[nova] Feedback só local.** O plano pede um botão de feedback, mas não define endpoint; o botão
    guarda a escolha apenas no estado da página.
28. **[nova] Token só em memória no frontend** (nada em `localStorage`).
29. **[nova] Frontend em JavaScript (JSX), não TypeScript**, e sem router: uma única vista.
30. **[nova] Portas de desenvolvimento** 18200 (API) e 13200 (frontend), por pedido da coordenação.

## Avaliação

31. **[nova] Golden validado pelo validador antes de ser executado.** Um golden que não passa a validação
    faz o build falhar, em vez de virar resultado esperado.
32. **[nova] Desempate determinístico nos golden com `ORDER BY ... LIMIT`.** A regeneração detectou
    empates indefinidos; corrigido.
33. **[nova] Ablation e baseline são código de laboratório** em `eval/`, nunca expostos pela API. A baseline
    só corre numa base com `sandbox` no nome, criada pelo próprio runner.
34. **[nova] Na baseline, a sessão resolve os nomes como a app e não há RLS** (sandbox descartável). Sem
    isto, quase todos os ataques falhavam por `UndefinedTable`, e o resultado não mediria nada.
35. **[nova] Relatório separa accuracy, respostas erradas e sem resposta.** Uma accuracy média esconderia
    as 8 respostas erradas que o validador não recusou.

## Infra de entrega

36. **[nova] Docker e CI validados só como YAML.** Não há Docker neste ambiente.
37. **[nova] `.gitattributes` com `* text=auto`** e linhas `binary` para pdf, png, jpg e sqlite (pedido da coordenação).
