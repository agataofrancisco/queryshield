# Spec Delta

## Purpose

Detectar SQL que corre mas responde à pergunta errada, verificando o schema, os joins, as unidades e a consistência com as definições de métricas.

## ADDED Requirements

### Requirement: Consistência com a semantic layer
O sistema SHALL verificar se as métricas usadas no SQL correspondem às definições canónicas (filtros obrigatórios, agregação, unidade). Divergências MUST gerar um aviso ou rejeição, conforme a gravidade.

#### Scenario: Receita sem excluir devoluções
- **WHEN** o SQL calcula a receita sem subtrair as devoluções
- **THEN** a resposta inclui o aviso `metric_definition_mismatch: receita` e não é marcada como verificada

### Requirement: Detecção de alucinação de schema
Colunas, tabelas ou valores de enum inexistentes SHALL ser detectados antes da execução, com sugestão de correcção quando possível.

#### Scenario: Coluna inexistente
- **WHEN** o SQL usa `orders.total_value`, que não existe
- **THEN** é rejeitado com `unknown_column` e a sugestão `orders.total_amount`

### Requirement: Explicação ao utilizador
Cada resposta executada SHALL incluir o SQL, os filtros aplicados em linguagem natural, as tabelas de origem, o número de linhas, as suposições e os avisos.

#### Scenario: Resposta com suposição
- **WHEN** o período foi assumido como o mês corrente
- **THEN** a explicação diz explicitamente a suposição

### Requirement: Dúvida leva a esclarecimento
Quando a verificação tem dúvidas sérias (métrica ambígua, join suspeito), o sistema MUST pedir esclarecimento ou rejeitar, em vez de apresentar o resultado como fiável.

#### Scenario: Join suspeito
- **WHEN** um join duplica linhas e infla a soma (fan-out)
- **THEN** o sistema avisa `possible_fanout` e não marca o resultado como verificado
