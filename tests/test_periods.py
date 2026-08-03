"""Period slicing and the forward expectation (concept §7).

Also covers the two things periods make possible: windowed builds, and a
prediction holdout drawn from transactions the map never saw.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.eval import evaluate_prediction
from alm.io_tsv import load_accounts, load_holdout_edges, load_lines
from alm.models import DEFAULT_BASELINE_PERIODS, EdgeKey
from alm.periods import (
    filter_lines,
    forward_expectation,
    period_activity,
    period_key,
)
from alm.score import score_map
from alm.validate import build_transactions

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "history"
OPEN_MONTH_START = date(2025, 1, 1)


class PeriodKeyTests(unittest.TestCase):
    def test_keys_sort_chronologically_as_strings(self):
        days = [date(2023, 2, 5), date(2023, 11, 30), date(2024, 1, 1)]
        for gran in ("month", "quarter", "year"):
            keys = [period_key(d, gran) for d in days]
            self.assertEqual(keys, sorted(keys), msg=gran)

    def test_granularity_boundaries(self):
        self.assertEqual(period_key(date(2024, 3, 31), "month"), "2024-03")
        self.assertEqual(period_key(date(2024, 3, 31), "quarter"), "2024-Q1")
        self.assertEqual(period_key(date(2024, 4, 1), "quarter"), "2024-Q2")
        self.assertEqual(period_key(date(2024, 12, 31), "year"), "2024")

    def test_unknown_granularity_rejected(self):
        with self.assertRaises(ValueError):
            period_key(date(2024, 1, 1), "fortnight")


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.accounts = load_accounts(HISTORY / "accounts.tsv")
        cls.lines = load_lines(HISTORY / "transactions.tsv")

    def test_bounds_are_inclusive(self):
        kept = filter_lines(self.lines, start=date(2024, 6, 1), end=date(2024, 6, 30))
        self.assertTrue(kept)
        self.assertTrue(all(ln.date.month == 6 and ln.date.year == 2024 for ln in kept))

    def test_window_excludes_the_open_month_from_the_baseline(self):
        closed = filter_lines(self.lines, end=date(2024, 12, 31))
        self.assertLess(len(closed), len(self.lines))
        txns, errors = build_transactions(closed, self.accounts)
        self.assertEqual(errors, [], "a window must not split a journal")
        stats = period_activity(txns)
        self.assertEqual(stats[-1].period, "2024-12")
        self.assertNotIn("2025-01", [s.period for s in stats])

    def test_period_weights_sum_to_map_total(self):
        txns, _ = build_transactions(self.lines, self.accounts)
        logic_map = build_logic_map(self.accounts, txns)
        stats = period_activity(txns)
        self.assertAlmostEqual(
            sum(s.weight for s in stats), logic_map.total_weight, places=4
        )


class ForwardExpectationTests(unittest.TestCase):
    def _stats(self, weights):
        txns = []
        accounts = load_accounts(HISTORY / "accounts.tsv")
        del accounts  # only the shape matters here
        from alm.models import Line, Transaction

        for i, w in enumerate(weights):
            d = date(2024, i + 1, 15)
            txns.append(
                Transaction(
                    f"T{i}",
                    d,
                    [
                        Line(f"T{i}", d, "1000 Bank", "debit", w),
                        Line(f"T{i}", d, "4000 Vehicle Sales", "credit", w),
                    ],
                )
            )
        return period_activity(txns)

    def test_projection_is_the_mean_of_trailing_closed_periods(self):
        stats = self._stats([100.0, 200.0, 300.0, 900.0])
        fx = forward_expectation(stats, baseline_periods=3)
        self.assertEqual(fx.open_period, "2024-04")
        self.assertEqual(fx.baseline_periods, ["2024-01", "2024-02", "2024-03"])
        self.assertAlmostEqual(fx.expected_weight, 200.0)
        self.assertAlmostEqual(fx.actual_weight, 900.0)
        self.assertAlmostEqual(fx.weight_variance, 700.0)
        self.assertAlmostEqual(fx.weight_variance_pct, 3.5)

    def test_baseline_window_is_capped_not_padded(self):
        stats = self._stats([100.0, 200.0, 300.0])
        fx = forward_expectation(stats, baseline_periods=DEFAULT_BASELINE_PERIODS)
        self.assertEqual(len(fx.baseline_periods), 2, "only 2 closed periods exist")
        self.assertAlmostEqual(fx.expected_weight, 150.0)

    def test_needs_two_periods(self):
        self.assertIsNone(forward_expectation(self._stats([100.0])))
        self.assertIsNone(forward_expectation([]))


class HeldOutPredictionTests(unittest.TestCase):
    """The holdout is drawn from a month the map is built to exclude."""

    @classmethod
    def setUpClass(cls):
        accounts = load_accounts(HISTORY / "accounts.tsv")
        lines = load_lines(HISTORY / "transactions.tsv")
        closed = filter_lines(lines, end=date(2024, 12, 31))
        txns, errors = build_transactions(closed, accounts)
        assert not errors, errors
        cls.map = score_map(build_logic_map(accounts, txns, window_label="closed"))
        cls.holdout = load_holdout_edges(HISTORY / "holdout.tsv")
        cls.open_lines = filter_lines(lines, start=OPEN_MONTH_START)

    def test_holdout_comes_from_transactions_outside_the_map(self):
        map_txn_ids = set()
        for ln in filter_lines(
            load_lines(HISTORY / "transactions.tsv"), end=date(2024, 12, 31)
        ):
            map_txn_ids.add(ln.txn_id)
        open_txn_ids = {ln.txn_id for ln in self.open_lines}
        self.assertTrue(open_txn_ids)
        self.assertFalse(map_txn_ids & open_txn_ids)

    def test_holdout_matches_the_open_month_edges(self):
        from alm.rewrite import rewrite_transactions

        accounts = load_accounts(HISTORY / "accounts.tsv")
        txns, _ = build_transactions(self.open_lines, accounts)
        actual = {
            (k.debit_account_id, k.credit_account_id)
            for _, k, _, _ in rewrite_transactions(txns)
        }
        self.assertEqual(set(self.holdout), actual)

    def test_prediction_beats_random_on_unseen_transactions(self):
        rows = evaluate_prediction(self.map, self.holdout, ks=(5,))
        for r in rows:
            self.assertTrue(
                r["above_random"],
                msg=f"{r['metric']} [{r['cohort']}] {r['hit_rate']} vs {r['random_baseline']}",
            )
            self.assertGreaterEqual(r["hit_rate"], 0.75)

    def test_recurring_edge_types_are_not_leakage(self):
        """A stable business repeats its edges, so overlap is expected.

        What makes this a real holdout is that the *transactions* were excluded,
        which `test_holdout_comes_from_transactions_outside_the_map` asserts.
        """
        in_map = [e for e in self.holdout if EdgeKey(*e) in self.map.edges]
        self.assertEqual(len(in_map), len(self.holdout))


if __name__ == "__main__":
    unittest.main()
