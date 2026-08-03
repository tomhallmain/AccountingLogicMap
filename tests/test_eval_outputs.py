"""Eval artifact contents — the metrics must survive the write to TSV.

Regression cover for two defects the original eval could not surface:
  * heterogeneous metric rows silently losing every column the first row lacked
  * the spec §11.2 "frequent edges (depth >= 3)" cohort never being computed
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.eval import evaluate_prediction
from alm.io_tsv import load_accounts, load_lines, write_eval_summary
from alm.models import PREDICT_FREQUENT_DEPTH, EdgeKey
from alm.score import score_map
from alm.validate import build_transactions

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class EvalSummaryWriterTests(unittest.TestCase):
    def test_union_of_keys_across_metric_families(self):
        rows = [
            {"metric": "verify_labeled", "n": 7, "strict_match_rate": 1.0},
            {"metric": "predict_hit@5_from_debit", "n": 8, "hit_rate": 0.75},
            {"metric": "anomaly_recovery", "n": 3, "recovery_rate": 1.0},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eval_summary.tsv"
            write_eval_summary(path, rows)
            with path.open(newline="", encoding="utf-8") as f:
                out = list(csv.DictReader(f, delimiter="\t"))

        self.assertEqual(
            list(out[0].keys()),
            ["metric", "n", "strict_match_rate", "hit_rate", "recovery_rate"],
        )
        # Every value a row supplied must round-trip, not just the first row's.
        self.assertEqual(out[1]["hit_rate"], "0.75")
        self.assertEqual(out[2]["recovery_rate"], "1.0")

    def test_empty_rows_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "eval_summary.tsv"
            write_eval_summary(path, [])
            self.assertFalse(path.exists())


class PredictCohortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        txns, errors = build_transactions(load_lines(SAMPLE / "transactions.tsv"), accounts)
        assert not errors, errors
        cls.map = score_map(build_logic_map(accounts, txns, window_label="baseline"))

    def test_reports_all_and_frequent_cohorts(self):
        holdout = [
            ("1000 Bank", "4000 Vehicle Sales"),  # depth 8
            ("6100 Fuel", "2100 Card"),           # depth 4
            ("2000 AP", "1000 Bank"),             # depth 1 — below the bar
            ("6400 Office", "9999 Nonexistent"),  # depth 0 — not in map
        ]
        rows = evaluate_prediction(self.map, holdout, ks=(5,))
        cohorts = {r["cohort"] for r in rows}
        self.assertEqual(cohorts, {"all", "frequent"})

        by = {(r["metric"], r["cohort"]): r for r in rows}
        self.assertEqual(by[("predict_hit@5_from_debit", "all")]["n"], 4)
        # Only the two edges at/above PREDICT_FREQUENT_DEPTH qualify.
        self.assertEqual(by[("predict_hit@5_from_debit", "frequent")]["n"], 2)
        self.assertEqual(by[("predict_hit@5_from_debit", "frequent")]["hit_rate"], 1.0)

    def test_frequent_cohort_honours_the_depth_constant(self):
        deep = [
            (k.debit_account_id, k.credit_account_id)
            for k, s in self.map.edges.items()
            if s.depth >= PREDICT_FREQUENT_DEPTH
        ]
        rows = evaluate_prediction(self.map, deep, ks=(5,))
        frequent = [r for r in rows if r["cohort"] == "frequent"]
        self.assertTrue(frequent)
        for r in frequent:
            self.assertEqual(r["n"], len(deep))

    def test_empty_frequent_cohort_is_not_above_random(self):
        rows = evaluate_prediction(self.map, [("2000 AP", "1000 Bank")], ks=(5,))
        frequent = [r for r in rows if r["cohort"] == "frequent"]
        for r in frequent:
            self.assertEqual(r["n"], 0)
            self.assertFalse(r["above_random"])

    def test_sample_holdout_is_in_window_by_design(self):
        """`data/sample/holdout.tsv` is drawn from the baseline's own window.

        It exercises the eval plumbing on the small fixture; it does not measure
        generalisation. The held-out split lives in `data/history/` and is
        covered by `test_periods.HeldOutPredictionTests`.
        """
        from alm.io_tsv import load_holdout_edges

        holdout = load_holdout_edges(SAMPLE / "holdout.tsv")
        in_map = [e for e in holdout if EdgeKey(*e) in self.map.edges]
        self.assertEqual(len(in_map), len(holdout))


if __name__ == "__main__":
    unittest.main()
