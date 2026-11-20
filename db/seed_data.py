"""Geração determinística do seed sintético do marketplace Kianda Market.

Função pura: a mesma seed produz exactamente os mesmos dados (ver fingerprint).
Não usa relógio, rede nem hash() do Python (que varia entre processos).
Todos os dados são fictícios; emails usam o domínio reservado .invalid.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

DEFAULT_SEED = 20261120
START = date(2025, 1, 1)
END = date(2026, 6, 30)  # inclusivo
CUSTOMERS_PER_SELLER = 150
ORDERS_PER_SELLER = 700
PRODUCTS_PER_SELLER = 12
COMMISSION_RATE = Decimal("0.10")
CATEGORY_NAMES = ["Eletrónica", "Moda", "Casa", "Beleza", "Desporto"]
SELLER_NAMES = ["Ngola Tech", "Casa Benguela", "Mercado Huíla"]
STATUS_WEIGHTS = [
    ("delivered", 45),
    ("shipped", 15),
    ("paid", 15),
    ("pending", 5),
    ("cancelled", 20),
]
RETURN_REASONS = ["tamanho errado", "danificado", "não corresponde à descrição", "desistência"]
CITIES = ["Luanda", "Benguela", "Huambo", "Lubango", "Cabinda"]


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass
class SeedData:
    sellers: list[tuple] = field(default_factory=list)
    categories: list[tuple] = field(default_factory=list)
    customers: list[tuple] = field(default_factory=list)
    products: list[tuple] = field(default_factory=list)
    orders: list[tuple] = field(default_factory=list)
    order_items: list[tuple] = field(default_factory=list)
    returns: list[tuple] = field(default_factory=list)
    payments: list[tuple] = field(default_factory=list)
    payouts: list[tuple] = field(default_factory=list)
    internal_fraud_flags: list[tuple] = field(default_factory=list)

    def counts(self) -> dict[str, int]:
        return {
            "sellers": len(self.sellers),
            "categories": len(self.categories),
            "customers": len(self.customers),
            "products": len(self.products),
            "orders": len(self.orders),
            "order_items": len(self.order_items),
            "returns": len(self.returns),
            "payments": len(self.payments),
            "payouts": len(self.payouts),
            "internal_fraud_flags": len(self.internal_fraud_flags),
        }

    def fingerprint(self) -> str:
        digest = hashlib.sha256()
        for name in self.counts():
            for row in getattr(self, name):
                digest.update(repr((name, row)).encode("utf-8"))
        return digest.hexdigest()


def _random_date(rng: random.Random) -> date:
    return START + timedelta(days=rng.randrange((END - START).days + 1))


def generate(seed: int = DEFAULT_SEED) -> SeedData:
    rng = random.Random(seed)
    data = SeedData()
    seller_ids = [i + 1 for i in range(len(SELLER_NAMES))]
    for sid, name in zip(seller_ids, SELLER_NAMES, strict=True):
        data.sellers.append((sid, name, "AOA", START))

    category_id = 0
    product_id = 0
    customer_id = 0
    order_id = 0
    item_id = 0
    return_id = 0
    payment_id = 0
    flag_id = 0
    category_by_seller: dict[int, list[int]] = {}
    product_by_seller: dict[int, list[tuple[int, Decimal]]] = {}
    customers_by_seller: dict[int, list[int]] = {}

    for sid in seller_ids:
        category_by_seller[sid] = []
        for cname in CATEGORY_NAMES:
            category_id += 1
            data.categories.append((category_id, sid, cname))
            category_by_seller[sid].append(category_id)

        product_by_seller[sid] = []
        for p in range(PRODUCTS_PER_SELLER):
            product_id += 1
            price = money(Decimal(rng.randrange(20, 2500)) * Decimal("100"))
            cat = category_by_seller[sid][p % len(CATEGORY_NAMES)]
            data.products.append((product_id, sid, cat, f"Produto {sid}-{p + 1:02d}", price, True))
            product_by_seller[sid].append((product_id, price))

        customers_by_seller[sid] = []
        for _ in range(CUSTOMERS_PER_SELLER):
            customer_id += 1
            email = f"cliente{customer_id}@exemplo.invalid"
            phone = f"+244 9{rng.randrange(10**8):08d}"
            city = CITIES[rng.randrange(len(CITIES))]
            data.customers.append(
                (customer_id, sid, f"Cliente {customer_id}", email, phone, city, _random_date(rng))
            )
            customers_by_seller[sid].append(customer_id)

        statuses = [s for s, _ in STATUS_WEIGHTS]
        weights = [w for _, w in STATUS_WEIGHTS]
        for _ in range(ORDERS_PER_SELLER):
            order_id += 1
            status = rng.choices(statuses, weights=weights, k=1)[0]
            currency = "USD" if rng.random() < 0.05 else "AOA"
            ordered_on = _random_date(rng)
            customer = customers_by_seller[sid][rng.randrange(CUSTOMERS_PER_SELLER)]
            items: list[tuple[int, int, int, Decimal]] = []
            total = Decimal("0")
            for _ in range(rng.randrange(1, 5)):
                prod_id, price = product_by_seller[sid][rng.randrange(PRODUCTS_PER_SELLER)]
                qty = rng.randrange(1, 4)
                unit = price
                if rng.random() < 0.1:  # desconto pontual: preço unitário diferente do catálogo
                    unit = money(price * Decimal("0.9"))
                line = money(unit * qty)
                item_id += 1
                items.append((item_id, prod_id, qty, unit))
                total += line
                data.order_items.append((item_id, sid, order_id, prod_id, qty, unit, line))
            data.orders.append(
                (order_id, sid, customer, status, currency, ordered_on, money(total))
            )

            if status in ("paid", "shipped", "delivered"):
                data.payments.append(
                    (
                        payment_id := payment_id + 1,
                        sid,
                        order_id,
                        money(total),
                        rng.choice(["card", "transfer", "cash_on_delivery"]),
                        ordered_on,
                        "captured",
                    )
                )
                if status == "delivered":
                    for it_id, _, qty, unit in items:
                        if rng.random() < 0.12:
                            return_id += 1
                            ret_qty = rng.randrange(1, qty + 1)  # devolução parcial possível
                            data.returns.append(
                                (
                                    return_id,
                                    sid,
                                    it_id,
                                    ret_qty,
                                    money(unit * ret_qty),
                                    ordered_on + timedelta(days=rng.randrange(3, 31)),
                                    RETURN_REASONS[rng.randrange(len(RETURN_REASONS))],
                                )
                            )
            elif status == "cancelled" and rng.random() < 0.5:
                payment_id += 1
                data.payments.append(
                    (payment_id, sid, order_id, money(total), "card", ordered_on, "failed")
                )

            if rng.random() < 0.02:
                flag_id += 1
                data.internal_fraud_flags.append(
                    (
                        flag_id,
                        sid,
                        order_id,
                        Decimal(rng.randrange(50, 100)) / Decimal("100"),
                        "padrão de compra atípico",
                        ordered_on,
                    )
                )

    data.payouts = _build_payouts(data)
    return data


def _build_payouts(data: SeedData) -> list[tuple]:
    """Uma liquidação por vendedor e mês completo (jan-2025 a mai-2026).

    Base: receita AOA de encomendas válidas, líquida de devoluções.
    """
    valid = {"paid", "shipped", "delivered"}
    order_info = {o[0]: o for o in data.orders}
    refunds_by_item: dict[int, Decimal] = {}
    for ret in data.returns:
        refunds_by_item[ret[2]] = refunds_by_item.get(ret[2], Decimal("0")) + ret[4]
    gross: dict[tuple[int, date], Decimal] = {}
    for item in data.order_items:
        order = order_info[item[2]]
        if order[3] not in valid or order[4] != "AOA":
            continue
        key = (order[1], order[5].replace(day=1))
        net_line = item[6] - refunds_by_item.get(item[0], Decimal("0"))
        gross[key] = gross.get(key, Decimal("0")) + net_line
    payouts: list[tuple] = []
    pid = 0
    for sid in sorted({s[0] for s in data.sellers}):
        for year, month in [(2025 + (m // 12), m % 12 + 1) for m in range(17)]:
            period = date(year, month, 1)
            amount = money(gross.get((sid, period), Decimal("0")))
            commission = money(amount * COMMISSION_RATE)
            pid += 1
            payouts.append(
                (
                    pid,
                    sid,
                    period,
                    amount,
                    commission,
                    amount - commission,
                    period + timedelta(days=10),
                )
            )
    return payouts
