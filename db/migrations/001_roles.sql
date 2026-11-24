-- 001: roles da aplicação.
-- Executado como superuser local (QS_ADMIN_DSN) por db/migrate.py.
--
-- qs_app    : dono de todos os objectos (NOLOGIN). Nunca usado pela aplicação em runtime.
-- qs_reader : role histórico do primeiro desenho do executor. A migração 006 desactiva
--             o login e cria um role por vendedor. Passwords nunca ficam no SQL;
--             db/migrate.py define QS_READER_PASSWORD_S1..S3 no runtime.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qs_app') THEN
        CREATE ROLE qs_app NOLOGIN NOSUPERUSER NOBYPASSRLS;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'qs_reader') THEN
        CREATE ROLE qs_reader LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
    END IF;
END
$$;

ALTER ROLE qs_reader NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS NOINHERIT;
-- Defesa em profundidade: mesmo que uma transacção não declare READ ONLY, o role começa em leitura.
ALTER ROLE qs_reader SET default_transaction_read_only = on;
-- O search_path só expõe as vistas públicas da aplicação, nunca o schema privado.
ALTER ROLE qs_reader SET search_path = qs_api;
-- Limite de backstop; o executor define um valor por transacção.
ALTER ROLE qs_reader SET statement_timeout = '3s';
ALTER ROLE qs_reader SET idle_in_transaction_session_timeout = '10s';
