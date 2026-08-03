"""Minimal rewrite — splitting a journal into forced balanced subsets.

Concept §3.3. The splitter exists to remove estimation from packed journals, so
the property that matters most is the one it must *not* have: it never picks a
pairing out of several equally valid ones. Where the journal does not force a
split, averaging keeps handling it and the ambiguous share keeps recording that.
"""

from __future__ import annotations

import unittest
from datetime import date

from alm.aggregate import build_logic_map
from alm.models import SPLIT_MAX_LINES, Account, EdgeKey, Line, Transaction
from alm.rewrite import rewrite_transactions
from alm.split import split_lines, split_transaction

DAY = date(2025, 1, 15)


def accounts(*ids: str) -> dict[str, Account]:
    return {i: Account(i, i, "Bank" if i.startswith("1") else "Expense") for i in ids}


def txn(*spec: tuple[str, str, float], txn_id: str = "T1") -> Transaction:
    lines = [Line(txn_id, DAY, acct, side, amt) for acct, side, amt in spec]
    return Transaction(txn_id=txn_id, date=DAY, lines=lines)


def groups_as_sets(groups: list[list[Line]]) -> list[set[tuple[str, str, float]]]:
    return [{(ln.account_id, ln.side, ln.amount) for ln in g} for g in groups]


class ForcedSplitTests(unittest.TestCase):
    def test_unique_amounts_split_into_two_events(self):
        """The canonical packed journal: two unrelated events in one document."""
        t = txn(
            ("6000 Rent", "debit", 1000.0),
            ("6100 Fuel", "debit", 60.0),
            ("1000 Bank", "credit", 1000.0),
            ("2100 Card", "credit", 60.0),
        )
        groups = groups_as_sets(split_lines(t.lines))
        self.assertEqual(len(groups), 2)
        self.assertIn(
            {("6000 Rent", "debit", 1000.0), ("1000 Bank", "credit", 1000.0)}, groups
        )
        self.assertIn(
            {("6100 Fuel", "debit", 60.0), ("2100 Card", "credit", 60.0)}, groups
        )

    def test_three_events_all_separate(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 20.0),
            ("6200 Ads", "debit", 3.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 20.0),
            ("1100 Petty", "credit", 3.0),
        )
        self.assertEqual(len(split_lines(t.lines)), 3)

    def test_split_leaves_an_unsplittable_remainder_whole(self):
        """One clean pair plus a genuine three-line event."""
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("1000 Bank", "credit", 100.0),
            ("6100 Fuel", "debit", 50.0),
            ("2100 Card", "credit", 30.0),
            ("1100 Petty", "credit", 20.0),
        )
        groups = split_lines(t.lines)
        self.assertEqual(len(groups), 2)
        sizes = sorted(len(g) for g in groups)
        self.assertEqual(sizes, [2, 3])

    def test_nested_split_recurses_into_the_remainder(self):
        """A pair carves out first; the remainder then splits at a larger size.

        No two-line subset exists among the remaining six, so the size-3 events
        are only reachable on the recursive pass.
        """
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("1000 Bank", "credit", 100.0),
            ("6100 Fuel", "debit", 30.0),
            ("6200 Ads", "debit", 20.0),
            ("2100 Card", "credit", 50.0),
            ("6300 Wages", "debit", 40.0),
            ("2200 PAYE", "credit", 15.0),
            ("1100 Petty", "credit", 25.0),
        )
        groups = split_lines(t.lines)
        self.assertEqual(sorted(len(g) for g in groups), [2, 3, 3])
        as_sets = groups_as_sets(groups)
        self.assertIn(
            {
                ("6100 Fuel", "debit", 30.0),
                ("6200 Ads", "debit", 20.0),
                ("2100 Card", "credit", 50.0),
            },
            as_sets,
        )


class AmbiguityRefusalTests(unittest.TestCase):
    """Where several splits compete, the splitter declines to choose."""

    def test_equal_amounts_on_both_sides_are_not_split(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 100.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 100.0),
        )
        # (Rent,Bank)+(Fuel,Card) and (Rent,Card)+(Fuel,Bank) are equally valid.
        # Picking one would invent certainty the journal does not carry.
        self.assertEqual(len(split_lines(t.lines)), 1)

    def test_one_debit_matching_two_credits_is_not_split(self):
        """A single line that could settle against either of two counterparts."""
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("1000 Bank", "credit", 100.0),
            ("6100 Fuel", "debit", 70.0),
            ("6200 Ads", "debit", 30.0),
            ("2100 Card", "credit", 100.0),
        )
        # Rent balances against Bank and against Card alike, so the two candidate
        # carves overlap on Rent and neither is forced.
        self.assertEqual(len(split_lines(t.lines)), 1)

    def test_a_duplicate_counterpart_amount_blocks_the_split(self):
        t = txn(
            ("6000 Rent", "debit", 50.0),
            ("6100 Fuel", "debit", 50.0),
            ("1000 Bank", "credit", 50.0),
            ("2100 Card", "credit", 30.0),
            ("1100 Petty", "credit", 20.0),
        )
        # Either debit could be the one settling against the bank.
        self.assertEqual(len(split_lines(t.lines)), 1)

    def test_already_minimal_journals_are_untouched(self):
        two_line = txn(("6000 Rent", "debit", 100.0), ("1000 Bank", "credit", 100.0))
        self.assertEqual(split_lines(two_line.lines), [two_line.lines])

        n_to_one = txn(
            ("6000 Rent", "debit", 60.0),
            ("6100 Fuel", "debit", 40.0),
            ("1000 Bank", "credit", 100.0),
        )
        self.assertEqual(len(split_lines(n_to_one.lines)), 1)

    def test_uniform_amounts_force_nothing_at_any_width(self):
        spec = [(f"6{i:03d} Exp", "debit", 10.0) for i in range(10)]
        spec += [(f"1{i:03d} Bank", "credit", 10.0) for i in range(10)]
        t = txn(*spec)
        self.assertEqual(len(split_lines(t.lines)), 1)

    def test_journals_beyond_the_width_guard_are_left_whole(self):
        """The guard is a sanity bound on absurd input, not a working limit."""
        spec = []
        for i in range(SPLIT_MAX_LINES // 2 + 1):
            amount = round(10 + i * 7.31, 2)
            spec.append((f"6{i:04d} Exp", "debit", amount))
            spec.append((f"2{i:04d} Pay", "credit", amount))
        over = txn(*spec)
        self.assertGreater(len(over.lines), SPLIT_MAX_LINES)
        # Every event here is a clean pair, so only the width guard stops it.
        self.assertEqual(len(split_lines(over.lines)), 1)


class CatchUpEntryTests(unittest.TestCase):
    """Wide journals are the case the splitter exists for.

    A catch-up entry brings a whole period onto the books in one document, so it
    is a bundle of unrelated events by construction. Two-line events are matched
    by amount rather than enumerated, so width costs linear time, not
    exponential.
    """

    @staticmethod
    def catch_up(n_events: int) -> Transaction:
        spec = []
        for i in range(n_events):
            amount = round(10 + i * 7.31, 2)
            spec.append((f"6{i:04d} Expense", "debit", amount))
            spec.append((f"2{i:04d} Payable", "credit", amount))
        return txn(*spec, txn_id="CATCHUP")

    def test_a_wide_catch_up_entry_decomposes_completely(self):
        for n_events in (25, 100, 400):
            t = self.catch_up(n_events)
            groups = split_lines(t.lines)
            self.assertEqual(len(groups), n_events, f"{n_events} events")
            self.assertTrue(all(len(g) == 2 for g in groups))

    def test_width_costs_linear_time(self):
        """400 events must not cost anything like 16x the time of 100."""
        import time

        def elapsed(n):
            lines = self.catch_up(n).lines
            start = time.perf_counter()
            split_lines(lines)
            return time.perf_counter() - start

        elapsed(100)  # warm up
        small, large = elapsed(100), elapsed(400)
        self.assertLess(large, max(small * 12, 0.5))

    def test_an_ambiguous_cluster_does_not_block_the_clean_events(self):
        """Refusal is per subset, not per journal."""
        base = self.catch_up(40)
        spec = [(ln.account_id, ln.side, ln.amount) for ln in base.lines]
        spec += [
            ("6900 A", "debit", 500.0),
            ("6901 B", "debit", 500.0),
            ("2900 C", "credit", 500.0),
            ("2901 D", "credit", 500.0),
        ]
        groups = split_lines(txn(*spec).lines)
        # 40 clean pairs, plus the four contested lines held together.
        self.assertEqual(len(groups), 41)
        contested = [g for g in groups if len(g) == 4]
        self.assertEqual(len(contested), 1)
        self.assertEqual(
            {ln.amount for ln in contested[0]}, {500.0}
        )

    def test_events_larger_than_two_lines_are_still_found(self):
        """Three-line events have no equal-amount match, so they exercise the
        subset search rather than the pair pass."""
        spec = []
        for i in range(12):
            a = round(100 * (2**i % 97) + 0.11, 2)
            b = round(3 * (3**i % 89) + 0.07, 2)
            spec += [
                (f"6{i:04d} Expense", "debit", round(a + b, 2)),
                (f"2{i:04d} Payable", "credit", a),
                (f"2{i:04d} Tax", "credit", b),
            ]
        groups = split_lines(txn(*spec).lines)
        self.assertEqual(len(groups), 12)
        self.assertTrue(all(len(g) == 3 for g in groups))


class InvariantTests(unittest.TestCase):
    def test_every_group_balances(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 20.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 20.0),
        )
        for group in split_lines(t.lines):
            dr = sum(ln.amount for ln in group if ln.side == "debit")
            cr = sum(ln.amount for ln in group if ln.side == "credit")
            self.assertAlmostEqual(dr, cr, places=9)
            self.assertTrue(any(ln.side == "debit" for ln in group))
            self.assertTrue(any(ln.side == "credit" for ln in group))

    def test_no_line_is_lost_or_duplicated(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 20.0),
            ("6200 Ads", "debit", 3.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 23.0),
        )
        flat = [ln for g in split_lines(t.lines) for ln in g]
        self.assertEqual(len(flat), len(t.lines))
        self.assertEqual(sorted(map(id, flat)), sorted(map(id, t.lines)))

    def test_split_is_deterministic(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 20.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 20.0),
        )
        self.assertEqual(
            [groups_as_sets(split_lines(t.lines)) for _ in range(5)],
            [groups_as_sets(split_lines(t.lines))] * 5,
        )

    def test_sub_transactions_keep_the_parent_id(self):
        t = txn(
            ("6000 Rent", "debit", 100.0),
            ("6100 Fuel", "debit", 20.0),
            ("1000 Bank", "credit", 100.0),
            ("2100 Card", "credit", 20.0),
            txn_id="JE-9",
        )
        parts = split_transaction(t)
        self.assertEqual(len(parts), 2)
        for part in parts:
            self.assertEqual(part.txn_id, "JE-9")
            self.assertEqual(part.date, t.date)


class RewriteWithSplitTests(unittest.TestCase):
    packed = txn(
        ("6000 Rent", "debit", 1000.0),
        ("6100 Fuel", "debit", 60.0),
        ("1000 Bank", "credit", 1000.0),
        ("2100 Card", "credit", 60.0),
    )
    accts = accounts("6000 Rent", "6100 Fuel", "1000 Bank", "2100 Card")

    def test_averaging_emits_four_edges_and_splitting_emits_two(self):
        averaged = rewrite_transactions([self.packed])
        split = rewrite_transactions([self.packed], split=True)
        self.assertEqual(len(averaged), 4)
        self.assertEqual(len(split), 2)

    def test_weight_is_conserved_either_way(self):
        for rows in (
            rewrite_transactions([self.packed]),
            rewrite_transactions([self.packed], split=True),
        ):
            self.assertAlmostEqual(sum(w for _, _, w, _, _ in rows), 1060.0, places=6)

    def test_splitting_removes_the_cross_edges(self):
        split = {key for _, key, _, _, _ in rewrite_transactions([self.packed], split=True)}
        self.assertEqual(
            split,
            {EdgeKey("6000 Rent", "1000 Bank"), EdgeKey("6100 Fuel", "2100 Card")},
        )
        averaged = {key for _, key, _, _, _ in rewrite_transactions([self.packed])}
        self.assertIn(EdgeKey("6000 Rent", "2100 Card"), averaged)

    def test_splitting_drives_ambiguity_to_zero(self):
        averaged = build_logic_map(self.accts, [self.packed])
        split = build_logic_map(self.accts, [self.packed], split=True)
        self.assertTrue(all(s.ambiguous_share == 1.0 for s in averaged.edges.values()))
        self.assertTrue(all(s.ambiguous_share == 0.0 for s in split.edges.values()))

    def test_depth_still_counts_source_transactions_not_pieces(self):
        split = build_logic_map(self.accts, [self.packed], split=True)
        for stat in split.edges.values():
            self.assertEqual(stat.depth, 1)

    def test_map_records_the_rewrite_mode(self):
        self.assertEqual(build_logic_map(self.accts, [self.packed]).rewrite_mode, "averaging")
        self.assertEqual(
            build_logic_map(self.accts, [self.packed], split=True).rewrite_mode, "minimal"
        )

    def test_unsplittable_journals_are_unchanged_by_the_flag(self):
        simple = txn(("6000 Rent", "debit", 100.0), ("1000 Bank", "credit", 100.0))
        accts = accounts("6000 Rent", "1000 Bank")
        self.assertEqual(
            build_logic_map(accts, [simple]).edges.keys(),
            build_logic_map(accts, [simple], split=True).edges.keys(),
        )


if __name__ == "__main__":
    unittest.main()
