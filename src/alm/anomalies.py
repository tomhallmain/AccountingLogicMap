from __future__ import annotations

from .models import (
    ANOMALY_DEFAULT_TOP_K,
    BASELINE_TOP_FRAC,
    MISSING_EDGE_MIN_SHARE,
    NEAR_ZERO_SHARE,
    RANK_SHIFT_MIN_DELTA_SHARE,
    RANK_SHIFT_MIN_PCTILE,
    AnomalyRow,
    EdgeKey,
    LogicMap,
)

CLEARING_HINTS = (
    "uncategorized",
    "clearing",
    "discrepanc",
    "ask my accountant",
)


def _is_clearing_account(logic_map: LogicMap, account_id: str) -> bool:
    acct = logic_map.accounts.get(account_id)
    blob = f"{account_id} {acct.name if acct else ''} {acct.account_type if acct else ''}".lower()
    return any(h in blob for h in CLEARING_HINTS)


def _pctile(rank: int | None, n: int) -> float | None:
    """Rank as a position in [0, 1], so maps of different size are comparable.

    Raw ranks are not: an edge can move from 14th of 20 to 9th of 13 without
    anything about it changing.
    """
    if rank is None or n <= 1:
        return None
    return (rank - 1) / (n - 1)


def compare_maps(
    baseline: LogicMap,
    open_map: LogicMap,
    *,
    top_k: int = ANOMALY_DEFAULT_TOP_K,
    baseline_top_frac: float = BASELINE_TOP_FRAC,
) -> list[AnomalyRow]:
    """Structural deltas between baseline and open windows.

    One row per edge: an edge that trips several qualifiers reports them all
    rather than consuming several slots in the top-K.
    """
    base_idx = baseline.edge_rank_index()
    open_idx = open_map.edge_rank_index()
    all_keys = set(baseline.edges) | set(open_map.edges)

    n_base = len(baseline.scored)
    n_open = len(open_map.scored)

    # "Top baseline edge" as a fraction of the map, and material enough to care
    # about. A fixed count silently means "every edge" on a small map.
    top_cutoff = max(1, round(n_base * baseline_top_frac))
    baseline_top = {
        se.key
        for se in baseline.scored[:top_cutoff]
        if se.share_w >= MISSING_EDGE_MIN_SHARE
    }

    rows: list[AnomalyRow] = []

    for key in all_keys:
        b = base_idx.get(key)
        o = open_idx.get(key)
        b_share = b.share_w if b else 0.0
        o_share = o.share_w if o else 0.0
        delta = o_share - b_share

        signals: list[str] = []
        notes: list[str] = []

        if o and not b:
            signals.append("new_edge")
            notes.append("present in open, absent in baseline")

        if key in baseline_top and o_share < NEAR_ZERO_SHARE:
            signals.append("missing_edge")
            notes.append(
                f"top baseline edge (share {b_share:.3f}) missing/near-zero in open"
            )

        if b and o:
            b_pct = _pctile(b.rank, n_base)
            o_pct = _pctile(o.rank, n_open)
            if (
                b_pct is not None
                and o_pct is not None
                and abs(o_pct - b_pct) >= RANK_SHIFT_MIN_PCTILE
                and abs(delta) >= RANK_SHIFT_MIN_DELTA_SHARE
            ):
                signals.append("rank_shift")
                notes.append(
                    f"rank {b.rank}/{n_base} → {o.rank}/{n_open} "
                    f"({b_pct:.0%} → {o_pct:.0%}), Δshare={delta:+.4f}"
                )

        if o and (
            _is_clearing_account(open_map, key.debit_account_id)
            or _is_clearing_account(open_map, key.credit_account_id)
        ):
            if not b or o_share > b_share * 1.5 + MISSING_EDGE_MIN_SHARE:
                signals.append("clearing_surge")
                notes.append("clearing/uncategorized involvement grew")

        if not signals:
            continue

        rows.append(
            AnomalyRow(
                signals=signals,
                debit_account_id=key.debit_account_id,
                credit_account_id=key.credit_account_id,
                baseline_share_w=b_share,
                open_share_w=o_share,
                delta_share_w=delta,
                baseline_rank=b.rank if b else None,
                open_rank=o.rank if o else None,
                note="; ".join(notes),
            )
        )

    rows.sort(key=lambda r: (-abs(r.delta_share_w), r.debit_account_id, r.credit_account_id))
    return rows[:top_k]


def edge_key(debit: str, credit: str) -> EdgeKey:
    return EdgeKey(debit, credit)
