-- 006: isolamento por vendedor imposto pela base de dados, com um role de login por vendedor.
--
-- Porquê: o tenant era uma definição de sessão (app.seller_id). Qualquer SQL na sessão a podia
-- mudar com SET (achado A1 de docs/security-review.md). Agora a identidade é o próprio role:
--  * qs_reader_s1..s3: LOGIN, NOINHERIT, sem membership em nenhum outro role, read-only por omissão.
--    A RLS compara seller_id com o vendedor associado a current_user. SET ROLE, SET SESSION
--    AUTHORIZATION e RESET ROLE não mudam current_user sem membership, e os roles não têm nenhuma.
--  * qs_private.seller_roles(role_name, seller_id): mapeamento legível pelos roles de vendedor.
--  * qs_api.begin_request(timeout_ms): só define o statement_timeout local à transacção. Já não
--    recebe nem define o tenant.
--  * qs_reader deixa de ser usável (NOLOGIN, sem privilégios); fica como modelo histórico.

-- 1. Roles de login (criação como superuser; a password é definida por db/migrate.py).
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['qs_reader_s1', 'qs_reader_s2', 'qs_reader_s3'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format(
                'CREATE ROLE %I LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT', r);
        END IF;
        EXECUTE format(
            'ALTER ROLE %I NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT', r);
        EXECUTE format('ALTER ROLE %I SET default_transaction_read_only = on', r);
        EXECUTE format('ALTER ROLE %I SET search_path = qs_api', r);
        EXECUTE format('ALTER ROLE %I SET statement_timeout = ''3s''', r);
        EXECUTE format('ALTER ROLE %I SET idle_in_transaction_session_timeout = ''10s''', r);
    END LOOP;
END
$$;

-- 2. qs_reader deixa de ter privilégios e de poder entrar.
REVOKE ALL ON ALL TABLES IN SCHEMA qs_api FROM qs_reader;
REVOKE USAGE ON SCHEMA qs_api FROM qs_reader;
ALTER ROLE qs_reader NOLOGIN;

-- 3. Mapeamento role -> vendedor.
SET ROLE qs_app;

CREATE TABLE qs_private.seller_roles (
    role_name  text PRIMARY KEY CHECK (role_name ~ '^qs_reader_s[0-9]+$'),
    seller_id  integer NOT NULL UNIQUE CHECK (seller_id > 0)
);

INSERT INTO qs_private.seller_roles (role_name, seller_id) VALUES
    ('qs_reader_s1', 1),
    ('qs_reader_s2', 2),
    ('qs_reader_s3', 3);

-- 4. Políticas RLS: o vendedor é o do role corrente (current_user), lido do mapeamento.
DROP POLICY tenant_isolation ON qs_private.sellers;
CREATE POLICY tenant_isolation ON qs_private.sellers
    USING (id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.categories;
CREATE POLICY tenant_isolation ON qs_private.categories
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.customers;
CREATE POLICY tenant_isolation ON qs_private.customers
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.products;
CREATE POLICY tenant_isolation ON qs_private.products
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.orders;
CREATE POLICY tenant_isolation ON qs_private.orders
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.order_items;
CREATE POLICY tenant_isolation ON qs_private.order_items
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.returns;
CREATE POLICY tenant_isolation ON qs_private.returns
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.payments;
CREATE POLICY tenant_isolation ON qs_private.payments
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.payouts;
CREATE POLICY tenant_isolation ON qs_private.payouts
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

DROP POLICY tenant_isolation ON qs_private.internal_fraud_flags;
CREATE POLICY tenant_isolation ON qs_private.internal_fraud_flags
    USING (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user))
    WITH CHECK (seller_id = (SELECT m.seller_id FROM qs_private.seller_roles AS m WHERE m.role_name = current_user));

-- 5. Remove o caminho antigo baseado em definições de sessão.
DROP FUNCTION qs_private.current_seller_id();
DROP FUNCTION qs_api.begin_request(integer, integer);

-- 6. begin_request só define o timeout (local à transacção). Sem tenant.
CREATE FUNCTION qs_api.begin_request(p_timeout_ms integer)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog
AS $$
BEGIN
    IF p_timeout_ms IS NULL OR p_timeout_ms < 100 OR p_timeout_ms > 10000 THEN
        RAISE EXCEPTION 'invalid request scope' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    PERFORM set_config('statement_timeout', p_timeout_ms::text || 'ms', true);
END
$$;

RESET ROLE;

-- 7. Privilégios: cada role de vendedor só lê as vistas públicas e o mapeamento.
GRANT USAGE ON SCHEMA qs_api, qs_private TO qs_reader_s1, qs_reader_s2, qs_reader_s3;
GRANT SELECT ON qs_private.seller_roles TO qs_reader_s1, qs_reader_s2, qs_reader_s3;
GRANT SELECT ON qs_api.sellers, qs_api.categories, qs_api.customers, qs_api.products,
    qs_api.orders, qs_api.order_items, qs_api.returns, qs_api.payments, qs_api.payouts
    TO qs_reader_s1, qs_reader_s2, qs_reader_s3;

REVOKE EXECUTE ON FUNCTION qs_api.begin_request(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qs_api.begin_request(integer)
    TO qs_reader_s1, qs_reader_s2, qs_reader_s3;

-- Nota: os roles de vendedor não são membros de nenhum role (verificado em tests/postgres).
