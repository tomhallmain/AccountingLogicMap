from __future__ import annotations

from .models import EdgeStat, LogicMap, ScoredEdge


def score_edge(
    stat: EdgeStat,
    *,
    total_weight: float,
    total_depth: int,
    total_mean_weight: float,
) -> tuple[float, float, float, float]:
    """Return (share_w, share_c, share_m, norm).

    Mirrors the workbook `n` sheet:
        average(w/st!B1, c/st!B2, (w/c)/st!B3)
    Each term is a share of its own global total, so all three are on the same
    scale and the average is a genuine blend. See aggregate.map_globals.
    """
    terms: list[float] = []
    share_w = (stat.weight_sum / total_weight) if total_weight else 0.0
    share_c = (stat.depth / total_depth) if total_depth else 0.0
    if total_mean_weight > 0 and stat.depth > 0:
        share_m = (stat.weight_sum / stat.depth) / total_mean_weight
    else:
        share_m = 0.0

    if total_weight:
        terms.append(share_w)
    if total_depth:
        terms.append(share_c)
    if total_mean_weight > 0 and stat.depth > 0:
        terms.append(share_m)

    norm = sum(terms) / len(terms) if terms else 0.0
    return share_w, share_c, share_m, norm


def score_map(logic_map: LogicMap) -> LogicMap:
    """Attach ranked spectrum to logic_map.scored (mutates and returns map)."""
    scored: list[ScoredEdge] = []
    for stat in logic_map.edges.values():
        share_w, share_c, share_m, norm = score_edge(
            stat,
            total_weight=logic_map.total_weight,
            total_depth=logic_map.total_depth,
            total_mean_weight=logic_map.total_mean_weight,
        )
        scored.append(
            ScoredEdge(
                key=stat.key,
                weight_sum=stat.weight_sum,
                depth=stat.depth,
                mean_weight=stat.mean_weight,
                share_w=share_w,
                share_c=share_c,
                share_m=share_m,
                norm=norm,
                rank=0,
            )
        )

    scored.sort(key=lambda s: (-s.norm, -s.weight_sum, s.key.debit_account_id, s.key.credit_account_id))
    for i, se in enumerate(scored, start=1):
        se.rank = i

    logic_map.scored = scored
    return logic_map


def node_activity(logic_map: LogicMap) -> list[dict[str, float | str]]:
    """Per-account debit/credit weight and incident norm sum."""
    rows: dict[str, dict[str, float | str]] = {}
    for acct_id, acct in logic_map.accounts.items():
        rows[acct_id] = {
            "account_id": acct_id,
            "account_type": acct.account_type,
            "as_debit_weight": 0.0,
            "as_credit_weight": 0.0,
            "incident_norm": 0.0,
        }

    rank_index = logic_map.edge_rank_index()
    for key, stat in logic_map.edges.items():
        for aid, field in (
            (key.debit_account_id, "as_debit_weight"),
            (key.credit_account_id, "as_credit_weight"),
        ):
            if aid not in rows:
                rows[aid] = {
                    "account_id": aid,
                    "account_type": logic_map.account_type(aid),
                    "as_debit_weight": 0.0,
                    "as_credit_weight": 0.0,
                    "incident_norm": 0.0,
                }
            rows[aid][field] = float(rows[aid][field]) + stat.weight_sum

        se = rank_index.get(key)
        if se:
            for aid in (key.debit_account_id, key.credit_account_id):
                rows[aid]["incident_norm"] = float(rows[aid]["incident_norm"]) + se.norm

    out = list(rows.values())
    out.sort(key=lambda r: (-float(r["incident_norm"]), str(r["account_id"])))
    return out
