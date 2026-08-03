from __future__ import annotations

import unittest
from datetime import date

from alm.models import Line, Transaction
from alm.rewrite import has_ambiguous_pairing, rewrite_transaction
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

    def test_self_loop_edge_is_emitted_and_conserves_weight(self):
        """An account on both sides produces an (a, a) edge.

        It carries no value movement, but dropping it would break conservation,
        so the rewrite keeps it and downstream code labels it instead.
        """
        txn = _txn(
            "S",
            [
                ("AR", "debit", 1200.0),
                ("Office", "debit", 45.0),
                ("AR", "credit", 1200.0),
                ("Card", "credit", 45.0),
            ],
        )
        edges = rewrite_transaction(txn)
        self.assertAlmostEqual(sum(w for _, w in edges), 1245.0)
        self_loops = [(k, w) for k, w in edges if k.is_self_loop]
        self.assertEqual(len(self_loops), 1)
        self.assertEqual(self_loops[0][0].debit_account_id, "AR")
        self.assertAlmostEqual(self_loops[0][1], 1200 * 1200 / 1245)

    def test_pairing_is_ambiguous_only_when_both_sides_are_multi_line(self):
        one_to_one = _txn("A", [("Bank", "debit", 100.0), ("Sales", "credit", 100.0)])
        many_to_one = _txn(
            "B",
            [
                ("Util", "debit", 60.0),
                ("Advert", "debit", 40.0),
                ("Bank", "credit", 100.0),
            ],
        )
        many_to_many = _txn(
            "C",
            [
                ("Util", "debit", 60.0),
                ("Advert", "debit", 40.0),
                ("Bank", "credit", 70.0),
                ("Card", "credit", 30.0),
            ],
        )
        self.assertFalse(has_ambiguous_pairing(one_to_one))
        # (n,1) apportions exactly: each debit pairs with the only credit.
        self.assertFalse(has_ambiguous_pairing(many_to_one))
        weights = {k.label(): w for k, w in rewrite_transaction(many_to_one)}
        self.assertAlmostEqual(weights["Util | Bank"], 60.0)
        self.assertAlmostEqual(weights["Advert | Bank"], 40.0)
        # Only here can the product invent a pair that never happened.
        self.assertTrue(has_ambiguous_pairing(many_to_many))

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
