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


def has_ambiguous_pairing(txn: Transaction) -> bool:
    """True when the rewrite has to guess which credit funded which debit.

    With one line on either side every emitted pair is forced by the journal
    itself: a (n,1) journal apportions w(dr_j, cr_1) = dr_j, which is exact. Only
    when both sides carry several lines can DR×CR produce a pair that never
    corresponded to a real movement — the paper's "false edge" case.
    """
    return len(txn.debit_lines()) > 1 and len(txn.credit_lines()) > 1


def rewrite_transactions(
    txns: list[Transaction],
    *,
    granularity: str = "month",
    split: bool = False,
) -> list[tuple[str, EdgeKey, float, bool, str]]:
    """Rewrite all transactions.

    Returns (txn_id, key, weight, ambiguous, period) tuples. The period travels
    with each pair so aggregation can retain per-period edge mass, which is what
    seasonal conditioning reads.

    With `split`, each journal is first decomposed into the balanced subsets it
    is forced into (concept §3.3), and averaging runs within each subset. Every
    piece keeps the parent `txn_id`, so depth still counts source transactions
    rather than pieces; ambiguity is assessed per subset, which is the point —
    a packed journal that decomposes into two-line events has no ambiguity left.
    """
    from .periods import period_key
    from .split import split_transaction

    out: list[tuple[str, EdgeKey, float, bool, str]] = []
    for txn in txns:
        period = period_key(txn.date, granularity)
        parts = split_transaction(txn) if split else [txn]
        for part in parts:
            ambiguous = has_ambiguous_pairing(part)
            for key, weight in rewrite_transaction(part):
                out.append((txn.txn_id, key, weight, ambiguous, period))
    return out
