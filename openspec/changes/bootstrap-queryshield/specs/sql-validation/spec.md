# Spec Delta

## Purpose

Rejeitar antes da execução qualquer SQL que não seja uma leitura simples, permitida e inequívoca, analisando a árvore sintáctica e não o texto.

## ADDED Requirements

### Requirement: Uma única leitura
O validador SHALL fazer parse em dialecto PostgreSQL e MUST rejeitar múltiplos statements, qualquer comando de escrita (`INSERT`, `UPDATE`, `DELETE`, `MERGE`), DDL, controlo de transacções, `COPY`, `SET` e `CALL`.

#### Scenario: Multi-statement
- **WHEN** o SQL é `SELECT 1; DROP TABLE orders`
- **THEN** é rejeitado com `multiple_statements`

#### Scenario: Comentário a esconder escrita
- **WHEN** o SQL contém `/* */` ou `--` a tentar esconder um segundo comando
- **THEN** o parse detecta a estrutura real e a query é rejeitada

### Requirement: Allowlist de tabelas, colunas e funções
Todas as tabelas, colunas e funções referidas MUST estar na allowlist do papel. Funções perigosas (por exemplo `pg_sleep`, `pg_read_file`, `dblink`, `lo_import`) MUST ser sempre rejeitadas.

#### Scenario: Tabela secreta
- **WHEN** o SQL lê `internal_fraud_flags`
- **THEN** é rejeitado com `table_not_allowed`

#### Scenario: Função perigosa
- **WHEN** o SQL usa `pg_sleep(10)`
- **THEN** é rejeitado com `function_not_allowed`

### Requirement: CTEs e subqueries seguras
CTEs e subqueries SHALL ser permitidas apenas se forem leituras que cumprem as mesmas regras. CTEs com side effects (`WITH ... DELETE`) MUST ser rejeitadas.

#### Scenario: WITH malicioso
- **WHEN** o SQL é `WITH x AS (DELETE FROM orders RETURNING *) SELECT * FROM x`
- **THEN** é rejeitado com `write_in_cte`

### Requirement: Explosão combinatória
O validador SHALL rejeitar `CROSS JOIN` e joins sem condição entre tabelas grandes e MUST exigir `LIMIT` ou agregação nas queries que devolvem linhas brutas.

#### Scenario: CROSS JOIN explosivo
- **WHEN** o SQL faz `orders CROSS JOIN order_items`
- **THEN** é rejeitado com `cartesian_product`

### Requirement: Validação não substitui a base de dados
O resultado da validação SHALL ser registado, mas a execução MUST aplicar as protecções da base de dados mesmo que a validação passe.

#### Scenario: Bug no validador
- **WHEN** um teste desactiva o validador e envia um `UPDATE`
- **THEN** a base de dados recusa por falta de privilégio
