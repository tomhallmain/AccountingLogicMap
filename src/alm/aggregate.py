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


def map_globals(edges: dict[EdgeKey, EdgeStat]) -> tuple[float, int, float]:
    """Global denominators for the normed blend, matching the test workbook `st` sheet.

    Returns (total_weight, total_depth, total_mean_weight):

      total_weight      st!B1 = sum(rw!D)                — Σ edge weight
      total_depth       st!B2 = sum(rw!E)                — Σ edge depth
      total_mean_weight st!B3 = sum(if(c=0,0, w/c))      — Σ per-edge mean weight

    total_mean_weight is deliberately NOT total_weight / total_depth. The workbook
    normalizes each of the three blend terms into a share that sums to 1 across
    edges, so the third term needs the sum of per-edge means as its denominator.
    Using the global mean instead leaves that term ~Σ(w/c)/(Σw/Σc) times too large
    (542x on the reference workbook), which collapses the blend into mean-edge-size.
    """
    total_weight = sum(e.weight_sum for e in edges.values())
    total_depth = sum(e.depth for e in edges.values())
    total_mean_weight = sum(e.weight_sum / e.depth for e in edges.values() if e.depth)
    return total_weight, total_depth, total_mean_weight


def build_logic_map(
    accounts: dict[str, Account],
    txns: list[Transaction],
    *,
    window_label: str = "baseline",
) -> LogicMap:
    rewritten = rewrite_transactions(txns)
    edges = aggregate_rewritten(rewritten)
    total_weight, total_depth, total_mean_weight = map_globals(edges)
    line_count = sum(len(t.lines) for t in txns)

    logic_map = LogicMap(
        accounts=accounts,
        edges=edges,
        total_weight=total_weight,
        total_depth=total_depth,
        total_mean_weight=total_mean_weight,
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
    total_weight, total_depth, total_mean_weight = map_globals(edges)
    return LogicMap(
        accounts=accounts,
        edges=edges,
        total_weight=total_weight,
        total_depth=total_depth,
        total_mean_weight=total_mean_weight,
        window_label=window_label,
        txn_count=txn_count,
        line_count=line_count,
    )
