# 10 — Perguntas de entrevista

Cada resposta aponta para o código ou para o teste que a sustenta. Se uma resposta não se pode
verificar no repositório, não está aqui.

## Segurança e base de dados

**1. Porque é que o executor não usa a ligação da aplicação?**
Porque essa ligação tem privilégios de gestão. O executor usa um role por vendedor
(`qs_reader_s<N>`), que só lê vistas, sem escrita e com `default_transaction_read_only = on`
(`db/migrations/006_per_seller_roles.sql`).

**2. O que é RLS e porque não basta um `WHERE seller_id = ...` no SQL?**
RLS é uma política aplicada pelo motor a cada linha, independente do SQL. Um `OR 1=1` ou uma subquery não a
contorna. A política actual deriva o vendedor do login `session_user` (`test_each_seller_role_sees_only_its_own_rows`).

**3. O que faz `FORCE ROW LEVEL SECURITY` e porque o usamos?**
Aplica a política também ao dono da tabela. Sem ele, as vistas (de `qs_app`) leriam sem RLS. Teste:
`test_owner_role_is_subject_to_rls_because_of_force`.

**4. Como se define o tenant sem injecção?**
O tenant é a identidade do role de login, mapeado para `seller_id` dentro da política RLS. O SQL não
escolhe nem altera essa identidade; `qs_api.begin_request(timeout_ms)` define apenas o timeout.

**5. Porque é que `set_config` já não controla a RLS?**
Uma variável de sessão podia ser alterada por SQL no mesmo pedido. A migração 006 removeu essa
dependência e mapeia roles fixos para vendedores. O teste de ataques de sessão está em
`test_raw_session_attacks_cannot_change_visibility`.

**6. O que impede o tenant de vazar entre pedidos que reutilizam a ligação do pool?**
Cada pool usa sempre o mesmo role de vendedor, e a ligação não muda de identidade entre pedidos.
O timeout é local à transacção; a deadline da aplicação usa a mesma credencial do vendedor.

**7. Porque é que as vistas não expõem email nem telefone?**
Porque uma coluna que não existe na vista não pode ser lida por nenhum SQL, nem por sintaxe criativa. Teste:
`test_customers_view_has_no_pii_columns`.

**8. O que acontece com `pg_sleep` se o validador falhar?**
A base de dados não o bloqueia; só o timeout o interrompe. Por isso o validador o recusa por nome.
Medido em `eval/reports/report-mock.json`: travado pelo timeout de 3 s.

**9. Porque é que a baseline insegura não é contada como protecção em todos os casos?**
Porque sete dos oito bloqueios são de integridade referencial, nomes que resolvem para vistas, colunas
inexistentes ou o guarda do runner. Não são protecções de segurança (`docs/learn/09`).

**10. Porque é que se mede a base de dados com o validador desligado?**
Para não confiar no parser. Se a base de dados não travar um ataque, a segurança depende só do validador.
Medido por `eval/ablation.py`.

## Validação e SQL

**11. Porque é que não se usa uma lista negra de palavras (`DROP`, `DELETE`)?**
Porque é finita (esquece `TRUNCATE`), bloqueia texto que não é código (um literal `'DROP'`) e não vê
comentários. Ver `tests/unit/test_regex_vs_ast.py`.

**12. O que é um AST e como o validador o usa?**
A árvore sintáctica do SQL. O validador percorre-a com tipos de nó: `Insert`, `Table`, `Column`, `Func`,
`Join`. Não procura palavras (`backend/app/validation/ast_validator.py`).

**13. Porque é que `AND` e `OR` aparecem como funções no SQLGlot?**
Porque os operadores são subclasses de `Func`. Por isso há uma lista separada de operadores
(`OPERATOR_NODES` em `policy.py`), e a allowlist de funções não os recusa.

**14. Porque é que a comparação de tipos é exacta?**
Para que uma mudança de hierarquia no SQLGlot não altere o que é proibido. Teste:
`test_union_is_not_a_set_node_so_forbidden_check_stays_exact`.

**15. Porque se executa o SQL original validado e não o reescrito pelo SQLGlot?**
Porque o SQLGlot troca `%(x)s` por `:x`. O que se valida deve ser exactamente o que se executa.

**16. Porque é que um produto cartesiano com `WHERE` é recusado?**
Porque a regra é conservadora: a forma `FROM a, b` é recusada mesmo com `WHERE`. Preferimos recusar a aceitar
um produto por engano. Teste: `test_comma_join_with_where_is_refused_on_purpose`.

**17. Porque é que `%` dentro de um literal é recusado?**
Porque com parâmetros o psycopg interpreta `%`. Um `LIKE '%x%'` partiria a execução. É uma limitação
declarada em `docs/decisions.md`.

**18. O que é o hash do SQL validado e para que serve?**
Um SHA-256 do texto canónico. O cliente envia-o em `validated_hash`; se não corresponder ao SQL enviado,
a execução é recusada com `not_validated`. Teste: `test_changed_sql_after_validation_is_refused`.

## Geração e LLMs

**19. Porque é que a pergunta do utilizador é tratada como dado?**
Porque pode conter instruções. Vai delimitada no prompt, o delimitador é neutralizado, e a resposta do modelo
é validada de novo. Teste: `test_question_cannot_close_the_data_delimiter`.

**20. Porque é que o mock existe se não é um modelo?**
Para testar o pipeline inteiro offline. Todas as suas respostas levam `provider: mock`, para nunca se confundir
com um LLM.

**21. O que acontece se o modelo devolver JSON válido com tipos errados?**
É rejeitado com `generation_invalid_output` por validação pydantic com limites. Testes em
`test_invalid_model_output_is_rejected_with_a_generic_code`.

**22. Porque é que temperatura 0 não garante resultados iguais?**
Reduz a aleatoriedade, mas não a elimina. Por isso a correcção é medida, não assumida.

## Avaliação

**23. O que é execution accuracy e porque não se compara texto?**
A fracção de perguntas cujo resultado executado é igual ao golden. Duas consultas diferentes podem dar o mesmo
resultado, e comparar texto penaliza soluções correctas.

**24. Porque é que `NULL` não é igual a `0`?**
Uma soma sobre conjunto vazio é `NULL`. Igualá-los esconderia a diferença entre "sem vendas" e "vendas de zero".
Teste: `test_null_result_does_not_match_zero_result`.

**25. Quando a ordem das linhas conta?**
Só com `ORDER BY` no golden. Com empates, a ordem é indefinida; é preciso um desempate, como encontrámos.

**26. Porque é que as respostas erradas são uma métrica separada?**
Porque são o pior caso: parecem plausíveis e não são recusadas. Uma accuracy média esconderia as oito que
existem (`docs/learn/08`).

**27. Porque é que 100% em receita não prova que o sistema funciona?**
Porque o mock e o golden seguem a mesma definição canónica. Essa categoria mede o pipeline, não a
interpretação de perguntas novas. O relatório declara a sobreposição.

**28. Porque é que o golden passa pelo validador antes de ser executado?**
Para que um golden inválido não vire resultado esperado. Teste: a regeneração em
`tests/postgres/test_eval_postgres.py`.

## Verificação, fan-out e métricas

**29. O que é fan-out?**
Um join 1-N duplica as linhas do lado 1; somar o lado 1 depois disso inflaciona o total. Detectado por
`possible_fanout` em `backend/app/verification/checks.py`.

**30. Porque é que o aviso de fan-out não bloqueia a execução?**
Porque é uma heurística com falsos positivos. O sistema marca `verified: false`; decide o utilizador.

**31. Como se evita marcar a receita correcta como fan-out?**
Analisando as tabelas por `SELECT` (scope), e não em todo o SQL. Teste:
`test_fanout_is_judged_per_query_scope`.

**32. Qual é a diferença entre um erro de validação e `metric_definition_mismatch`?**
A validação decide o que pode ser executado. A verificação decide se a resposta respeita a definição de negócio.
Um SQL pode passar a primeira e falhar a segunda.

## Infra e processo

**33. Porque é que o frontend guarda o token só em memória?**
Para não deixar um token em `localStorage`, legível por qualquer script da página. Recarregar a página pede novo login.

**34. Porque é que há um error boundary em cada resposta?**
Para que um dado inesperado derrube só a secção afectada, e não o ecrã. Está em `ErrorBoundary.jsx`. Não
forcei nenhuma falha no browser: a verificação ficou por fazer.

**35. Porque é que o bundle é verificado por pesquisa de cadeias?**
Para garantir que não entram ligações de base de dados, nomes de papéis nem segredos no JavaScript. É uma
verificação simples e barata, que corre também no CI.

**36. O que faria para ter a revisão de segurança independente?**
Pedir a uma pessoa ou a outro agente, com o plano e o código, uma lista de ataques e as camadas a testar.
A auto-revisão está em `docs/security-review.md`, mas não substitui essa.

**37. Porque é que o pgserver é usado nos testes e não SQLite?**
Porque RLS, roles, `statement_timeout` e transacções read-only não têm equivalente fiel em SQLite.
Os testes provam o comportamento real do PostgreSQL.

**38. Qual é o risco de um pool de ligações com estado de sessão?**
Um estado que sobrevive à transacção pode vazar entre pedidos. Por isso o tenant é local à transacção e há
um teste de não-vazamento.
