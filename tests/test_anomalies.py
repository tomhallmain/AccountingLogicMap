from __future__ import annotations

import unittest
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.anomalies import compare_maps
from alm.eval import evaluate_anomalies
from alm.io_tsv import load_accounts, load_lines
from alm.score import score_map
from alm.validate import build_transactions

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class AnomalyTests(unittest.TestCase):
    def test_injected_signals_recovered(self):
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        base_lines = load_lines(SAMPLE / "transactions.tsv")
        open_lines = load_lines(SAMPLE / "transactions_open.tsv")
        base_txns, err_b = build_transactions(base_lines, accounts)
        open_txns, err_o = build_transactions(open_lines, accounts)
        self.assertEqual(err_b, [])
        self.assertEqual(err_o, [])

        baseline = score_map(build_logic_map(accounts, base_txns, window_label="baseline"))
        open_map = score_map(build_logic_map(accounts, open_txns, window_label="open"))
        rows = compare_maps(baseline, open_map, top_k=25)

        expected = [
            ("missing_edge", "1000 Bank", "4000 Vehicle Sales"),
            ("new_edge", "1200 Clearing", "1000 Bank"),
            ("new_edge", "1000 Bank", "2500 New Floor Plan"),
        ]
        summary = evaluate_anomalies(rows, expected_signals=expected)
        self.assertEqual(summary["recovered"], 3, msg=summary)


if __name__ == "__main__":
    unittest.main()
