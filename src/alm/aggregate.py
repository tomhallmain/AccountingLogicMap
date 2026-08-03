from __future__ import annotations

from collections import defaultdict

from .models import Account, EdgeKey, EdgeStat, LogicMap, Transaction
from .rewrite import rewrite_transactions


def aggregate_rewritten(
    rewritten: list[tuple[str, EdgeKey, float]],
) -> dict[EdgeKey, EdgeStat]:
    """Collapse identical edges.

    depth counts distinct transactions that produced the edge (not pair
    instances inside a single multi-line journal).
    """
    weights: dict[EdgeKey, float] = defaultdict(float)
    txn_sets: dict[EdgeKey, set[str]] = defaultdict(set)

    for txn_id, key, weight in rewritten:
        weights[key] += weight
        txn_sets[key].add(txn_id)

    edges: dict[EdgeKey, EdgeStat] = {}
    for key, weight_sum in weights.items():
        edges[key] = EdgeStat(
            key=key,
            weight_sum=weight_sum,
            depth=len(txn_sets[key]),
        )
    return edges


def build_logic_map(
    accounts: dict[str, Account],
    txns: list[Transaction],
    *,
    window_label: str = "baseline",
) -> LogicMap:
    rewritten = rewrite_transactions(txns)
    edges = aggregate_rewritten(rewritten)
    total_weight = sum(e.weight_sum for e in edges.values())
    total_depth = sum(e.depth for e in edges.values())
    mean_w = total_weight / total_depth if total_depth else 0.0
    line_count = sum(len(t.lines) for t in txns)

    logic_map = LogicMap(
        accounts=accounts,
        edges=edges,
        total_weight=total_weight,
        total_depth=total_depth,
        mean_weight_per_instance=mean_w,
        window_label=window_label,
        txn_count=len(txns),
        line_count=line_count,
    )
    return logic_map


def logic_map_from_edge_stats(
    accounts: dict[str, Account],
    edges: dict[EdgeKey, EdgeStat],
    *,
    window_label: str = "baseline",
    txn_count: int = 0,
    line_count: int = 0,
) -> LogicMap:
    total_weight = sum(e.weight_sum for e in edges.values())
    total_depth = sum(e.depth for e in edges.values())
    mean_w = total_weight / total_depth if total_depth else 0.0
    return LogicMap(
        accounts=accounts,
        edges=edges,
        total_weight=total_weight,
        total_depth=total_depth,
        mean_weight_per_instance=mean_w,
        window_label=window_label,
        txn_count=txn_count,
        line_count=line_count,
    )
