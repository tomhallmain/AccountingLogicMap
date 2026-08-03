from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.io_tsv import load_accounts, load_lines
from alm.models import Line, Transaction
from alm.predict import predict_counterparts
from alm.score import score_map
from alm.validate import build_transactions
from alm.verify import verify_transaction

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class VerifyPredictTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        lines = load_lines(SAMPLE / "transactions.tsv")
        txns, errors = build_transactions(lines, accounts)
        assert not errors, errors
        cls.map = score_map(build_logic_map(accounts, txns, window_label="baseline"))

    def test_known_edge_passes(self):
        txn = Transaction(
            "P1",
            date(2025, 4, 1),
            [
                Line("P1", date(2025, 4, 1), "1000 Bank", "debit", 1000),
                Line("P1", date(2025, 4, 1), "4000 Vehicle Sales", "credit", 1000),
            ],
        )
        result = verify_transaction(self.map, txn)
        self.assertEqual(result.verdict, "pass")

    def test_nonsense_fails(self):
        txn = Transaction(
            "F1",
            date(2025, 4, 1),
            [
                Line("F1", date(2025, 4, 1), "6000 Rent", "debit", 100),
                Line("F1", date(2025, 4, 1), "6200 Advertising", "credit", 100),
            ],
        )
        result = verify_transaction(self.map, txn)
        self.assertEqual(result.verdict, "fail")

    def test_unbalanced_fails(self):
        txn = Transaction(
            "U1",
            date(2025, 4, 1),
            [
                Line("U1", date(2025, 4, 1), "1000 Bank", "debit", 100),
                Line("U1", date(2025, 4, 1), "4000 Vehicle Sales", "credit", 40),
            ],
        )
        result = verify_transaction(self.map, txn)
        self.assertEqual(result.verdict, "fail")

    def test_predict_contains_counterpart(self):
        rows = predict_counterparts(self.map, "1000 Bank", "debit", top_k=5)
        ids = [r.account_id for r in rows]
        self.assertIn("4000 Vehicle Sales", ids)


if __name__ == "__main__":
    unittest.main()
