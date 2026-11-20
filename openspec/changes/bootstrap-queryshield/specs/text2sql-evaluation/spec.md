# Spec Delta

## Purpose

Medir se o sistema dá resultados correctos e se bloqueia o que deve bloquear, comparando resultados executados com respostas golden.

## ADDED Requirements

### Requirement: Perguntas golden com resultados
O projecto SHALL incluir pelo menos 100 perguntas com SQL golden e resultado esperado calculado a partir do seed, cobrindo agregações, filtros de datas, joins entre várias tabelas, perguntas ambíguas e ataques de prompt injection.

#### Scenario: Regenerar resultados esperados
- **WHEN** o seed é recriado
- **THEN** os resultados esperados são recalculados a partir do SQL golden e coincidem com os guardados

### Requirement: Execution accuracy
O runner SHALL comparar os resultados normalizados (ordem, tipos numéricos, arredondamento) do SQL gerado com os do golden e reportar a execution accuracy, a taxa de SQL válido, os erros de interpretação de métricas, a latência e o custo.

#### Scenario: Ordem diferente
- **WHEN** o SQL gerado devolve as mesmas linhas por outra ordem numa pergunta sem ordenação pedida
- **THEN** conta como correcto

### Requirement: Suite de ataques
O projecto SHALL incluir testes para `DROP`, `UPDATE`, leitura de tabela secreta, `WITH` malicioso, comentários SQL, multi-statement, `CROSS JOIN` explosivo, acesso cross-tenant e consultas longas, e MUST reportar a taxa de rejeição e em que camada cada ataque foi travado (validador ou base de dados).

#### Scenario: Ataque travado pela base de dados
- **WHEN** o validador é desactivado num teste de laboratório
- **THEN** o relatório mostra quais ataques a base de dados ainda bloqueou

### Requirement: Baseline insegura só em sandbox
Uma comparação com geração directa sem protecções MAY ser feita apenas num sandbox offline, sem dados reais e sem exposição de rede, e o relatório MUST identificá-la como tal.

#### Scenario: Comparação de segurança
- **WHEN** a baseline insegura corre no sandbox
- **THEN** o relatório mostra os ataques que ela deixaria passar e os que o QueryShield bloqueia
