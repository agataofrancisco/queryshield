# Revisão de segurança independente

**Estado:** revisão estática concluída; achados e limites documentados.  
**Escopo:** código no `HEAD` `b709cd0` e alterações ainda não commitadas visíveis na árvore de trabalho em 2026-11-24.  
**Método:** leitura independente de configuração, executor, autenticação, migração 006, compose e revisão anterior. Não foram executados testes, Docker nem PostgreSQL; portanto, alterações não commitadas e controlos da base de dados não foram confirmados em runtime.

## Achados

| ID | Severidade | Estado | Evidência e impacto |
|---|---|---|---|
| IR-1 | Alta | Aberto | `docker-compose.yml` injeta `QS_CANCEL_DSN` com o utilizador `postgres` na API. `DeadlineGuard` usa essa credencial para `pg_cancel_backend`. Uma falha na API ou exposição do ambiente dá ao processo credenciais de superutilizador, contornando RLS e permissões read-only. Usar um role dedicado, sem privilégios de leitura/escrita de dados, com apenas a capacidade de cancelar backends necessária. |
| IR-2 | Alta | Aberto | `db/migrate.py` define a mesma `QS_READER_PASSWORD` para `qs_reader_s1..s3`, e `docker-compose.yml` usa essa password no template de DSN. Quem obtiver a credencial de um vendedor pode autenticar-se como os outros vendedores e ultrapassar o isolamento por role. Usar segredos independentes por vendedor e impedir que a configuração agregada os exponha em conjunto quando cada serviço puder ser isolado. |
| IR-3 | Média | Não confirmado | A migração 006 altera a identidade RLS para `current_user`, removendo `app.seller_id`; é uma mitigação adequada em desenho para A1/A2 da auto-revisão. Porém a migração está por commit e sem validação PostgreSQL nesta revisão. Não declarar A1/A2 resolvidos antes de aplicar a migração e verificar roles, membership, grants, políticas e comportamento fail-closed num PostgreSQL real. |
| IR-4 | Média | Aberto | A revisão anterior regista divergência SQLGlot/PostgreSQL (A3) e ausência de rate limiting (A4). Os limites por pedido não limitam a frequência de chamadas; falta também evidência de cobertura das diferenças entre parser e servidor. |
| IR-5 | Baixa | Aberto | `QS_DEMO_AUTH=true` permite emitir tokens para personas sem palavra-passe; a opção está desligada por omissão, mas o arranque não distingue produção. Recusar essa configuração fora de desenvolvimento ou restringi-la a uma configuração local explícita. |
| IR-6 | Baixa | Por verificar | A7 (alteração de `statement_timeout` por SQL de topo) e A8 (`pg_stat_activity`) da auto-revisão não foram revalidados nesta revisão. `DeadlineGuard` acrescenta cancelamento externo ao timeout, mas depende da credencial elevada descrita em IR-1. |
| IR-7 | Média | Aberto | `QS_SELLER_IDS` aceita IDs configuráveis, mas a migração 006 cria somente vendedores 1–3 e `db/migrate.py` só define passwords para esses três. IDs adicionais podem produzir ligações sem role/mapeamento correspondente, causando falha de serviço; garantir que migração, segredos e configuração partilham o mesmo conjunto de vendedores. |

## Parecer

A revisão independente foi feita e os riscos identificados estão documentados, satisfazendo a parte de revisão/documentação da tarefa 8.4. **Não é uma aprovação para produção.** Os dois achados altos (credencial superuser no processo da API e password partilhada entre vendedores) devem ser corrigidos antes de usar dados reais. A mudança de RLS da migração 006 é promissora, mas continua sem confirmação em runtime. A revisão não substitui a auto-revisão existente em `docs/security-review.md`; complementa-a com a inspeção independente do estado atual.
