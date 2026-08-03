from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from .aggregate import build_logic_map, logic_map_from_edge_stats
from .anomalies import compare_maps
from .eval import evaluate_anomalies, evaluate_prediction, run_verify_eval
from .io_excel import load_excel_reference
from .io_tsv import (
    load_accounts,
    load_edge_list_tsv,
    load_expected_anomalies,
    load_expected_verdicts,
    load_holdout_edges,
    load_lines,
    load_map_dir,
    write_anomaly_rows,
    write_eval_summary,
    write_map_dir,
    write_period_rows,
    write_predict_rows,
    write_verify_results,
)
from .models import DEFAULT_BASELINE_PERIODS, Account, EdgeKey, Transaction, group_lines
from .periods import (
    GRANULARITIES,
    filter_lines,
    forward_expectation,
    period_activity,
    seasonal_periods,
)
from .predict import predict_counterparts
from .score import score_map
from .validate import build_transactions
from .verify import verify_transactions

LOG = logging.getLogger("alm")


def _configure_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s  %(message)s",
        stream=sys.stderr,
    )


def _log_spectrum(logic_map, top: int = 10) -> None:
    LOG.info(
        "build: %s distinct edges; total_weight=%.2f total_depth=%d",
        len(logic_map.edges),
        logic_map.total_weight,
        logic_map.total_depth,
    )
    total = logic_map.total_weight or 1.0
    self_loop_w = sum(s.weight_sum for s in logic_map.edges.values() if s.key.is_self_loop)
    ambiguous_w = sum(s.ambiguous_weight for s in logic_map.edges.values())
    if self_loop_w:
        LOG.warning(
            "build: %d self-loop edge(s) carry %.1f%% of weight — rewrite artifacts, not value flows",
            sum(1 for s in logic_map.edges.values() if s.key.is_self_loop),
            100 * self_loop_w / total,
        )
    if ambiguous_w:
        LOG.info(
            "build: %.1f%% of weight came from journals with several lines on both sides "
            "(pairing inferred, see ambiguous_share)",
            100 * ambiguous_w / total,
        )

    LOG.info("spectrum top:")
    for se in logic_map.scored[:top]:
        flags = "".join(
            f" [{f}]"
            for f in (
                "self-loop" if se.is_self_loop else "",
                f"ambig {se.ambiguous_share:.0%}" if se.ambiguous_share > 0 else "",
            )
            if f
        )
        LOG.info(
            "  %2d. %s   weight=%.2f depth=%d norm=%.4f%s",
            se.rank,
            se.key.label(),
            se.weight_sum,
            se.depth,
            se.norm,
            flags,
        )


def _date_arg(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def cmd_build(args: argparse.Namespace) -> int:
    accounts = load_accounts(Path(args.accounts))
    lines = load_lines(Path(args.transactions))
    LOG.info("build: loaded %d accounts, %d lines", len(accounts), len(lines))

    start, end = _date_arg(args.start), _date_arg(args.end)
    if start or end:
        kept = filter_lines(lines, start=start, end=end)
        LOG.info(
            "build: window [%s .. %s] keeps %d of %d lines",
            start or "-inf",
            end or "+inf",
            len(kept),
            len(lines),
        )
        lines = kept
        if not lines:
            LOG.error("build aborted: window selected no lines")
            return 1

    txns, errors = build_transactions(lines, accounts)
    for err in errors:
        LOG.error("txn %s: %s", err.txn_id, err.message)
    if errors:
        LOG.error("build aborted: %d validation error(s)", len(errors))
        return 1

    LOG.info("build: %d valid transactions", len(txns))
    logic_map = build_logic_map(accounts, txns, window_label=args.label or Path(args.out).name)
    score_map(logic_map)

    stats = period_activity(txns, granularity=args.granularity)
    logic_map.granularity = args.granularity
    logic_map.periods = [s.period for s in stats]
    if stats:
        LOG.info(
            "build: %d %s period(s) %s .. %s",
            len(stats),
            args.granularity,
            stats[0].period,
            stats[-1].period,
        )

    # Weight conservation check
    rewritten_total = logic_map.total_weight
    line_debit_total = sum(
        ln.amount for t in txns for ln in t.lines if ln.side == "debit"
    )
    if abs(rewritten_total - line_debit_total) > 1e-4:
        LOG.warning(
            "weight conservation drift: map=%.6f line_debits=%.6f",
            rewritten_total,
            line_debit_total,
        )
    else:
        LOG.info("build: rewrite ok; conserved weight within tol")

    _log_spectrum(logic_map)
    out = Path(args.out)
    write_map_dir(logic_map, out)
    LOG.info("wrote %s/*.tsv", out)
    return 0


def cmd_build_from_excel(args: argparse.Namespace) -> int:
    xlsx = Path(args.xlsx)
    LOG.info("build-from-excel: %s", xlsx)
    try:
        logic_map = load_excel_reference(xlsx, window_label=args.label or "excel_ref")
    except ImportError as exc:
        LOG.error("%s", exc)
        return 1
    _log_spectrum(logic_map)
    out = Path(args.out)
    write_map_dir(logic_map, out)
    LOG.info("wrote %s/*.tsv", out)
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    logic_map = load_map_dir(Path(args.map))
    accounts = logic_map.accounts
    lines = load_lines(Path(args.candidates))
    expected = load_expected_verdicts(Path(args.candidates))

    txns, errors = build_transactions(lines, accounts, require_known_accounts=True)
    # Include invalid/unbalanced candidates so verify can mark them fail.
    if errors:
        grouped = group_lines(lines)
        txns = [
            Transaction(txn_id=tid, date=min(ln.date for ln in lns), lines=lns)
            for tid, lns in grouped.items()
        ]
        for err in errors:
            LOG.warning("candidate %s: %s", err.txn_id, err.message)

    results = verify_transactions(logic_map, txns, expected=expected or None)
    for r in results:
        exp = f" (expected {r.expected_verdict})" if r.expected_verdict else ""
        LOG.info("verify %s → %s%s", r.txn_id, r.verdict, exp)
        for reason in r.reasons[:5]:
            LOG.info("    - %s", reason)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_verify_results(out_dir / "verify_results.tsv", results)
    LOG.info("wrote %s", out_dir / "verify_results.tsv")
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    logic_map = load_map_dir(Path(args.map))
    amount = float(args.amount) if args.amount is not None else None

    season: list[str] | None = None
    if args.season:
        season = seasonal_periods(args.season, logic_map.periods)
        if not season:
            LOG.warning(
                "no prior-year periods matching %s in this map (has %s); "
                "falling back to the whole window",
                args.season,
                f"{logic_map.periods[0]}..{logic_map.periods[-1]}"
                if logic_map.periods
                else "no period data",
            )
        else:
            LOG.info("conditioning on season %s → periods %s", args.season, ", ".join(season))

    rows = predict_counterparts(
        logic_map,
        args.account,
        args.side,
        top_k=args.top,
        amount=amount,
        periods=season or None,
    )
    if not rows:
        LOG.warning("no counterparts found for %s side=%s", args.account, args.side)
        return 0

    LOG.info("predict counterparts for %s (%s):", args.account, args.side)
    for i, r in enumerate(rows, 1):
        extra = ""
        if amount is not None and r.mean_weight:
            extra = f"  |Δmean|={abs(amount - r.mean_weight):.2f}"
        LOG.info(
            "  %2d. %-40s  p=%.3f  depth=%d  mean=%.2f  type=%s%s",
            i,
            r.account_id,
            r.probability,
            r.depth,
            r.mean_weight,
            r.account_type,
            extra,
        )

    if args.out:
        write_predict_rows(Path(args.out), rows)
        LOG.info("wrote %s", args.out)
    return 0


def cmd_anomalies(args: argparse.Namespace) -> int:
    baseline = load_map_dir(Path(args.baseline))
    open_map = load_map_dir(Path(args.open))
    rows = compare_maps(baseline, open_map, top_k=args.top)
    LOG.info("anomalies top %d:", len(rows))
    for r in rows[: min(15, len(rows))]:
        LOG.info(
            "  [%s] %s | %s  Δshare=%+.4f  (%s)",
            ",".join(r.signals),
            r.debit_account_id,
            r.credit_account_id,
            r.delta_share_w,
            r.note,
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_anomaly_rows(out_dir / "anomaly_edges.tsv", rows)
    LOG.info("wrote %s", out_dir / "anomaly_edges.tsv")
    return 0


def cmd_periods(args: argparse.Namespace) -> int:
    """Per-period activity and the forward expectation from concept §7."""
    accounts = load_accounts(Path(args.accounts))
    lines = filter_lines(
        load_lines(Path(args.transactions)),
        start=_date_arg(args.start),
        end=_date_arg(args.end),
    )
    txns, errors = build_transactions(lines, accounts)
    for err in errors:
        LOG.error("txn %s: %s", err.txn_id, err.message)
    if errors:
        LOG.error("periods aborted: %d validation error(s)", len(errors))
        return 1

    stats = period_activity(txns, granularity=args.granularity)
    LOG.info("periods (%s): %d period(s), %d transactions", args.granularity, len(stats), len(txns))
    for s in stats:
        LOG.info(
            "  %-8s  txns=%3d  lines=%4d  weight=%12.2f  mean/txn=%9.2f",
            s.period,
            s.txn_count,
            s.line_count,
            s.weight,
            s.mean_txn_weight,
        )

    fx = forward_expectation(stats, baseline_periods=args.baseline_periods)
    if fx is None:
        LOG.warning("periods: need at least 2 periods to project a forward expectation")
    else:
        LOG.info(
            "forward expectation for %s from trailing %d closed period(s) %s .. %s:",
            fx.open_period,
            len(fx.baseline_periods),
            fx.baseline_periods[0],
            fx.baseline_periods[-1],
        )
        LOG.info(
            "  weight   expected=%.2f  actual=%.2f  variance=%+.2f (%+.1f%%)",
            fx.expected_weight,
            fx.actual_weight,
            fx.weight_variance,
            100 * fx.weight_variance_pct,
        )
        LOG.info(
            "  txns     expected=%.1f  actual=%d",
            fx.expected_txn_count,
            fx.actual_txn_count,
        )

    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        write_period_rows(out_dir / "periods.tsv", stats, fx)
        LOG.info("wrote %s", out_dir / "periods.tsv")
    return 0


def cmd_build_from_edges(args: argparse.Namespace) -> int:
    """Build a map from a pre-aggregated edge list (spec §5.3), no Excel needed."""
    accounts = load_accounts(Path(args.accounts)) if args.accounts else {}
    edges = load_edge_list_tsv(Path(args.edges))
    for key in edges:
        for aid in (key.debit_account_id, key.credit_account_id):
            accounts.setdefault(aid, Account(account_id=aid, name=aid, account_type="Unknown"))

    logic_map = score_map(
        logic_map_from_edge_stats(
            accounts, edges, window_label=args.label or Path(args.out).name
        )
    )
    LOG.info("build-from-edges: %d edges from %s", len(edges), args.edges)
    _log_spectrum(logic_map)
    out = Path(args.out)
    write_map_dir(logic_map, out)
    LOG.info("wrote %s/*.tsv", out)
    return 0


def cmd_eval(args: argparse.Namespace) -> int:
    logic_map = load_map_dir(Path(args.map))
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    summaries: list[dict] = []
    details: list[dict] = []

    if args.candidates:
        lines = load_lines(Path(args.candidates))
        expected = load_expected_verdicts(Path(args.candidates))
        grouped = group_lines(lines)
        txns = [
            Transaction(txn_id=tid, date=min(ln.date for ln in lns), lines=lns)
            for tid, lns in grouped.items()
        ]
        results, summary = run_verify_eval(logic_map, txns, expected)
        summaries.append(summary)
        for r in results:
            details.append(
                {
                    "kind": "verify",
                    "txn_id": r.txn_id,
                    "verdict": r.verdict,
                    "expected": r.expected_verdict or "",
                    "match": (
                        r.verdict == r.expected_verdict if r.expected_verdict else ""
                    ),
                }
            )
        LOG.info("eval verify: %s", summary)

    if args.holdout:
        holdout = load_holdout_edges(Path(args.holdout))
        pred_summaries = evaluate_prediction(logic_map, holdout)
        summaries.extend(pred_summaries)
        for s in pred_summaries:
            LOG.info(
                "eval %s [%s]: hit_rate=%.3f random=%.3f above_random=%s (n=%s)",
                s["metric"],
                s["cohort"],
                s["hit_rate"],
                s["random_baseline"],
                s["above_random"],
                s["n"],
            )
        # Edge coverage is not leakage: a stable business repeats its edge types
        # every month, so a properly held-out window still overlaps the map. What
        # decides whether this measures generalisation is whether the holdout
        # *transactions* were excluded from the build — print the map's window so
        # the reader can check.
        in_map = sum(1 for dr, cr in holdout if EdgeKey(dr, cr) in logic_map.edges)
        window = (
            f"{logic_map.periods[0]} .. {logic_map.periods[-1]}"
            if logic_map.periods
            else "unrecorded"
        )
        LOG.info(
            "eval predict: %d/%d holdout edge types occur in the map (window %s); "
            "hit-rate measures generalisation only if the holdout transactions "
            "were outside that window",
            in_map,
            len(holdout),
            window,
        )

    if args.baseline and args.open_map:
        baseline = load_map_dir(Path(args.baseline))
        open_map = load_map_dir(Path(args.open_map))
        anomalies = compare_maps(baseline, open_map, top_k=args.top)
        expected_signals = [
            ("missing_edge", "1000 Bank", "4000 Vehicle Sales"),
            ("new_edge", "1200 Clearing", "1000 Bank"),
            ("new_edge", "1000 Bank", "2500 New Floor Plan"),
        ]
        if args.expected_anomalies:
            expected_signals = load_expected_anomalies(Path(args.expected_anomalies))
        anom_summary = evaluate_anomalies(anomalies, expected_signals=expected_signals)
        summaries.append(
            {
                "metric": anom_summary["metric"],
                "n": anom_summary["n"],
                "recovered": anom_summary["recovered"],
                "recovery_rate": anom_summary["recovery_rate"],
            }
        )
        for d in anom_summary["detail"]:
            details.append(
                {
                    "kind": "anomaly",
                    "txn_id": "",
                    "verdict": d["signal"],
                    "expected": f"{d['debit']}|{d['credit']}",
                    "match": d["recovered"],
                }
            )
        LOG.info(
            "eval anomalies: recovered %s/%s (%.0f%%)",
            anom_summary["recovered"],
            anom_summary["n"],
            100 * anom_summary["recovery_rate"],
        )

    write_eval_summary(out_dir / "eval_summary.tsv", summaries)
    if details:
        write_eval_summary(out_dir / "eval_detail.tsv", details)
    LOG.info("wrote %s", out_dir / "eval_summary.tsv")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="alm",
        description="Accounting Logic Map — Python proof of concept",
    )
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("build", help="Build map from journal line TSVs")
    b.add_argument("--accounts", required=True)
    b.add_argument("--transactions", required=True)
    b.add_argument("--out", required=True)
    b.add_argument("--label", default=None)
    b.add_argument("--from", dest="start", default=None, metavar="YYYY-MM-DD",
                   help="window start, inclusive")
    b.add_argument("--to", dest="end", default=None, metavar="YYYY-MM-DD",
                   help="window end, inclusive")
    b.add_argument("--granularity", default="month", choices=list(GRANULARITIES))
    b.set_defaults(func=cmd_build)

    bd = sub.add_parser("build-from-edges", help="Build a map from a pre-aggregated edge list TSV")
    bd.add_argument("--edges", required=True)
    bd.add_argument("--accounts", default=None, help="optional; supplies account types")
    bd.add_argument("--out", required=True)
    bd.add_argument("--label", default=None)
    bd.set_defaults(func=cmd_build_from_edges)

    pe = sub.add_parser("periods", help="Per-period activity and forward expectation")
    pe.add_argument("--accounts", required=True)
    pe.add_argument("--transactions", required=True)
    pe.add_argument("--out", default=None)
    pe.add_argument("--from", dest="start", default=None, metavar="YYYY-MM-DD")
    pe.add_argument("--to", dest="end", default=None, metavar="YYYY-MM-DD")
    pe.add_argument("--granularity", default="month", choices=list(GRANULARITIES))
    pe.add_argument("--baseline-periods", type=int, default=DEFAULT_BASELINE_PERIODS)
    pe.set_defaults(func=cmd_periods)

    be = sub.add_parser("build-from-excel", help="Build map from reference xlsx rw/ca sheets")
    be.add_argument("--xlsx", required=True)
    be.add_argument("--out", required=True)
    be.add_argument("--label", default=None)
    be.set_defaults(func=cmd_build_from_excel)

    v = sub.add_parser("verify", help="Verify candidate transactions against a map")
    v.add_argument("--map", required=True)
    v.add_argument("--candidates", required=True)
    v.add_argument("--out", required=True)
    v.set_defaults(func=cmd_verify)

    pr = sub.add_parser("predict", help="Predict counterpart accounts")
    pr.add_argument("--map", required=True)
    pr.add_argument("--account", required=True)
    pr.add_argument("--side", required=True, choices=["debit", "credit"])
    pr.add_argument("--top", type=int, default=10)
    pr.add_argument("--amount", type=float, default=None)
    pr.add_argument("--season", default=None, metavar="PERIOD",
                    help="condition on the same slot in prior years, e.g. 2025-01")
    pr.add_argument("--out", default=None)
    pr.set_defaults(func=cmd_predict)

    an = sub.add_parser("anomalies", help="Compare baseline vs open maps")
    an.add_argument("--baseline", required=True)
    an.add_argument("--open", required=True)
    an.add_argument("--out", required=True)
    an.add_argument("--top", type=int, default=25)
    an.set_defaults(func=cmd_anomalies)

    ev = sub.add_parser("eval", help="Run success-criteria checks")
    ev.add_argument("--map", required=True)
    ev.add_argument("--out", required=True)
    ev.add_argument("--candidates", default=None)
    ev.add_argument("--holdout", default=None)
    ev.add_argument("--baseline", default=None)
    ev.add_argument("--open-map", default=None)
    ev.add_argument("--expected-anomalies", default=None)
    ev.add_argument("--top", type=int, default=25)
    ev.set_defaults(func=cmd_eval)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    _configure_logging(args.verbose)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
