# Revisão de segurança independente

**Estado:** revisão estática concluída; achados e limites documentados.  
**Escopo:** código no commit `cfb254c` e alterações da árvore de trabalho em 2026-11-24.
**Método:** leitura independente de configuração, executor, autenticação, migração 006, compose e revisão anterior. Não foram executados testes, Docker nem PostgreSQL; portanto, alterações não commitadas e controlos da base de dados não foram confirmados em runtime.

## Achados

| ID | Severidade | Estado | Evidência e impacto |
|---|---|---|---|
| IR-1 | Alta | Implementado no código; runtime pendente | `SellerExecutors` passa o DSN do role do vendedor ao `QueryExecutor`, que usa esse mesmo role para cancelar apenas as suas sessões. `QS_CANCEL_DSN` e a credencial administrativa foram removidos do processo da API. Falta confirmar no PostgreSQL que o role pode cancelar as suas próprias sessões. |
| IR-2 | Alta | Parcialmente mitigado | `db/migrate.py` e o Compose usam `QS_READER_PASSWORD_S1..S3`; `Settings` exige `{role}`, `{password}`, uma password por role, mínimo de 24 caracteres e valores distintos. A API ainda recebe os três segredos, pelo que o comprometimento desse processo expõe todos os vendedores. Para isolamento forte, executar serviços por vendedor com armazenamento de segredos independente. |
| IR-3 | Média | Implementado no código; runtime pendente | As migrações 006–007 substituem `app.seller_id` por uma associação do login `session_user`, incluindo o acesso através das vistas. Falta confirmar roles, membership, grants, políticas e comportamento fail-closed num PostgreSQL real. |
| IR-4 | Média | Aberto | A revisão anterior regista divergência SQLGlot/PostgreSQL (A3) e ausência de rate limiting (A4). Os limites por pedido não limitam a frequência de chamadas; falta também evidência de cobertura das diferenças entre parser e servidor. |
| IR-5 | Baixa | Aberto | `QS_DEMO_AUTH=true` permite emitir tokens para personas sem palavra-passe; a opção está desligada por omissão, mas o arranque não distingue produção. Recusar essa configuração fora de desenvolvimento ou restringi-la a uma configuração local explícita. |
| IR-6 | Baixa | Por verificar | A7 (alteração de `statement_timeout` por SQL de topo) e A8 (`pg_stat_activity`) da auto-revisão não foram revalidados nesta revisão. O `DeadlineGuard` usa agora o role do próprio vendedor; falta confirmar o cancelamento no PostgreSQL. |
| IR-7 | Média | Mitigado no código; runtime pendente | `QS_SELLER_IDS` só aceita IDs 1–3, iguais aos roles, segredos e mapeamento criados pela migração 006. Falta confirmação integrada em PostgreSQL. |

## Parecer

A revisão independente foi feita e os riscos identificados estão documentados, satisfazendo a parte de revisão/documentação da tarefa 8.4. **Não é uma aprovação para produção.** O código remove a credencial superuser da API e exige segredos distintos, mas as mudanças da migração 006 ainda não foram confirmadas em runtime; além disso, o processo da API continua a agregar os três segredos. A revisão não substitui a auto-revisão existente em `docs/security-review.md`; complementa-a com a inspeção independente do estado atual.
