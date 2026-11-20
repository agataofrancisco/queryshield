-- 004: vistas públicas da aplicação (schema qs_api) e grants para qs_reader.
--
-- Regras:
--  * Os nomes das vistas são os nomes que a semantic layer e o SQL gerado usam.
--  * customers NÃO expõe email nem telefone. Nenhum papel da aplicação tem PII de clientes
--    disponível através do executor (decisão documentada em docs/decisions.md).
--  * internal_fraud_flags não tem vista: é invisível para qs_reader.
--  * security_barrier impede que funções/operadores do SQL gerado vejam linhas antes da
--    política de RLS (princípio de barreira de segurança em vistas).
--  * As vistas são propriedade de qs_app; a política RLS continua activa por causa de FORCE.

SET ROLE qs_app;

CREATE VIEW qs_api.sellers WITH (security_barrier = true) AS
    SELECT id, name, currency, created_on FROM qs_private.sellers;

CREATE VIEW qs_api.categories WITH (security_barrier = true) AS
    SELECT id, seller_id, name FROM qs_private.categories;

CREATE VIEW qs_api.customers WITH (security_barrier = true) AS
    SELECT id, seller_id, full_name, city, created_on FROM qs_private.customers;

CREATE VIEW qs_api.products WITH (security_barrier = true) AS
    SELECT id, seller_id, category_id, name, unit_price, active FROM qs_private.products;

CREATE VIEW qs_api.orders WITH (security_barrier = true) AS
    SELECT id, seller_id, customer_id, status, currency, ordered_on, total_amount
    FROM qs_private.orders;

CREATE VIEW qs_api.order_items WITH (security_barrier = true) AS
    SELECT id, seller_id, order_id, product_id, quantity, unit_price, line_total
    FROM qs_private.order_items;

CREATE VIEW qs_api.returns WITH (security_barrier = true) AS
    SELECT id, seller_id, order_item_id, quantity, refund_amount, returned_on, reason
    FROM qs_private.returns;

CREATE VIEW qs_api.payments WITH (security_barrier = true) AS
    SELECT id, seller_id, order_id, amount, method, paid_on, status FROM qs_private.payments;

CREATE VIEW qs_api.payouts WITH (security_barrier = true) AS
    SELECT id, seller_id, period_month, gross_amount, commission_amount, net_amount, paid_on
    FROM qs_private.payouts;

RESET ROLE;

-- Grants: qs_reader só recebe SELECT nas vistas públicas. Nada em qs_private.
REVOKE ALL ON SCHEMA qs_private FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA qs_private FROM PUBLIC;
REVOKE ALL ON SCHEMA qs_api FROM PUBLIC;

GRANT USAGE ON SCHEMA qs_api TO qs_reader;
GRANT SELECT ON qs_api.sellers, qs_api.categories, qs_api.customers, qs_api.products,
    qs_api.orders, qs_api.order_items, qs_api.returns, qs_api.payments, qs_api.payouts
    TO qs_reader;
