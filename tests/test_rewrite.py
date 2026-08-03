from __future__ import annotations

import unittest
from datetime import date

from alm.models import Line, Transaction
from alm.rewrite import rewrite_transaction
from alm.validate import build_transactions
from alm.models import Account


def _txn(txn_id: str, pairs: list[tuple[str, str, float]]) -> Transaction:
    lines = [
        Line(txn_id, date(2025, 1, 1), acct, side, amt)
        for acct, side, amt in pairs
    ]
    return Transaction(txn_id=txn_id, date=date(2025, 1, 1), lines=lines)


class RewriteTests(unittest.TestCase):
    def test_two_line_identity(self):
        txn = _txn("A", [("Bank", "debit", 100.0), ("Sales", "credit", 100.0)])
        edges = rewrite_transaction(txn)
        self.assertEqual(len(edges), 1)
        key, weight = edges[0]
        self.assertEqual(key.debit_account_id, "Bank")
        self.assertEqual(key.credit_account_id, "Sales")
        self.assertAlmostEqual(weight, 100.0)

    def test_two_by_two_four_edges_conserve_weight(self):
        txn = _txn(
            "B",
            [
                ("A1", "debit", 60.0),
                ("A2", "debit", 40.0),
                ("B1", "credit", 25.0),
                ("B2", "credit", 75.0),
            ],
        )
        edges = rewrite_transaction(txn)
        self.assertEqual(len(edges), 4)
        total = sum(w for _, w in edges)
        self.assertAlmostEqual(total, 100.0)
        weights = {(k.debit_account_id, k.credit_account_id): w for k, w in edges}
        self.assertAlmostEqual(weights[("A1", "B1")], 60 * 25 / 100)
        self.assertAlmostEqual(weights[("A1", "B2")], 60 * 75 / 100)
        self.assertAlmostEqual(weights[("A2", "B1")], 40 * 25 / 100)
        self.assertAlmostEqual(weights[("A2", "B2")], 40 * 75 / 100)

    def test_reject_unbalanced_in_validate(self):
        accounts = {
            "Bank": Account("Bank", "Bank", "Bank"),
            "Sales": Account("Sales", "Sales", "Income"),
        }
        lines = [
            Line("U1", date(2025, 1, 1), "Bank", "debit", 100.0),
            Line("U1", date(2025, 1, 1), "Sales", "credit", 40.0),
        ]
        txns, errors = build_transactions(lines, accounts)
        self.assertEqual(txns, [])
        self.assertTrue(any("unbalanced" in e.message for e in errors))


if __name__ == "__main__":
    unittest.main()
