-- 002: schema privado com as 10 tabelas de negócio (fictícias, marketplace Kianda Market).
-- Todas as tabelas de negócio têm seller_id (tenant). Objectos criados como qs_app.

CREATE SCHEMA IF NOT EXISTS qs_private AUTHORIZATION qs_app;
CREATE SCHEMA IF NOT EXISTS qs_api AUTHORIZATION qs_app;

SET ROLE qs_app;

CREATE TABLE qs_private.sellers (
    id          integer PRIMARY KEY,
    name        text NOT NULL,
    currency    text NOT NULL DEFAULT 'AOA' CHECK (currency = 'AOA'),
    created_on  date NOT NULL
);

CREATE TABLE qs_private.categories (
    id          integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES qs_private.sellers (id),
    name        text NOT NULL,
    UNIQUE (seller_id, name)
);

CREATE TABLE qs_private.customers (
    id          integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES qs_private.sellers (id),
    full_name   text NOT NULL,
    email       text NOT NULL,
    phone       text,
    city        text NOT NULL,
    created_on  date NOT NULL,
    UNIQUE (seller_id, email)
);

CREATE TABLE qs_private.products (
    id           integer PRIMARY KEY,
    seller_id    integer NOT NULL REFERENCES qs_private.sellers (id),
    category_id  integer NOT NULL REFERENCES qs_private.categories (id),
    name         text NOT NULL,
    unit_price   numeric(12, 2) NOT NULL CHECK (unit_price > 0),
    active       boolean NOT NULL DEFAULT true
);

CREATE TABLE qs_private.orders (
    id            integer PRIMARY KEY,
    seller_id     integer NOT NULL REFERENCES qs_private.sellers (id),
    customer_id   integer NOT NULL REFERENCES qs_private.customers (id),
    status        text NOT NULL CHECK (status IN ('pending', 'paid', 'shipped', 'delivered', 'cancelled')),
    currency      text NOT NULL CHECK (currency IN ('AOA', 'USD')),
    ordered_on    date NOT NULL,
    total_amount  numeric(12, 2) NOT NULL CHECK (total_amount >= 0)
);

CREATE TABLE qs_private.order_items (
    id          integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES qs_private.sellers (id),
    order_id    integer NOT NULL REFERENCES qs_private.orders (id),
    product_id  integer NOT NULL REFERENCES qs_private.products (id),
    quantity    integer NOT NULL CHECK (quantity > 0),
    unit_price  numeric(12, 2) NOT NULL CHECK (unit_price > 0),
    line_total  numeric(12, 2) NOT NULL CHECK (line_total = quantity * unit_price)
);

CREATE TABLE qs_private.returns (
    id             integer PRIMARY KEY,
    seller_id      integer NOT NULL REFERENCES qs_private.sellers (id),
    order_item_id  integer NOT NULL REFERENCES qs_private.order_items (id),
    quantity       integer NOT NULL CHECK (quantity > 0),
    refund_amount  numeric(12, 2) NOT NULL CHECK (refund_amount >= 0),
    returned_on    date NOT NULL,
    reason         text NOT NULL
);

CREATE TABLE qs_private.payments (
    id          integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES qs_private.sellers (id),
    order_id    integer NOT NULL REFERENCES qs_private.orders (id),
    amount      numeric(12, 2) NOT NULL CHECK (amount >= 0),
    method      text NOT NULL CHECK (method IN ('card', 'transfer', 'cash_on_delivery')),
    paid_on     date NOT NULL,
    status      text NOT NULL CHECK (status IN ('captured', 'failed', 'refunded'))
);

CREATE TABLE qs_private.payouts (
    id                 integer PRIMARY KEY,
    seller_id          integer NOT NULL REFERENCES qs_private.sellers (id),
    period_month       date NOT NULL,
    gross_amount       numeric(12, 2) NOT NULL,
    commission_amount  numeric(12, 2) NOT NULL,
    net_amount         numeric(12, 2) NOT NULL CHECK (net_amount = gross_amount - commission_amount),
    paid_on            date NOT NULL,
    UNIQUE (seller_id, period_month)
);

-- Tabela secreta: nunca exposta por nenhuma vista e sem grants para qs_reader.
CREATE TABLE qs_private.internal_fraud_flags (
    id          integer PRIMARY KEY,
    seller_id   integer NOT NULL REFERENCES qs_private.sellers (id),
    order_id    integer NOT NULL REFERENCES qs_private.orders (id),
    score       numeric(4, 2) NOT NULL CHECK (score BETWEEN 0 AND 1),
    reason      text NOT NULL,
    flagged_on  date NOT NULL
);

CREATE INDEX orders_seller_date_idx ON qs_private.orders (seller_id, ordered_on);
CREATE INDEX order_items_order_idx ON qs_private.order_items (order_id);
CREATE INDEX returns_item_idx ON qs_private.returns (order_item_id);
CREATE INDEX payments_order_idx ON qs_private.payments (order_id);

RESET ROLE;
