from __future__ import annotations

import unittest
from datetime import date

from alm.aggregate import aggregate_rewritten, build_logic_map
from alm.models import Account, EdgeKey, Line, Transaction
from alm.rewrite import rewrite_transactions
from alm.score import score_map


def _accounts(*ids: str) -> dict[str, Account]:
    return {i: Account(i, i, "Expense" if i.startswith("E") else "Bank") for i in ids}


class AggregateTests(unittest.TestCase):
    def test_collapse_sums_and_depth(self):
        accounts = _accounts("Bank", "Sales", "Rent")
        txns = [
            Transaction(
                "1",
                date(2025, 1, 1),
                [
                    Line("1", date(2025, 1, 1), "Bank", "debit", 100),
                    Line("1", date(2025, 1, 1), "Sales", "credit", 100),
                ],
            ),
            Transaction(
                "2",
                date(2025, 1, 2),
                [
                    Line("2", date(2025, 1, 2), "Bank", "debit", 50),
                    Line("2", date(2025, 1, 2), "Sales", "credit", 50),
                ],
            ),
            Transaction(
                "3",
                date(2025, 1, 3),
                [
                    Line("3", date(2025, 1, 3), "Rent", "debit", 10),
                    Line("3", date(2025, 1, 3), "Bank", "credit", 10),
                ],
            ),
        ]
        rewritten = rewrite_transactions(txns)
        edges = aggregate_rewritten(rewritten)
        sales = edges[EdgeKey("Bank", "Sales")]
        self.assertAlmostEqual(sales.weight_sum, 150.0)
        self.assertEqual(sales.depth, 2)

        logic = build_logic_map(accounts, txns)
        score_map(logic)
        self.assertEqual(logic.scored[0].key, EdgeKey("Bank", "Sales"))
        self.assertGreater(logic.scored[0].norm, logic.scored[-1].norm)


if __name__ == "__main__":
    unittest.main()
