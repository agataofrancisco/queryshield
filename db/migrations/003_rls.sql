-- 003: Row-Level Security por vendedor (tenant).
-- O servidor define app.seller_id com set_config(..., is_local => true) dentro da transacção.
-- O SQL gerado nunca define nem altera o tenant.
--
-- FORCE ROW LEVEL SECURITY: sem isto, o dono das tabelas (qs_app) ignoraria a política.
-- Como as vistas de qs_api são propriedade de qs_app, é isto que mantém a política activa
-- quando qs_reader lê através delas.
-- Superusers (admin de migrações/seed) continuam a contornar RLS; por isso o executor
-- nunca usa uma ligação de superuser.

SET ROLE qs_app;

-- Devolve NULL se o tenant não estiver definido (fail-closed: nenhuma linha é visível).
CREATE FUNCTION qs_private.current_seller_id() RETURNS integer
LANGUAGE sql STABLE AS $$
    SELECT NULLIF(current_setting('app.seller_id', true), '')::integer
$$;

ALTER TABLE qs_private.sellers ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.sellers FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.sellers
    USING (id = qs_private.current_seller_id())
    WITH CHECK (id = qs_private.current_seller_id());

ALTER TABLE qs_private.categories ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.categories FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.categories
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.customers ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.customers FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.customers
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.products ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.products FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.products
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.orders FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.orders
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.order_items ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.order_items FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.order_items
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.returns ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.returns FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.returns
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.payments ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.payments FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.payments
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.payouts ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.payouts FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.payouts
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

ALTER TABLE qs_private.internal_fraud_flags ENABLE ROW LEVEL SECURITY;
ALTER TABLE qs_private.internal_fraud_flags FORCE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON qs_private.internal_fraud_flags
    USING (seller_id = qs_private.current_seller_id())
    WITH CHECK (seller_id = qs_private.current_seller_id());

RESET ROLE;
