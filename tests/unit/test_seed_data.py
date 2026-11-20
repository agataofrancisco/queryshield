"""Invariantes do seed sintético: determinismo, integridade e casos difíceis."""

from __future__ import annotations

from collections import Counter

from db.seed_data import DEFAULT_SEED, generate


def test_same_seed_produces_identical_data() -> None:
    assert generate(DEFAULT_SEED).fingerprint() == generate(DEFAULT_SEED).fingerprint()


def test_different_seed_produces_different_data() -> None:
    assert generate(DEFAULT_SEED).fingerprint() != generate(DEFAULT_SEED + 1).fingerprint()


def test_expected_table_counts() -> None:
    counts = generate(DEFAULT_SEED).counts()
    assert counts["sellers"] == 3
    assert counts["orders"] == 2100
    assert counts["customers"] == 450
    assert len(counts) == 10  # as 10 tabelas de negócio da D1


def test_line_totals_match_quantity_times_unit_price() -> None:
    data = generate()
    for item_id, _, _, _, qty, unit, line in data.order_items:
        assert line == qty * unit, item_id


def test_payout_net_equals_gross_minus_commission() -> None:
    for pid, _, _, gross, commission, net, _ in generate().payouts:
        assert net == gross - commission, pid


def test_all_rows_belong_to_their_seller_and_references_are_consistent() -> None:
    data = generate()
    customer_seller = {c[0]: c[1] for c in data.customers}
    order_seller = {o[0]: o[1] for o in data.orders}
    item_seller = {i[0]: i[1] for i in data.order_items}
    for order in data.orders:
        assert customer_seller[order[2]] == order[1], "encomenda com cliente de outro vendedor"
    for item in data.order_items:
        assert order_seller[item[2]] == item[1]
    for ret in data.returns:
        assert item_seller[ret[2]] == ret[1]


def test_returns_never_exceed_the_purchased_quantity() -> None:
    data = generate()
    qty = {i[0]: i[4] for i in data.order_items}
    for ret in data.returns:
        assert ret[3] <= qty[ret[2]]


def test_hard_cases_are_present() -> None:
    data = generate()
    statuses = Counter(o[3] for o in data.orders)
    assert statuses["cancelled"] > 0
    assert any(o[4] == "USD" for o in data.orders), "faltam encomendas em moeda não AOA"
    partial = [r for r in data.returns if r[3] < {i[0]: i[4] for i in data.order_items}[r[2]]]
    assert partial, "faltam devoluções parciais"
