# 01 — Semantic layer

## O problema

Quando alguém pergunta "qual foi a receita de março?", há pelo menos três respostas possíveis: a soma de todos os pagamentos, a soma dos itens de encomendas válidas, ou essa soma menos devoluções. Um modelo que não conhece a definição escolhe uma ao acaso, e o SQL é válido em todas.

Também há o problema do schema: se o modelo recebe todas as tabelas da base, pode usar colunas de PII ou tabelas internas.

A semantic layer resolve os dois: define **uma vez** o significado das métricas e o schema visível por papel, e todos os componentes leem a mesma fonte.

## O que entra e o que sai

Entra: `semantic/schema.yaml` e `semantic/metrics.yaml`. Sai: um modelo tipado (`SemanticModel`) e, por papel, a vista que o modelo e a API veem.

Saída real de `GET /schema/semantic` para o papel `seller_analyst` (executada com `uvicorn`):

```
role seller_analyst tables ['sellers', 'categories', 'customers', 'products', 'orders', 'order_items', 'returns']
customers cols ['id', 'seller_id', 'full_name', 'city', 'created_on']
metrics ['periodo', 'venda', 'encomenda_valida', 'receita', 'devolucao']
joins 11
```

O analista não vê `payouts` nem `payments`, e `customers` não tem `email` nem `phone`.

## Como funciona por dentro

- `semantic/schema.yaml`: tabelas com colunas, tipo e descrição; papéis por tabela (`roles`) e, opcionalmente, por coluna (`roles` na coluna); e a lista de `joins` permitidos, cada um como `tabela.coluna -> tabela.coluna`.
- `semantic/metrics.yaml`: para cada métrica, `canonical_sql` (documentação e exemplo para o prompt), e dois campos que a verificação usa: `signature` (a agregação que identifica a métrica no SQL, por exemplo `SUM(order_items.line_total)`) e `requires_tables` / `requires_filter_columns` (o que uma consulta correcta tem de conter).
- `backend/app/semantic/models.py`: modelos pydantic com `extra="forbid"`. Um campo desconhecido no YAML falha em vez de ser ignorado.
- `backend/app/semantic/loader.py:load_semantic_model`: valida as referências cruzadas. Um join para `sellers.nope` ou uma métrica que aponta para uma coluna inexistente levanta `SemanticConfigError` **ao arrancar**. Os testes `test_semantic_loader_rejects_join_to_missing_column` e `test_semantic_loader_rejects_unknown_role` cobrem os dois casos.
- `backend/app/semantic/view.py:build_role_view`: filtra tabelas, colunas e joins pelo papel. Um join só aparece se as duas tabelas forem visíveis ao papel.
- `backend/app/api/routes_schema.py`: `GET /schema/semantic` exige token e devolve só a vista do papel do token.

### Porque é que o YAML não é o único controlo

O YAML define o que a aplicação *mostra* e *valida*. O que a base de dados *permite* está nas vistas de `db/migrations/004_views.sql`, com isolamento por role/RLS reforçado em `db/migrations/006_per_seller_roles.sql`. Um teste (`tests/postgres/test_semantic_matches_db.py`) compara as vistas com a configuração coluna a coluna: se alguém acrescentar uma coluna ao YAML que a vista não expõe, o teste falha.

## Porquê esta escolha

- **Fonte única.** O prompt (tarefa 4.1), o validador (3.1), a verificação (5.1) e a API leem o mesmo ficheiro. Não há cópias que possam divergir.
- **Ficheiros, não código.** Um analista de negócio pode rever `metrics.yaml` sem ler Python.
- **Validação na leitura.** Um YAML errado não chega a produção: falha no arranque.
- **Papel como filtro, não como excepção.** O analista nunca recebe `payouts` no contexto, por isso o modelo não pode sequer referi-la de forma correcta.

## Alternativas

- **Schema completo no prompt e validação a posteriori.** Dá ao modelo mais informação que não deve ter, e a validação tem de compensar.
- **Ontologia ou OWL.** Mais expressiva, mas excessiva para 10 tabelas e 5 métricas, e difícil de testar.
- **Métricas só em código Python.** Funciona, mas o negócio deixa de conseguir rever as definições.

## Como falha

- Join para coluna inexistente: `test_semantic_loader_rejects_join_to_missing_column`.
- Papel desconhecido: `test_semantic_loader_rejects_unknown_role`.
- Analista vê PII ou tabelas de finanças: `test_analyst_sees_customers_without_email_or_phone`, `test_analyst_does_not_see_finance_tables`.
- Tabela secreta em qualquer vista: `test_secret_table_never_appears_in_any_role_view`.
- YAML e base de dados divergem: `test_semantic_tables_and_columns_match_reader_views`.

Limitação: a semantic layer não impede o modelo de escolher uma métrica errada *dentro* das definições disponíveis. Isso é tratado pela verificação (tarefa 5.1) e medido na avaliação (tarefa 7.2).

## Perguntas de entrevista

**1. Porque é que `receita` é definida em YAML e não só no prompt?**
Porque o prompt é probabilístico e a definição tem de ser determinística. O YAML é usado para gerar o prompt, para verificar o SQL e para documentar a API. Se a definição mudar, muda em todos os sítios.

**2. O que significa `extra="forbid"` nos modelos?**
Que um campo desconhecido no YAML é um erro. Um erro de digitação (`requires_table:` em vez de `requires_tables:`) não passa silenciosamente como "sem requisitos".

**3. Porque é que os joins são uma lista explícita?**
Porque uma regra genérica ("qualquer `seller_id = seller_id` é permitido") deixaria `payouts` juntar-se a `customers` directamente, o que a spec proíbe. Uma lista explícita é mais verbosa e mais segura.

**4. Como se testa que a semantic layer não mente sobre a base de dados?**
Comparando os nomes das colunas das vistas (`information_schema`) com o YAML num teste de PostgreSQL real. Foi o que fizemos.

**5. Porque é que `canonical_sql` não é executado?**
Porque é um exemplo, com parâmetros nomeados e sem garantias de forma. Executar texto de documentação seria criar uma segunda porta de entrada de SQL. O que se executa é sempre o SQL validado.
