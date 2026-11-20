# Spec Delta

## Purpose

Expor o pipeline por API e por uma interface de chat analítica que mostra sempre o SQL, os resultados e os avisos de segurança.

## ADDED Requirements

### Requirement: Endpoints
O sistema SHALL expor `POST /query/generate`, `POST /query/validate`, `POST /query/execute`, `GET /schema/semantic`, `GET /query/history` e `GET /health`. Todos, excepto o health, MUST exigir autenticação com tenant e papel.

#### Scenario: Sem autenticação
- **WHEN** um pedido chega a `/query/execute` sem token
- **THEN** recebe `401`

### Requirement: Histórico por utilizador
`GET /query/history` SHALL devolver apenas o histórico do utilizador (pergunta, SQL, estado, avisos), sem dados de resultado em bruto.

#### Scenario: Histórico isolado
- **WHEN** dois vendedores consultam o histórico
- **THEN** cada um vê só as suas perguntas

### Requirement: Explain seguro
O sistema SHALL oferecer `EXPLAIN` (sem `ANALYZE`) da query validada, para mostrar o plano sem a executar.

#### Scenario: Pedido de explain
- **WHEN** o utilizador pede o plano
- **THEN** recebe o plano de `EXPLAIN` e a query não é executada

### Requirement: Frontend analítico
O frontend SHALL ter o chat, o SQL com syntax highlight, a tabela de resultados, um gráfico quando adequado, os avisos de segurança, o explain e o botão de feedback.

#### Scenario: Pergunta bloqueada
- **WHEN** uma pergunta resulta em SQL rejeitado
- **THEN** o frontend mostra o motivo do bloqueio sem executar nada
