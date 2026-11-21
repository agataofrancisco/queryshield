-- 005: âmbito de pedido (tenant + timeout) definido só pelo executor, uma vez por transacção.
--
-- Porquê: sem esta migração, qs_reader podia chamar set_config('app.seller_id', '2', true)
-- directamente no SQL gerado e mudar o tenant dentro da transacção (RLS passaria a ver o outro).
-- Agora:
--  * EXECUTE em set_config é retirado do PUBLIC e concedido só ao dono (qs_app).
--  * qs_api.begin_request(seller, timeout_ms) é a única forma de definir o tenant. É SECURITY
--    DEFINER (corre como qs_app), só pode ser chamada uma vez por transacção (flag local) e o
--    executor chama-a antes de qualquer SQL do utilizador.

SET ROLE qs_app;

CREATE FUNCTION qs_api.begin_request(p_seller_id integer, p_timeout_ms integer)
RETURNS void
LANGUAGE plpgsql
VOLATILE
SECURITY DEFINER
SET search_path = pg_catalog, qs_private
AS $$
BEGIN
    IF current_setting('qs.request_started', true) = 'on' THEN
        RAISE EXCEPTION 'request scope already started'
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    IF p_seller_id IS NULL OR p_seller_id <= 0 THEN
        RAISE EXCEPTION 'invalid request scope' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    IF p_timeout_ms IS NULL OR p_timeout_ms < 100 OR p_timeout_ms > 10000 THEN
        RAISE EXCEPTION 'invalid request scope' USING ERRCODE = 'invalid_parameter_value';
    END IF;
    PERFORM set_config('app.seller_id', p_seller_id::text, true);
    PERFORM set_config('statement_timeout', p_timeout_ms::text || 'ms', true);
    PERFORM set_config('qs.request_started', 'on', true);
END
$$;

RESET ROLE;

-- set_config deixa de estar disponível ao reader; o dono mantém-no para a função acima.
REVOKE EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION pg_catalog.set_config(text, text, boolean) TO qs_app;

REVOKE EXECUTE ON FUNCTION qs_api.begin_request(integer, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION qs_api.begin_request(integer, integer) TO qs_reader;
