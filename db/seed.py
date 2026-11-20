"""Carrega o seed determinístico na base de dados (ligação administrativa).

Uso:  python -m db.seed [--seed 20261120]
Apaga e recria o conteúdo das tabelas de negócio (TRUNCATE). Só para bases de desenvolvimento/teste.
"""

from __future__ import annotations

import argparse
import os
import sys

import psycopg

from db.seed_data import DEFAULT_SEED, SeedData, generate

TABLE_ORDER = [
    "sellers",
    "categories",
    "customers",
    "products",
    "orders",
    "order_items",
    "returns",
    "payments",
    "payouts",
    "internal_fraud_flags",
]

INSERTS = {
    "sellers": (
        "INSERT INTO qs_private.sellers (id, name, currency, created_on) VALUES (%s,%s,%s,%s)"
    ),
    "categories": "INSERT INTO qs_private.categories (id, seller_id, name) VALUES (%s,%s,%s)",
    "customers": (
        "INSERT INTO qs_private.customers"
        " (id, seller_id, full_name, email, phone, city, created_on)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "products": (
        "INSERT INTO qs_private.products (id, seller_id, category_id, name, unit_price, active)"
        " VALUES (%s,%s,%s,%s,%s,%s)"
    ),
    "orders": (
        "INSERT INTO qs_private.orders (id, seller_id, customer_id, status, currency, ordered_on,"
        " total_amount) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "order_items": (
        "INSERT INTO qs_private.order_items (id, seller_id, order_id, product_id, quantity,"
        " unit_price, line_total) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "returns": (
        "INSERT INTO qs_private.returns (id, seller_id, order_item_id, quantity, refund_amount,"
        " returned_on, reason) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "payments": (
        "INSERT INTO qs_private.payments (id, seller_id, order_id, amount, method, paid_on, status)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "payouts": (
        "INSERT INTO qs_private.payouts (id, seller_id, period_month, gross_amount,"
        " commission_amount, net_amount, paid_on) VALUES (%s,%s,%s,%s,%s,%s,%s)"
    ),
    "internal_fraud_flags": (
        "INSERT INTO qs_private.internal_fraud_flags (id, seller_id, order_id, score, reason,"
        " flagged_on) VALUES (%s,%s,%s,%s,%s,%s)"
    ),
}


def load_seed(admin_dsn: str, seed: int = DEFAULT_SEED) -> dict[str, int]:
    data: SeedData = generate(seed)
    with psycopg.connect(admin_dsn) as conn, conn.transaction():
        conn.execute(
            "TRUNCATE "
            + ", ".join(f"qs_private.{t}" for t in reversed(TABLE_ORDER))
            + " RESTART IDENTITY"
        )
        with conn.cursor() as cur:
            for table in TABLE_ORDER:
                cur.executemany(INSERTS[table], getattr(data, table))
    return data.counts()


def main() -> int:
    parser = argparse.ArgumentParser(description="Carrega o seed sintético do QueryShield.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    args = parser.parse_args()
    admin_dsn = os.environ.get("QS_ADMIN_DSN", "")
    if not admin_dsn:
        print("QS_ADMIN_DSN não definido.", file=sys.stderr)
        return 2
    try:
        counts = load_seed(admin_dsn, args.seed)
    except psycopg.Error as exc:
        print(f"Falha no seed: {type(exc).__name__}", file=sys.stderr)
        return 1
    print(f"Seed {args.seed} carregado: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
