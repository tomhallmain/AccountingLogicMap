from __future__ import annotations

from collections import Counter

from .models import EVAL_HIT_K, PREDICT_FREQUENT_DEPTH, EdgeKey, LogicMap, Transaction
from .predict import predict_counterparts
from .verify import verify_transactions


def evaluate_verification(
    results,
) -> dict[str, float | int | str]:
    """Compare verdicts to expected_verdict when present."""
    labeled = [r for r in results if r.expected_verdict]
    if not labeled:
        counts = Counter(r.verdict for r in results)
        return {
            "metric": "verify_unlabeled",
            "n": len(results),
            "pass": counts.get("pass", 0),
            "warn": counts.get("warn", 0),
            "fail": counts.get("fail", 0),
            "match_rate": "",
        }

    matches = sum(1 for r in labeled if r.verdict == r.expected_verdict)
    # Soft match: expected pass accepts warn; expected fail accepts warn only if we want —
    # keep strict match for summary, plus separation helper.
    normal = [r for r in labeled if r.expected_verdict == "pass"]
    bad = [r for r in labeled if r.expected_verdict == "fail"]
    normal_ok = sum(1 for r in normal if r.verdict in {"pass", "warn"})
    bad_flagged = sum(1 for r in bad if r.verdict in {"fail", "warn"})

    return {
        "metric": "verify_labeled",
        "n": len(labeled),
        "strict_match_rate": matches / len(labeled) if labeled else 0.0,
        "normal_pass_or_warn_rate": normal_ok / len(normal) if normal else "",
        "bad_fail_or_warn_rate": bad_flagged / len(bad) if bad else "",
    }


def evaluate_prediction(
    logic_map: LogicMap,
    holdout: list[tuple[str, str]],
    *,
    ks: tuple[int, ...] = EVAL_HIT_K,
    frequent_depth: int = PREDICT_FREQUENT_DEPTH,
) -> list[dict]:
    """Hit-rate@K for conditioning on each side; compare to uniform random baseline.

    Reported for two cohorts, because the spec's pass bar is stated only for the
    second:
      cohort=all        every holdout edge
      cohort=frequent   holdout edges whose map depth >= frequent_depth
    """
    n_accounts = max(len(logic_map.accounts), 1)
    summaries: list[dict] = []

    # Depth of each holdout edge in the map (0 if the map never saw it).
    depths = {
        (dr, cr): (
            logic_map.edges[EdgeKey(dr, cr)].depth
            if EdgeKey(dr, cr) in logic_map.edges
            else 0
        )
        for dr, cr in holdout
    }
    cohorts = {
        "all": list(holdout),
        "frequent": [e for e in holdout if depths[e] >= frequent_depth],
    }

    for cohort, edges in cohorts.items():
        for k in ks:
            hits_debit = 0
            hits_credit = 0
            for dr, cr in edges:
                if any(p.account_id == cr for p in predict_counterparts(logic_map, dr, "debit", top_k=k)):
                    hits_debit += 1
                if any(p.account_id == dr for p in predict_counterparts(logic_map, cr, "credit", top_k=k)):
                    hits_credit += 1

            random_rate = min(1.0, k / n_accounts)
            n = len(edges) or 1
            for side, hits in (("debit", hits_debit), ("credit", hits_credit)):
                summaries.append(
                    {
                        "metric": f"predict_hit@{k}_from_{side}",
                        "cohort": cohort,
                        "n": len(edges),
                        "hit_rate": hits / n,
                        "random_baseline": random_rate,
                        "above_random": bool(edges) and (hits / n) > random_rate,
                    }
                )
    return summaries


def evaluate_anomalies(
    anomaly_rows,
    *,
    expected_signals: list[tuple[str, str, str]],
) -> dict:
    """expected_signals: list of (signal, debit_id, credit_id)."""
    found = {
        (r.signal, r.debit_account_id, r.credit_account_id) for r in anomaly_rows
    }
    # Also allow matching by edge ignoring signal family overlap
    found_edges = {(r.debit_account_id, r.credit_account_id) for r in anomaly_rows}

    hits = 0
    detail = []
    for signal, dr, cr in expected_signals:
        ok = (signal, dr, cr) in found or (dr, cr) in found_edges
        hits += int(ok)
        detail.append({"signal": signal, "debit": dr, "credit": cr, "recovered": ok})

    n = len(expected_signals) or 1
    return {
        "metric": "anomaly_recovery",
        "n": len(expected_signals),
        "recovered": hits,
        "recovery_rate": hits / n,
        "detail": detail,
    }


def run_verify_eval(logic_map: LogicMap, txns: list[Transaction], expected: dict[str, str]):
    results = verify_transactions(logic_map, txns, expected=expected)
    summary = evaluate_verification(results)
    return results, summary
