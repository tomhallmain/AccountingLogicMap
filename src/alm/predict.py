from __future__ import annotations

from .models import PREDICT_DEFAULT_TOP_K, LogicMap, PredictRow


def predict_counterparts(
    logic_map: LogicMap,
    account_id: str,
    side: str,
    *,
    top_k: int = PREDICT_DEFAULT_TOP_K,
    amount: float | None = None,
    periods: list[str] | None = None,
) -> list[PredictRow]:
    """Rank counterpart accounts given a known node and side.

    Probability is the counterpart's share of the weight on that node-side.

    `periods` restricts the mass to a set of period keys — pass the output of
    `periods.seasonal_periods` to condition on the same month in prior years
    rather than on the whole window. Edges with no activity in those periods drop
    out, so a seasonal query returns the counterparts that season actually saw.
    """
    side = side.lower().strip()
    if side not in {"debit", "credit"}:
        raise ValueError("side must be 'debit' or 'credit'")

    rank_index = logic_map.edge_rank_index()
    stats = (
        logic_map.iter_edges_from_debit(account_id)
        if side == "debit"
        else logic_map.iter_edges_from_credit(account_id)
    )

    rows: list[PredictRow] = []
    for stat in stats:
        counterpart = (
            stat.key.credit_account_id if side == "debit" else stat.key.debit_account_id
        )
        weight = stat.weight_in(periods)
        depth = stat.depth_in(periods)
        if periods is not None and weight <= 0:
            continue  # this counterpart never appeared in the selected season
        se = rank_index.get(stat.key)
        rows.append(
            PredictRow(
                account_id=counterpart,
                account_type=logic_map.account_type(counterpart),
                weight_sum=weight,
                depth=depth,
                probability=0.0,
                norm=se.norm if se else None,
                mean_weight=weight / depth if depth else 0.0,
            )
        )

    total = sum(r.weight_sum for r in rows)
    for r in rows:
        r.probability = (r.weight_sum / total) if total else 0.0

    rows.sort(key=lambda r: (-r.probability, -r.weight_sum, r.account_id))
    return rows[:top_k]
