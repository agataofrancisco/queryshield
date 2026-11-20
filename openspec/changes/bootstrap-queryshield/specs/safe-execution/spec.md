# Spec Delta

## Purpose

Executar as queries aprovadas com o menor privilégio possível, garantindo na própria base de dados o isolamento por vendedor e limites de recursos.

## ADDED Requirements

### Requirement: Ligação só de leitura e separada
A execução MUST usar uma ligação PostgreSQL dedicada, com um role sem privilégios de escrita e sem acesso a tabelas privadas, distinta da ligação da aplicação, numa transacção `READ ONLY`.

#### Scenario: Tentativa de escrita na base de dados
- **WHEN** uma escrita chega ao executor
- **THEN** o PostgreSQL recusa com um erro de privilégio ou de transacção só de leitura

### Requirement: Isolamento por tenant na base de dados
O isolamento entre vendedores MUST ser aplicado por Row-Level Security com o `seller_id` da sessão autenticada, definido pelo servidor e não pelo SQL gerado.

#### Scenario: SQL sem filtro de vendedor
- **WHEN** o SQL gerado não filtra por `seller_id`
- **THEN** o resultado contém apenas linhas do vendedor autenticado

#### Scenario: SQL que tenta outro vendedor
- **WHEN** o SQL filtra `WHERE seller_id = 'outro'`
- **THEN** o resultado vem vazio

### Requirement: Limites de recursos
A execução SHALL aplicar `statement_timeout` curto, limite de linhas devolvidas e limite de tamanho do resultado. Ao exceder um limite, a query MUST ser cancelada com um erro claro.

#### Scenario: Query lenta
- **WHEN** uma query excede o `statement_timeout`
- **THEN** é cancelada e a API devolve `code: "query_timeout"`

### Requirement: Execução condicionada à política
`POST /query/execute` SHALL executar apenas SQL que passou na validação no mesmo pedido ou num pedido anterior identificado por hash, e MUST recusar SQL alterado desde a validação.

#### Scenario: SQL alterado após validação
- **WHEN** o cliente envia para execução um SQL diferente do validado
- **THEN** a execução é recusada com `not_validated`

### Requirement: Credenciais protegidas
Connection strings e credenciais NÃO SHALL aparecer em respostas, logs ou no frontend.

#### Scenario: Erro de ligação
- **WHEN** a base de dados não está acessível
- **THEN** a resposta diz `database_unavailable` sem o host, o utilizador ou a password
