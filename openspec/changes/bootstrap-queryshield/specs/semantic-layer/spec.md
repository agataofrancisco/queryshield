# Spec Delta

## Purpose

Definir de forma explícita e única o significado das métricas de negócio e a parte do schema que cada papel pode ver, para o modelo e para os humanos.

## ADDED Requirements

### Requirement: Definições de métricas
A semantic layer SHALL definir `venda`, `receita`, `devolução`, `encomenda válida` e `período` com expressão SQL canónica, filtros obrigatórios e unidade. `GET /schema/semantic` SHALL devolver estas definições.

#### Scenario: Definição de receita
- **WHEN** um utilizador consulta a semântica
- **THEN** `receita` aparece como a soma dos itens de encomendas válidas, menos as devoluções, em AOA, com os filtros de estado explícitos

### Requirement: Schema visível por papel
O contexto enviado ao modelo e devolvido pela API MUST conter apenas as tabelas e colunas permitidas ao papel do utilizador. Colunas sensíveis (por exemplo, email e telefone de clientes) NÃO SHALL ser mostradas a papéis sem permissão.

#### Scenario: Analista sem PII
- **WHEN** um `seller_analyst` pede o schema
- **THEN** a tabela `customers` aparece sem `email` nem `phone`

### Requirement: Joins permitidos
A semantic layer SHALL declarar os caminhos de join permitidos entre tabelas. Joins fora desta lista MUST ser rejeitados pela validação.

#### Scenario: Join não declarado
- **WHEN** o SQL junta `payouts` com `customers` directamente
- **THEN** a validação rejeita com `join_not_allowed`
