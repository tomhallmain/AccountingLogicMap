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

    def test_ambiguous_weight_tracks_inferred_pairings(self):
        """Edges fed only by a multi-line-both-sides journal are fully inferred."""
        accounts = _accounts("Bank", "Card", "Util", "Advert")
        clean = Transaction(
            "1",
            date(2025, 1, 1),
            [
                Line("1", date(2025, 1, 1), "Util", "debit", 100),
                Line("1", date(2025, 1, 1), "Bank", "credit", 100),
            ],
        )
        combined = Transaction(
            "2",
            date(2025, 1, 2),
            [
                Line("2", date(2025, 1, 2), "Util", "debit", 60),
                Line("2", date(2025, 1, 2), "Advert", "debit", 40),
                Line("2", date(2025, 1, 2), "Bank", "credit", 70),
                Line("2", date(2025, 1, 2), "Card", "credit", 30),
            ],
        )
        edges = aggregate_rewritten(rewrite_transactions([clean, combined]))

        util_bank = edges[EdgeKey("Util", "Bank")]
        self.assertEqual(util_bank.depth, 2)
        self.assertEqual(util_bank.pair_instances, 2)
        # 100 certain from the clean journal, 42 inferred from the combined one.
        self.assertAlmostEqual(util_bank.ambiguous_weight, 60 * 70 / 100)
        self.assertLess(util_bank.ambiguous_share, 1.0)

        advert_card = edges[EdgeKey("Advert", "Card")]
        self.assertAlmostEqual(advert_card.ambiguous_share, 1.0)

    def test_self_loop_edge_is_flagged_on_the_key(self):
        accounts = _accounts("AR", "Card", "Office")
        txn = Transaction(
            "1",
            date(2025, 1, 1),
            [
                Line("1", date(2025, 1, 1), "AR", "debit", 1200),
                Line("1", date(2025, 1, 1), "Office", "debit", 45),
                Line("1", date(2025, 1, 1), "AR", "credit", 1200),
                Line("1", date(2025, 1, 1), "Card", "credit", 45),
            ],
        )
        logic = score_map(build_logic_map(accounts, [txn]))
        by_key = {se.key: se for se in logic.scored}
        self.assertTrue(by_key[EdgeKey("AR", "AR")].is_self_loop)
        self.assertFalse(by_key[EdgeKey("Office", "Card")].is_self_loop)


if __name__ == "__main__":
    unittest.main()
