from __future__ import annotations

from .models import PREDICT_DEFAULT_TOP_K, LogicMap, PredictRow


def predict_counterparts(
    logic_map: LogicMap,
    account_id: str,
    side: str,
    *,
    top_k: int = PREDICT_DEFAULT_TOP_K,
    amount: float | None = None,
) -> list[PredictRow]:
    """Rank counterpart accounts given a known node and side."""
    side = side.lower().strip()
    if side not in {"debit", "credit"}:
        raise ValueError("side must be 'debit' or 'credit'")

    rank_index = logic_map.edge_rank_index()
    rows: list[PredictRow] = []

    if side == "debit":
        stats = list(logic_map.iter_edges_from_debit(account_id))
        for stat in stats:
            counterpart = stat.key.credit_account_id
            se = rank_index.get(stat.key)
            rows.append(
                PredictRow(
                    account_id=counterpart,
                    account_type=logic_map.account_type(counterpart),
                    weight_sum=stat.weight_sum,
                    depth=stat.depth,
                    probability=0.0,
                    norm=se.norm if se else None,
                    mean_weight=stat.mean_weight,
                )
            )
    else:
        stats = list(logic_map.iter_edges_from_credit(account_id))
        for stat in stats:
            counterpart = stat.key.debit_account_id
            se = rank_index.get(stat.key)
            rows.append(
                PredictRow(
                    account_id=counterpart,
                    account_type=logic_map.account_type(counterpart),
                    weight_sum=stat.weight_sum,
                    depth=stat.depth,
                    probability=0.0,
                    norm=se.norm if se else None,
                    mean_weight=stat.mean_weight,
                )
            )

    total = sum(r.weight_sum for r in rows)
    for r in rows:
        r.probability = (r.weight_sum / total) if total else 0.0

    rows.sort(key=lambda r: (-r.probability, -r.weight_sum, r.account_id))
    rows = rows[:top_k]

    if amount is not None:
        # Annotation only — callers may log distance to mean_weight.
        pass

    return rows
