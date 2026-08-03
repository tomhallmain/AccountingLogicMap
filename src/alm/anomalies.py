from __future__ import annotations

from .models import ANOMALY_DEFAULT_TOP_K, AnomalyRow, EdgeKey, LogicMap

CLEARING_HINTS = (
    "uncategorized",
    "clearing",
    "discrepanc",
    "ask my accountant",
    "undeposited",
)


def _is_clearing_account(logic_map: LogicMap, account_id: str) -> bool:
    acct = logic_map.accounts.get(account_id)
    blob = f"{account_id} {acct.name if acct else ''} {acct.account_type if acct else ''}".lower()
    return any(h in blob for h in CLEARING_HINTS)


def compare_maps(
    baseline: LogicMap,
    open_map: LogicMap,
    *,
    top_k: int = ANOMALY_DEFAULT_TOP_K,
    baseline_top_n: int = 30,
) -> list[AnomalyRow]:
    """Structural deltas between baseline and open windows."""
    base_idx = baseline.edge_rank_index()
    open_idx = open_map.edge_rank_index()
    all_keys = set(baseline.edges) | set(open_map.edges)

    rows: list[AnomalyRow] = []

    baseline_top = {se.key for se in baseline.scored[:baseline_top_n]}

    for key in all_keys:
        b = base_idx.get(key)
        o = open_idx.get(key)
        b_share = b.share_w if b else 0.0
        o_share = o.share_w if o else 0.0
        delta = o_share - b_share
        b_rank = b.rank if b else None
        o_rank = o.rank if o else None

        signals: list[tuple[str, str]] = []

        if o and not b:
            signals.append(("new_edge", "present in open, absent in baseline"))
        if key in baseline_top and (not o or (o and o.share_w < 1e-12)):
            signals.append(("missing_edge", "top baseline edge missing/near-zero in open"))
        if b and o and abs((b.rank or 0) - (o.rank or 0)) >= max(5, len(baseline.scored) // 10):
            signals.append(
                (
                    "rank_shift",
                    f"rank {b.rank} → {o.rank}, Δshare={delta:+.4f}",
                )
            )
        if o and (
            _is_clearing_account(open_map, key.debit_account_id)
            or _is_clearing_account(open_map, key.credit_account_id)
        ):
            if not b or (o.share_w > b_share * 1.5 + 0.01):
                signals.append(("clearing_surge", "clearing/uncategorized involvement grew"))

        for signal, note in signals:
            rows.append(
                AnomalyRow(
                    signal=signal,
                    debit_account_id=key.debit_account_id,
                    credit_account_id=key.credit_account_id,
                    baseline_share_w=b_share,
                    open_share_w=o_share,
                    delta_share_w=delta,
                    baseline_rank=b_rank,
                    open_rank=o_rank,
                    note=note,
                )
            )

    rows.sort(key=lambda r: (-abs(r.delta_share_w), r.signal, r.debit_account_id))
    # Deduplicate same edge+signal while keeping order
    seen: set[tuple[str, str, str]] = set()
    unique: list[AnomalyRow] = []
    for r in rows:
        k = (r.signal, r.debit_account_id, r.credit_account_id)
        if k in seen:
            continue
        seen.add(k)
        unique.append(r)

    return unique[:top_k]


def edge_key(debit: str, credit: str) -> EdgeKey:
    return EdgeKey(debit, credit)
