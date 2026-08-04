from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from .aggregate import map_globals
from .models import Account, EdgeKey, EdgeStat, Line, LogicMap, ScoredEdge
from .score import node_activity, score_map


def _read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter="\t")
        return [{k: (v if v is not None else "") for k, v in row.items()} for row in reader]


def _write_tsv(path: Path, fieldnames: list[str], rows: Iterable[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def load_accounts(path: Path) -> dict[str, Account]:
    rows = _read_tsv(path)
    accounts: dict[str, Account] = {}
    for row in rows:
        acct = Account(
            account_id=row["account_id"].strip(),
            name=row.get("name", row["account_id"]).strip(),
            account_type=row["account_type"].strip(),
        )
        accounts[acct.account_id] = acct
    return accounts


def load_lines(path: Path) -> list[Line]:
    rows = _read_tsv(path)
    lines: list[Line] = []
    for row in rows:
        side = row["side"].strip().lower()
        lines.append(
            Line(
                txn_id=row["txn_id"].strip(),
                date=date.fromisoformat(row["date"].strip()),
                account_id=row["account_id"].strip(),
                side=side,
                amount=float(row["amount"]),
                memo=row.get("memo", "").strip(),
            )
        )
    return lines


def load_expected_verdicts(path: Path) -> dict[str, str]:
    """Optional column expected_verdict on candidates file — read distinct txn expectations."""
    rows = _read_tsv(path)
    out: dict[str, str] = {}
    for row in rows:
        exp = row.get("expected_verdict", "").strip()
        if exp:
            out[row["txn_id"].strip()] = exp.lower()
    return out


def load_holdout_edges(path: Path) -> list[tuple[str, str]]:
    rows = _read_tsv(path)
    return [(r["debit_account_id"].strip(), r["credit_account_id"].strip()) for r in rows]


def load_expected_anomalies(path: Path) -> list[tuple[str, str, str]]:
    rows = _read_tsv(path)
    return [
        (r["signal"].strip(), r["debit_account_id"].strip(), r["credit_account_id"].strip())
        for r in rows
    ]


def load_edge_list_tsv(path: Path) -> dict[EdgeKey, EdgeStat]:
    """Load a pre-aggregated edge list (spec §5.3).

    Accepts either the export column names (`debit_account`, `credit_account`,
    `edge_sum`) or the map-directory ones (`*_account_id`, `weight_sum`), so an
    `edges.tsv` this tool wrote can be fed straight back in.
    """
    aliases = {
        "debit": ("debit_account", "debit_account_id"),
        "credit": ("credit_account", "credit_account_id"),
        "weight": ("edge_sum", "weight_sum"),
    }

    def pick(row: dict[str, str], field: str) -> str:
        for name in aliases[field]:
            if row.get(name):
                return row[name]
        raise KeyError(f"{path}: expected one of {aliases[field]}")

    edges: dict[EdgeKey, EdgeStat] = {}
    for row in _read_tsv(path):
        key = EdgeKey(pick(row, "debit").strip(), pick(row, "credit").strip())
        weight = float(pick(row, "weight"))
        depth = int(float(row["depth"]))
        # Repeated keys accumulate rather than overwrite; an export may carry the
        # same pair on several rows.
        prior = edges.get(key)
        edges[key] = EdgeStat(
            key=key,
            weight_sum=weight + (prior.weight_sum if prior else 0.0),
            depth=depth + (prior.depth if prior else 0),
            pair_instances=depth + (prior.pair_instances if prior else 0),
        )
    return edges


def write_map_dir(logic_map: LogicMap, out_dir: Path) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    score_map(logic_map)

    _write_tsv(
        out_dir / "meta.tsv",
        [
            "window_label",
            "txn_count",
            "line_count",
            "edge_count",
            "total_weight",
            "total_depth",
            "total_mean_weight",
            "granularity",
            "rewrite_mode",
            "period_count",
            "period_first",
            "period_last",
            "generated_at",
        ],
        [
            {
                "window_label": logic_map.window_label,
                "txn_count": logic_map.txn_count,
                "line_count": logic_map.line_count,
                "edge_count": len(logic_map.edges),
                "total_weight": f"{logic_map.total_weight:.6f}",
                "total_depth": logic_map.total_depth,
                "total_mean_weight": f"{logic_map.total_mean_weight:.6f}",
                "granularity": logic_map.granularity,
                "rewrite_mode": logic_map.rewrite_mode,
                "period_count": len(logic_map.periods),
                "period_first": logic_map.periods[0] if logic_map.periods else "",
                "period_last": logic_map.periods[-1] if logic_map.periods else "",
                "generated_at": datetime.now().isoformat(timespec="seconds"),
            }
        ],
    )

    _write_tsv(
        out_dir / "accounts.tsv",
        ["account_id", "name", "account_type"],
        [
            {
                "account_id": a.account_id,
                "name": a.name,
                "account_type": a.account_type,
            }
            for a in logic_map.accounts.values()
        ],
    )

    edge_rows = [
        _scored_to_row(se, logic_map.edges.get(se.key)) for se in logic_map.scored
    ]
    fields = [
        "debit_account_id",
        "credit_account_id",
        "weight_sum",
        "depth",
        "pair_instances",
        "mean_weight",
        "share_w",
        "share_c",
        "share_m",
        "norm",
        "rank",
        "ambiguous_share",
        "is_self_loop",
    ]
    _write_tsv(out_dir / "edges.tsv", fields, edge_rows)
    _write_tsv(out_dir / "spectrum.tsv", fields, edge_rows)

    # Per-period edge mass, so seasonal conditioning survives a round-trip.
    _write_tsv(
        out_dir / "edge_periods.tsv",
        ["debit_account_id", "credit_account_id", "period", "weight", "depth"],
        [
            {
                "debit_account_id": key.debit_account_id,
                "credit_account_id": key.credit_account_id,
                "period": period,
                "weight": f"{weight:.6f}",
                "depth": stat.period_depths.get(period, 0),
            }
            for key, stat in sorted(
                logic_map.edges.items(),
                key=lambda kv: (kv[0].debit_account_id, kv[0].credit_account_id),
            )
            for period, weight in sorted(stat.period_weights.items())
        ],
    )

    activity = node_activity(logic_map)
    _write_tsv(
        out_dir / "node_activity.tsv",
        ["account_id", "account_type", "as_debit_weight", "as_credit_weight", "incident_norm"],
        [
            {
                "account_id": r["account_id"],
                "account_type": r["account_type"],
                "as_debit_weight": f"{float(r['as_debit_weight']):.6f}",
                "as_credit_weight": f"{float(r['as_credit_weight']):.6f}",
                "incident_norm": f"{float(r['incident_norm']):.6f}",
            }
            for r in activity
        ],
    )


def _scored_to_row(se: ScoredEdge, stat: EdgeStat | None = None) -> dict:
    # pair_instances lives on EdgeStat rather than ScoredEdge, but it has to be
    # persisted for a map directory to reload without losing the multi-line
    # signal (pair_instances > depth). Falls back to depth when unavailable.
    return {
        "debit_account_id": se.key.debit_account_id,
        "credit_account_id": se.key.credit_account_id,
        "weight_sum": f"{se.weight_sum:.6f}",
        "depth": se.depth,
        "pair_instances": stat.pair_instances if stat is not None else se.depth,
        "mean_weight": f"{se.mean_weight:.6f}",
        "share_w": f"{se.share_w:.6f}",
        "share_c": f"{se.share_c:.6f}",
        "share_m": f"{se.share_m:.6f}",
        "norm": f"{se.norm:.6f}",
        "rank": se.rank,
        "ambiguous_share": f"{se.ambiguous_share:.6f}",
        "is_self_loop": "1" if se.is_self_loop else "0",
    }


def load_map_dir(path: Path) -> LogicMap:
    path = Path(path)
    accounts = load_accounts(path / "accounts.tsv")
    edge_rows = _read_tsv(path / "edges.tsv")
    edges: dict[EdgeKey, EdgeStat] = {}
    scored: list[ScoredEdge] = []
    for row in edge_rows:
        key = EdgeKey(row["debit_account_id"], row["credit_account_id"])
        weight = float(row["weight_sum"])
        depth = int(float(row["depth"]))
        edges[key] = EdgeStat(
            key=key,
            weight_sum=weight,
            depth=depth,
            # Older map directories predate the column; depth is the floor, since
            # every contributing transaction emits at least one pair.
            pair_instances=int(float(row.get("pair_instances") or depth)),
            ambiguous_weight=weight * float(row.get("ambiguous_share", 0) or 0),
        )
        scored.append(
            ScoredEdge(
                key=key,
                weight_sum=weight,
                depth=depth,
                mean_weight=float(row["mean_weight"]),
                share_w=float(row["share_w"]),
                share_c=float(row["share_c"]),
                share_m=float(row.get("share_m", 0) or 0),
                norm=float(row["norm"]),
                rank=int(float(row["rank"])),
                ambiguous_share=float(row.get("ambiguous_share", 0) or 0),
                is_self_loop=key.is_self_loop,
            )
        )

    period_path = path / "edge_periods.tsv"
    if period_path.exists():
        for row in _read_tsv(period_path):
            key = EdgeKey(row["debit_account_id"], row["credit_account_id"])
            stat = edges.get(key)
            if stat is None:
                continue
            stat.period_weights[row["period"]] = float(row["weight"])
            stat.period_depths[row["period"]] = int(float(row["depth"] or 0))

    meta_rows = _read_tsv(path / "meta.tsv")
    meta = meta_rows[0] if meta_rows else {}
    derived_w, derived_c, derived_m = map_globals(edges)
    total_weight = float(meta.get("total_weight") or derived_w)
    total_depth = int(float(meta.get("total_depth") or derived_c))
    total_mean_weight = float(meta.get("total_mean_weight") or derived_m)

    scored.sort(key=lambda s: s.rank)
    return LogicMap(
        accounts=accounts,
        edges=edges,
        total_weight=total_weight,
        total_depth=total_depth,
        total_mean_weight=total_mean_weight,
        window_label=meta.get("window_label", path.name),
        granularity=meta.get("granularity") or "month",
        rewrite_mode=meta.get("rewrite_mode") or "averaging",
        periods=sorted({p for e in edges.values() for p in e.period_weights})
        or (
            [meta["period_first"], meta["period_last"]]
            if meta.get("period_first") and meta.get("period_last")
            else []
        ),
        txn_count=int(float(meta.get("txn_count") or 0)),
        line_count=int(float(meta.get("line_count") or 0)),
        scored=scored,
    )


def write_verify_results(path: Path, results) -> None:
    rows = []
    for r in results:
        rows.append(
            {
                "txn_id": r.txn_id,
                "verdict": r.verdict,
                "expected_verdict": r.expected_verdict or "",
                "reasons": " | ".join(r.reasons),
                "edge_count": len(r.findings),
                "edges": "; ".join(
                    f"{f.key.label()} seen={f.seen} rank={f.rank} ({f.note})" for f in r.findings
                ),
            }
        )
    _write_tsv(
        path,
        ["txn_id", "verdict", "expected_verdict", "reasons", "edge_count", "edges"],
        rows,
    )


def write_predict_rows(path: Path, rows) -> None:
    _write_tsv(
        path,
        ["account_id", "account_type", "weight_sum", "depth", "probability", "norm", "mean_weight"],
        [
            {
                "account_id": r.account_id,
                "account_type": r.account_type,
                "weight_sum": f"{r.weight_sum:.6f}",
                "depth": r.depth,
                "probability": f"{r.probability:.6f}",
                "norm": f"{r.norm:.6f}" if r.norm is not None else "",
                "mean_weight": f"{r.mean_weight:.6f}",
            }
            for r in rows
        ],
    )


def write_anomaly_rows(path: Path, rows) -> None:
    _write_tsv(
        path,
        [
            "signals",
            "debit_account_id",
            "credit_account_id",
            "baseline_share_w",
            "open_share_w",
            "delta_share_w",
            "baseline_rank",
            "open_rank",
            "note",
        ],
        [
            {
                "signals": ",".join(r.signals),
                "debit_account_id": r.debit_account_id,
                "credit_account_id": r.credit_account_id,
                "baseline_share_w": f"{r.baseline_share_w:.6f}",
                "open_share_w": f"{r.open_share_w:.6f}",
                "delta_share_w": f"{r.delta_share_w:.6f}",
                "baseline_rank": r.baseline_rank if r.baseline_rank is not None else "",
                "open_rank": r.open_rank if r.open_rank is not None else "",
                "note": r.note,
            }
            for r in rows
        ],
    )


def write_period_rows(path: Path, stats, forward=None) -> None:
    """Per-period activity, with the forward expectation appended as a final row.

    The projection is written alongside the observations it came from so the
    artifact is self-contained: `kind` distinguishes them.
    """
    rows = [
        {
            "kind": "period",
            "period": s.period,
            "txn_count": s.txn_count,
            "line_count": s.line_count,
            "weight": f"{s.weight:.2f}",
            "mean_txn_weight": f"{s.mean_txn_weight:.2f}",
        }
        for s in stats
    ]
    if forward is not None:
        rows.append(
            {
                "kind": "forward_expectation",
                "period": forward.open_period,
                "txn_count": forward.actual_txn_count,
                "weight": f"{forward.actual_weight:.2f}",
                "baseline_periods": len(forward.baseline_periods),
                "expected_weight": f"{forward.expected_weight:.2f}",
                "expected_txn_count": f"{forward.expected_txn_count:.2f}",
                "weight_variance": f"{forward.weight_variance:+.2f}",
                "weight_variance_pct": f"{forward.weight_variance_pct:+.4f}",
            }
        )
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    _write_tsv(path, fields, rows)


def write_balance_rows(path: Path, findings, contra=None) -> None:
    """Unnatural-balance findings, with inferred contra accounts appended.

    The contras are written alongside the findings because they are the reason
    certain accounts are *absent* from the list — a reviewer needs to see what
    the inference excused, not just what it flagged.
    """
    rows = [
        {
            "kind": "unnatural_balance",
            "account_id": f.account_id,
            "account_type": f.account_type,
            "period": f.period,
            "expected_side": f.expected_side,
            "actual_side": f.actual_side,
            "balance": f"{f.balance:.2f}",
            "periods_off": f.periods_off,
            "consecutive_off": f.consecutive_off,
            "contra_inferred": "1" if f.contra_inferred else "0",
            "severity": f.severity,
            "note": f.note,
        }
        for f in findings
    ]
    for verdict in (contra or {}).values():
        if not verdict.is_contra:
            continue
        rows.append(
            {
                "kind": "inferred_contra",
                "account_id": verdict.account_id,
                "contra_inferred": "1",
                "severity": "info",
                "note": f"score {verdict.score}: " + "; ".join(verdict.reasons),
            }
        )
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    _write_tsv(path, fields, rows)


def write_eval_summary(path: Path, rows: list[dict]) -> None:
    """Write heterogeneous metric rows.

    Metric families carry different keys (verify vs predict vs anomaly), so the
    header is the union across all rows in first-seen order. Taking the header
    from rows[0] alone silently blanks every column the first row lacks.
    """
    if not rows:
        return
    fields: list[str] = []
    for row in rows:
        for key in row:
            if key not in fields:
                fields.append(key)
    _write_tsv(path, fields, rows)


def write_type_spectra(path: Path, spectra) -> None:
    """One row per entity per type pair — the comparable projection (spec §7.10)."""
    _write_tsv(
        path,
        [
            "entity",
            "level",
            "debit_type",
            "credit_type",
            "weight_share",
            "depth_share",
            "edge_count",
            "weight",
            "depth",
        ],
        [
            {
                "entity": s.label,
                "level": s.level,
                "debit_type": c.debit,
                "credit_type": c.credit,
                "weight_share": f"{c.weight_share:.6f}",
                "depth_share": f"{c.depth_share:.6f}",
                "edge_count": c.edge_count,
                "weight": f"{c.weight:.6f}",
                "depth": c.depth,
            }
            for s in spectra
            for c in sorted(s.cells.values(), key=lambda c: -c.weight_share)
        ],
    )


def write_benchmark_rows(path: Path, rows) -> None:
    _write_tsv(
        path,
        [
            "signal",
            "debit_type",
            "credit_type",
            "subject_share",
            "peer_median",
            "peer_mean",
            "peer_min",
            "peer_max",
            "delta",
            "peers_present",
            "peers_total",
        ],
        [
            {
                "signal": r.signal,
                "debit_type": r.debit,
                "credit_type": r.credit,
                "subject_share": f"{r.subject_share:.6f}",
                "peer_median": f"{r.peer_median:.6f}",
                "peer_mean": f"{r.peer_mean:.6f}",
                "peer_min": f"{r.peer_min:.6f}",
                "peer_max": f"{r.peer_max:.6f}",
                "delta": f"{r.delta:+.6f}",
                "peers_present": r.peers_present,
                "peers_total": r.peers_total,
            }
            for r in rows
        ],
    )


def write_divergence_matrix(path: Path, rows) -> None:
    _write_tsv(
        path,
        ["entity_a", "entity_b", "divergence"],
        [
            {"entity_a": a, "entity_b": b, "divergence": f"{d:.6f}"}
            for a, b, d in rows
        ],
    )
