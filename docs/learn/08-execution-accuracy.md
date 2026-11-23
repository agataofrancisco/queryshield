# 08 — Execution accuracy e a avaliação

## O problema

Como se sabe se um sistema text-to-SQL "funciona"? Comparar o SQL gerado com o SQL de referência (exact match) é um erro: `SELECT id FROM orders WHERE 1=1` e `SELECT id FROM orders` são equivalentes, e duas consultas diferentes podem devolver o mesmo número. A pergunta útil é: **o resultado está certo?**

Este documento explica a métrica *execution accuracy*, as regras de normalização, e o que o relatório actual mede (e o que não mede).

## O que entra e o que sai

Entra: 164 perguntas (`eval/questions.jsonl`) e 140 resultados golden (`eval/expected.jsonl`), calculados a partir do seed, não escritos à mão. Sai: `eval/reports/report-mock.json`, com métricas, uma linha por pergunta e a camada que travou cada ataque.

Saída real da execução (`python -m eval.run_eval`):

```
execution_accuracy=0.5143 valid_sql_rate=0.9639 p50=9.7ms p95=75.26ms
ataques: 15/15 passaram; validador=14 base_de_dados_sem_validador=12
```

Métricas do relatório (`metrics`):

| Métrica | Valor | Como se calcula |
|---|---|---|
| Execution accuracy | 0.5143 (72/140) | perguntas com resultado esperado cujo resultado normalizado é igual ao golden |
| Valid SQL rate | 0.9639 (80/83) | SQL gerado que passa a validação AST |
| Respostas erradas (não recusadas) | 8 | `answered` com resultado diferente do golden |
| Sem resposta (`unsupported`) | 63 | o gerador não tem a intenção |
| Erros de definição de métrica | 0 | avisos `metric_definition_mismatch` nas consultas geradas |
| Latência (mock, ponta a ponta) | p50 9.7 ms, p95 75.26 ms | medido na máquina de desenvolvimento |
| Custo | n/a | provider `mock`, 0 tokens. `TODO: medir com LLM real` |

## Como funciona por dentro

- **Golden.** `eval/build_expected.py` valida cada SQL golden com o **mesmo validador** de produção antes de o executar. Um golden que não passa a validação faz o build falhar (`GoldenInvalid`): não se pode tornar um resultado esperado sem ser executável. Depois executa-o como o papel e o tenant da pergunta, com o executor de produção.
- **Normalização** (`eval/normalize.py`). Números são comparados com 2 casas e arredondamento half-up: `8529600`, `"8529600.00"` e `Decimal("8529600")` são iguais. `NULL` é diferente de `0`. Sem `ORDER BY` no golden, a comparação é um **multiconjunto** (a ordem é irrelevante); com `ORDER BY`, a ordem conta.
- **Comparação.** `results_equal` compara as linhas normalizadas. O runner (`eval/run_eval.py:_answer_question`) só conta uma resposta como correcta se a execução tiver êxito **e** o resultado for igual.
- **Ataques.** Não passam pelo gerador: o SQL do ataque é entregue directamente, como se um modelo comprometido o tivesse produzido. Cada ataque é medido em duas fases (`_run_attack`): primeiro o validador; depois, se o validador deixar passar, a experiência de laboratório (`eval/ablation.py`) executa o SQL como instrução de topo, com o validador ignorado, e regista a camada que o travou.

## Os números e o que significam

Por categoria (perguntas com resultado esperado):

| Categoria | Correctas / total | Leitura |
|---|---|---|
| receita (mês a mês, 2 vendedores) | 36 / 36 | o mock cobre esta intenção |
| encomendas válidas (mês a mês) | 36 / 36 | o mock cobre esta intenção |
| devoluções (mês a mês) | 0 / 36 | **falha do mock**: reconhece "devolução" mas não "devolvido" |
| itens vendidos | 0 / 18 | fora da cobertura do mock |
| join multi-tabela (categoria, top produtos) | 0 / 6 | fora da cobertura; 4 destas perguntas recebem uma resposta **errada** (ver abaixo) |
| encomendas canceladas | 0 / 4 | 4 respostas **erradas**: contou encomendas válidas |
| comissões (só finanças) | 0 / 2 | fora da cobertura |
| clientes por cidade | 0 / 2 | fora da cobertura |
| ambíguas (melhores clientes) | 3 / 4 | a 4.ª ("quem compra mais?") não tem intenção no mock |
| injeção (pedidos de contactos) | 5 / 5 | nenhum dado vazou (3 bloqueadas pelo validador, 2 sem resposta) |

**O número que mais importa não é a accuracy: são as 8 respostas erradas que não foram recusadas.** Quatro são "receita por categoria" a responder com a receita total; quatro são "encomendas canceladas" a responder com a contagem de encomendas válidas. Cada SQL é válido e canónico. O validador aceita-os, e a verificação semântica **não avisou** (0 avisos), porque verifica se a *definição* da métrica está correcta, não se a *intenção* da pergunta foi respeitada. Este é o modo de falha mais perigoso do sistema: um número plausível, com SQL correcto, sobre a pergunta errada. Não o escondemos numa accuracy média: o relatório conta-o à parte.

**Falha do mock, sem ajuste à avaliação.** As 36 perguntas de devoluções falham porque o mock procura o radical "devolu", e "devolvido" não o contém. Podíamos ter alargado a palavra-chave para subir a métrica; não o fizemos, porque ajustar o mock ao conjunto de avaliação tornaria o número inútil.

**Sobreposição declarada.** A definição de receita, devoluções e encomendas válidas é a mesma no mock e nos resultados golden (ambos seguem `semantic/metrics.yaml`). Por isso os 100% nessas categorias medem sobretudo o pipeline, não a capacidade de um modelo. Os golden de categorias fora do mock foram escritos para serem independentes do gerador.

## Porquê esta escolha

- **Execução em vez de texto.** Duas consultas diferentes podem dar o mesmo resultado; comparar texto penaliza soluções correctas.
- **Golden calculado, não escrito à mão.** O resultado vem da base de dados com o mesmo executor de produção. A regeneração é verificada: `test_golden_results_regenerate_identically` reconstrói o ficheiro e compara byte a byte.
- **Normalização explícita.** Cada regra (2 casas, `NULL` ≠ 0, multiconjunto sem `ORDER BY`) tem um teste em `tests/unit/test_eval_normalize_and_catalog.py`.
- **Métricas separadas.** Accuracy, respostas erradas, sem resposta e validade do SQL respondem a perguntas diferentes e não se devem somar.

## Alternativas

- **Exact match do SQL.** Penaliza equivalências e não diz nada sobre o resultado.
- **Juiz LLM.** Útil para perguntas abertas, mas introduz o próprio modelo como juiz e custo. Não é necessário para resultados tabulares.
- **Accuracy única.** Esconderia as 8 respostas erradas numa média.

## Como falha

Testes:

- Normalização: `test_values_normalise_to_two_decimals_and_keep_null`, `test_null_result_does_not_match_zero_result`, `test_row_order_is_irrelevant_without_order_by`, `test_row_order_matters_when_golden_has_order_by`.
- Regeneração idêntica do golden (PostgreSQL real): `tests/postgres/test_eval_postgres.py::test_golden_results_regenerate_identically`.

**Defeito encontrado e corrigido pela regeneração.** Duas consultas golden usavam `ORDER BY ... LIMIT` sem desempate: cidades com o mesmo número de clientes apareciam em ordem indefinida. Com `ordered=True` isto torna a pontuação dependente da sorte. A correcção foi um desempate determinístico (`ORDER BY clientes DESC, cidade`), e o teste de regeneração passa agora byte a byte.

**Limitações conhecidas.**

- O número é de um gerador mock com um conjunto fixo de intenções (receita, devoluções, encomendas válidas, clarificação de "melhores clientes" e o caso de contactos). **Não é um resultado de LLM.** Não houve chave de API neste ambiente; a avaliação com LLM fica pendente (`TODO: medir`).
- A amostra é de 164 perguntas geradas a partir de modelos; não cobre a variedade de linguagem natural real.
- A latência é medida num portátil de desenvolvimento com PostgreSQL local, não num ambiente de produção.
- O campo `git_commit` do relatório regista o último commit (`c92c688`); a avaliação em si foi gerada sobre alterações ainda não commitadas.

## Perguntas de entrevista

**1. Porque é que não se compara o SQL gerado com o SQL de referência?**
Porque há muitas formas equivalentes de escrever a mesma consulta. O que o utilizador precisa é do resultado. Comparar texto penaliza soluções correctas e premeia consultas textualmente parecidas mas erradas.

**2. O que é `NULL` vs `0` na comparação e porque importa?**
Uma soma sobre um conjunto vazio é `NULL` em SQL, não `0`. Tratá-los como iguais esconderia a diferença entre "não houve vendas" e "houve vendas de zero". Por isso a normalização não os iguala.

**3. Quando é que a ordem das linhas conta?**
Só quando o golden tem `ORDER BY`. Sem ele, o resultado é um multiconjunto. Com `ORDER BY` e empates, a ordem é indefinida: é preciso um desempate, como encontrámos.

**4. Porque é que as respostas erradas são uma métrica separada?**
Porque uma resposta errada com SQL válido é o pior caso: parece plausível e não é recusada. Uma accuracy média esconde-a. O relatório conta-a à parte, com 8 casos concretos.

**5. Porque é que o golden passa pelo validador?**
Para que um golden inválido não se torne resultado esperado. Se um golden fosse rejeitado em produção, o build da avaliação falha em vez de contar uma resposta como "errada" injustamente.

**6. Porque é que 100% em receita não prova que o sistema funciona?**
Porque o mock e o golden usam a mesma definição canónica. Essa categoria mede o pipeline (validação, execução, normalização), não a capacidade de interpretar uma pergunta nova. Declaramos a sobreposição no relatório.

**7. Qual é a diferença entre "sem resposta" e "resposta errada"?**
Sem resposta é um custo de cobertura (o sistema diz que não sabe). Resposta errada é um risco de confiança (o sistema responde com confiança). Por isso medimos e reportamos os dois separadamente.
