from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .aggregate import build_logic_map
from .anomalies import compare_maps
from .eval import evaluate_anomalies, evaluate_prediction, run_verify_eval
from .io_excel import load_excel_reference
from .io_tsv import (
    load_accounts,
    load_expected_anomalies,
    load_expected_verdicts,
    load_holdout_edges,
    load_lines,
    load_map_dir,
    write_anomaly_rows,
    write_eval_summary,
    write_map_dir,
    write_predict_rows,
    write_verify_results,
)
from .models import Transaction, group_lines
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
    LOG.info("spectrum top:")
    for se in logic_map.scored[:top]:
        LOG.info(
            "  %2d. %s   weight=%.2f depth=%d norm=%.4f",
            se.rank,
            se.key.label(),
            se.weight_sum,
            se.depth,
            se.norm,
        )


def cmd_build(args: argparse.Namespace) -> int:
    accounts = load_accounts(Path(args.accounts))
    lines = load_lines(Path(args.transactions))
    LOG.info("build: loaded %d accounts, %d lines", len(accounts), len(lines))

    txns, errors = build_transactions(lines, accounts)
    for err in errors:
        LOG.error("txn %s: %s", err.txn_id, err.message)
    if errors:
        LOG.error("build aborted: %d validation error(s)", len(errors))
        return 1

    LOG.info("build: %d valid transactions", len(txns))
    logic_map = build_logic_map(accounts, txns, window_label=args.label or Path(args.out).name)
    score_map(logic_map)

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
    rows = predict_counterparts(
        logic_map,
        args.account,
        args.side,
        top_k=args.top,
        amount=amount,
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
            r.signal,
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
                "eval %s: hit_rate=%.3f random=%.3f above_random=%s (n=%s)",
                s["metric"],
                s["hit_rate"],
                s["random_baseline"],
                s["above_random"],
                s["n"],
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
    b.set_defaults(func=cmd_build)

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
