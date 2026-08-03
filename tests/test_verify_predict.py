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

    def test_negative_line_weight_fails_before_rewrite(self):
        """Axiom: weights are stored positive; sign never encodes direction.

        The transaction balances, so the balance check alone lets it through —
        and the rewrite would then emit a negative edge weight.
        """
        txn = Transaction(
            "N1",
            date(2025, 4, 1),
            [
                Line("N1", date(2025, 4, 1), "1000 Bank", "debit", 10000),
                Line("N1", date(2025, 4, 1), "6200 Advertising", "debit", -9000),
                Line("N1", date(2025, 4, 1), "4000 Vehicle Sales", "credit", 1000),
            ],
        )
        result = verify_transaction(self.map, txn)
        self.assertEqual(result.verdict, "fail")
        self.assertIn("non-positive line weight", result.reasons[0])
        self.assertEqual(result.findings, [], "must not rewrite an invalid transaction")

    def test_self_transfer_fails_regardless_of_account_type(self):
        """Same account on both sides of a 2-line posting moves nothing.

        Bank->Bank is a *common* type pair (transfer between two bank accounts),
        so the type table alone would wave this through.
        """
        for account in ("1000 Bank", "4000 Vehicle Sales"):
            with self.subTest(account=account):
                txn = Transaction(
                    "SELF",
                    date(2025, 4, 1),
                    [
                        Line("SELF", date(2025, 4, 1), account, "debit", 500),
                        Line("SELF", date(2025, 4, 1), account, "credit", 500),
                    ],
                )
                result = verify_transaction(self.map, txn)
                self.assertEqual(result.verdict, "fail")
                self.assertIn("moves no value", " ".join(result.reasons))

    def test_self_loop_inside_a_journal_does_not_vote(self):
        """The (a,a) edge is a rewrite artifact, so it must not sway the verdict.

        Every other edge here is known-good, so the transaction should pass.
        """
        txn = Transaction(
            "MIX",
            date(2025, 4, 1),
            [
                Line("MIX", date(2025, 4, 1), "1000 Bank", "debit", 5000),
                Line("MIX", date(2025, 4, 1), "1100 AR", "debit", 400),
                Line("MIX", date(2025, 4, 1), "4000 Vehicle Sales", "credit", 5000),
                Line("MIX", date(2025, 4, 1), "1100 AR", "credit", 400),
            ],
        )
        result = verify_transaction(self.map, txn)
        artifacts = [f for f in result.findings if f.key.is_self_loop]
        self.assertEqual(len(artifacts), 1)
        self.assertIn("artifact", artifacts[0].note)
        self.assertEqual(result.verdict, "pass")

    def test_predict_contains_counterpart(self):
        rows = predict_counterparts(self.map, "1000 Bank", "debit", top_k=5)
        ids = [r.account_id for r in rows]
        self.assertIn("4000 Vehicle Sales", ids)


if __name__ == "__main__":
    unittest.main()
