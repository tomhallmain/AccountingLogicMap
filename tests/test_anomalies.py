from __future__ import annotations

import unittest
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.anomalies import compare_maps
from alm.eval import evaluate_anomalies
from alm.io_tsv import load_accounts, load_lines
from alm.models import MISSING_EDGE_MIN_SHARE, RANK_SHIFT_MIN_DELTA_SHARE
from alm.score import score_map
from alm.validate import build_transactions

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class AnomalyTests(unittest.TestCase):
    def _maps(self):
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        base_txns, err_b = build_transactions(load_lines(SAMPLE / "transactions.tsv"), accounts)
        open_txns, err_o = build_transactions(load_lines(SAMPLE / "transactions_open.tsv"), accounts)
        self.assertEqual(err_b, [])
        self.assertEqual(err_o, [])
        return (
            score_map(build_logic_map(accounts, base_txns, window_label="baseline")),
            score_map(build_logic_map(accounts, open_txns, window_label="open")),
        )

    def test_injected_signals_recovered(self):
        baseline, open_map = self._maps()
        rows = compare_maps(baseline, open_map, top_k=25)

        expected = [
            ("missing_edge", "1000 Bank", "4000 Vehicle Sales"),
            ("new_edge", "1200 Clearing", "1000 Bank"),
            ("new_edge", "1000 Bank", "2500 New Floor Plan"),
        ]
        summary = evaluate_anomalies(rows, expected_signals=expected)
        self.assertEqual(summary["recovered"], 3, msg=summary)

    def test_qualifiers_do_not_flood_a_small_map(self):
        """`missing_edge` must mean "a top edge vanished", not "any edge did".

        A fixed top-N larger than the map makes every baseline edge qualify.
        """
        baseline, open_map = self._maps()
        rows = compare_maps(baseline, open_map, top_k=25)

        missing = [r for r in rows if "missing_edge" in r.signals]
        self.assertLessEqual(len(missing), max(1, round(len(baseline.scored) * 0.25)))
        for r in missing:
            self.assertGreaterEqual(r.baseline_share_w, MISSING_EDGE_MIN_SHARE)

    def test_rank_shift_needs_a_material_weight_move(self):
        """Rank churn caused by the open map simply having fewer edges is not a signal."""
        baseline, open_map = self._maps()
        rows = compare_maps(baseline, open_map, top_k=25)
        for r in rows:
            if "rank_shift" in r.signals:
                self.assertGreaterEqual(
                    abs(r.delta_share_w), RANK_SHIFT_MIN_DELTA_SHARE, msg=r
                )

    def test_one_row_per_edge_even_with_several_signals(self):
        """A multi-signal edge reports once; it must not eat several top-K slots."""
        baseline, open_map = self._maps()
        rows = compare_maps(baseline, open_map, top_k=25)

        keys = [(r.debit_account_id, r.credit_account_id) for r in rows]
        self.assertEqual(len(keys), len(set(keys)))

        clearing = [r for r in rows if r.debit_account_id == "1200 Clearing"]
        self.assertEqual(len(clearing), 1)
        self.assertEqual(set(clearing[0].signals), {"new_edge", "clearing_surge"})


if __name__ == "__main__":
    unittest.main()
