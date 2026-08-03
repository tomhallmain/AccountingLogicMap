from __future__ import annotations

from .models import EdgeKey, Transaction


def rewrite_transaction(txn: Transaction) -> list[tuple[EdgeKey, float]]:
    """Exact-cover averaging: every DR×CR pair gets proportional weight.

    w(dr_j, cr_k) = w(dr_j) * w(cr_k) / W
    Sum of emitted weights equals W.
    """
    debits = txn.debit_lines()
    credits = txn.credit_lines()
    if not debits or not credits:
        raise ValueError(f"transaction {txn.txn_id} missing debit or credit lines")

    total = sum(ln.amount for ln in debits)
    if total <= 0:
        raise ValueError(f"transaction {txn.txn_id} has non-positive total weight")

    edges: list[tuple[EdgeKey, float]] = []
    for dr in debits:
        for cr in credits:
            weight = (dr.amount * cr.amount) / total
            key = EdgeKey(dr.account_id, cr.account_id)
            edges.append((key, weight))
    return edges


def rewrite_transactions(txns: list[Transaction]) -> list[tuple[str, EdgeKey, float]]:
    """Rewrite all transactions; returns (txn_id, key, weight) triples."""
    out: list[tuple[str, EdgeKey, float]] = []
    for txn in txns:
        for key, weight in rewrite_transaction(txn):
            out.append((txn.txn_id, key, weight))
    return out
