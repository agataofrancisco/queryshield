# Revisão de segurança independente

**Estado:** revisão estática concluída; achados e limites documentados.  
**Escopo:** código no `HEAD` `b709cd0` e alterações ainda não commitadas visíveis na árvore de trabalho em 2026-11-24.  
**Método:** leitura independente de configuração, executor, autenticação, migração 006, compose e revisão anterior. Não foram executados testes, Docker nem PostgreSQL; portanto, alterações não commitadas e controlos da base de dados não foram confirmados em runtime.

## Achados

| ID | Severidade | Estado | Evidência e impacto |
|---|---|---|---|
| IR-1 | Alta | Mitigado na árvore de trabalho; integração pendente | O código atual da árvore não precisa de credencial administrativa: `SellerExecutors` passa o DSN do role do vendedor ao `QueryExecutor`, que usa esse mesmo role para cancelar apenas as suas sessões; `QS_CANCEL_DSN` foi removido da configuração e do compose. PostgreSQL permite cancelar sessões do próprio role. Estas alterações estão misturadas com mudanças anteriores ainda não commitadas e não foram verificadas em runtime; o achado só pode ser encerrado depois de integrar e confirmar o caminho real. |
| IR-2 | Alta | Parcialmente mitigado | `db/migrate.py` e o Compose usam agora `QS_READER_PASSWORD_S1..S3`, e a configuração exige segredos diferentes (24+ caracteres); assim, uma password isolada já não autentica nos outros roles. O processo da API ainda recebe os três segredos, pelo que o comprometimento desse processo expõe todos os vendedores. Para isolamento forte, executar serviços por vendedor com armazenamento de segredos independente. A alteração ainda não foi confirmada contra PostgreSQL em runtime. |
| IR-3 | Média | Não confirmado | A migração 006 altera a identidade RLS para `current_user`, removendo `app.seller_id`; é uma mitigação adequada em desenho para A1/A2 da auto-revisão. Porém a migração está por commit e sem validação PostgreSQL nesta revisão. Não declarar A1/A2 resolvidos antes de aplicar a migração e verificar roles, membership, grants, políticas e comportamento fail-closed num PostgreSQL real. |
| IR-4 | Média | Aberto | A revisão anterior regista divergência SQLGlot/PostgreSQL (A3) e ausência de rate limiting (A4). Os limites por pedido não limitam a frequência de chamadas; falta também evidência de cobertura das diferenças entre parser e servidor. |
| IR-5 | Baixa | Aberto | `QS_DEMO_AUTH=true` permite emitir tokens para personas sem palavra-passe; a opção está desligada por omissão, mas o arranque não distingue produção. Recusar essa configuração fora de desenvolvimento ou restringi-la a uma configuração local explícita. |
| IR-6 | Baixa | Por verificar | A7 (alteração de `statement_timeout` por SQL de topo) e A8 (`pg_stat_activity`) da auto-revisão não foram revalidados nesta revisão. `DeadlineGuard` acrescenta cancelamento externo ao timeout, mas depende da credencial elevada descrita em IR-1. |
| IR-7 | Média | Aberto | `QS_SELLER_IDS` aceita IDs configuráveis, mas a migração 006 cria somente vendedores 1–3 e `db/migrate.py` só define passwords para esses três. IDs adicionais podem produzir ligações sem role/mapeamento correspondente, causando falha de serviço; garantir que migração, segredos e configuração partilham o mesmo conjunto de vendedores. |

## Parecer

A revisão independente foi feita e os riscos identificados estão documentados, satisfazendo a parte de revisão/documentação da tarefa 8.4. **Não é uma aprovação para produção.** O achado alto da credencial superuser no processo da API continua por corrigir; IR-2 foi parcialmente mitigado, mas a API ainda agrega os três segredos. A mudança de RLS da migração 006 e a rotação de credenciais continuam sem confirmação em runtime. A revisão não substitui a auto-revisão existente em `docs/security-review.md`; complementa-a com a inspeção independente do estado atual.
