"""Cross-entity comparison and benchmarking.

Concept §6.2. The claim under test is that two entities with no account
identifiers in common are still comparable, because account types are a shared
axis and the map is already expressed in shares. The peer fixtures exist to make
that concrete: alpha, beta and gamma share no account id, use different type
labels for the same thing, and differ in size by a factor of four.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.benchmark import (
    UNCLASSIFIED,
    base_group,
    benchmark,
    divergence,
    divergence_matrix,
    pooled,
    type_spectrum,
)
from alm.io_tsv import load_accounts, load_lines
from alm.models import Account, Line, Transaction
from alm.validate import build_transactions

PEERS = Path(__file__).resolve().parents[1] / "data" / "peers"
DAY = date(2025, 3, 4)


def peer_map(name: str):
    accounts = load_accounts(PEERS / name / "accounts.tsv")
    txns, errors = build_transactions(load_lines(PEERS / name / "transactions.tsv"), accounts)
    assert not errors, errors
    return build_logic_map(accounts, txns, window_label=name)


def peer_spectrum(name: str, level: str = "group"):
    return type_spectrum(peer_map(name), label=name, level=level)


class BaseGroupTests(unittest.TestCase):
    def test_type_vocabularies_collapse_onto_shared_groups(self):
        # The same thing under three product-specific labels.
        self.assertEqual(base_group("Expense"), "Expense")
        self.assertEqual(base_group("Expenses"), "Expense")
        self.assertEqual(base_group("Cost of Goods Sold"), "Expense")
        self.assertEqual(base_group("Bank"), "Asset")
        self.assertEqual(base_group("Accounts receivable (A/R)"), "Asset")
        self.assertEqual(base_group("Credit Card"), "Liability")
        self.assertEqual(base_group("Accounts payable (A/P)"), "Liability")

    def test_unknown_types_are_kept_not_dropped(self):
        """Dropping them would quietly change the denominators."""
        self.assertEqual(base_group("Sundry Widgets"), UNCLASSIFIED)


class TypeSpectrumTests(unittest.TestCase):
    def test_shares_form_a_distribution(self):
        spectrum = peer_spectrum("alpha")
        self.assertAlmostEqual(sum(c.weight_share for c in spectrum.cells.values()), 1.0, places=9)
        self.assertAlmostEqual(sum(c.depth_share for c in spectrum.cells.values()), 1.0, places=9)

    def test_projection_is_over_types_not_accounts(self):
        spectrum = peer_spectrum("alpha")
        entity_map = peer_map("alpha")
        self.assertLess(len(spectrum.cells), len(entity_map.edges))
        for debit, credit in spectrum.cells:
            self.assertIn(debit, {"Asset", "Liability", "Equity", "Income", "Expense"})
            self.assertIn(credit, {"Asset", "Liability", "Equity", "Income", "Expense"})

    def test_raw_type_level_is_finer_than_group_level(self):
        by_group = peer_spectrum("alpha", "group")
        by_type = peer_spectrum("alpha", "type")
        self.assertGreaterEqual(len(by_type.cells), len(by_group.cells))
        self.assertAlmostEqual(sum(c.weight_share for c in by_type.cells.values()), 1.0, places=9)

    def test_self_loops_are_excluded_before_type_reasoning(self):
        """Concept §3.3.1: a self-loop's type pair is identical by construction,
        so counting it would load the diagonal with rewrite artifacts."""
        accounts = {
            "1000": Account("1000", "Bank", "Bank"),
            "1100": Account("1100", "AR", "Accounts receivable (A/R)"),
            "4000": Account("4000", "Sales", "Income"),
        }
        # Kept apart deliberately: a receivable against itself is the only
        # source of an Asset-against-Asset pair here, so if it survived the
        # projection it would show up as a type pair of its own.
        reclass = Transaction("T1", DAY, [
            Line("T1", DAY, "1100", "debit", 100.0),
            Line("T1", DAY, "1100", "credit", 100.0),
        ])
        sale = Transaction("T2", DAY, [
            Line("T2", DAY, "1000", "debit", 50.0),
            Line("T2", DAY, "4000", "credit", 50.0),
        ])
        spectrum = type_spectrum(build_logic_map(accounts, [reclass, sale]), label="x")

        self.assertNotIn(("Asset", "Asset"), spectrum.cells)
        self.assertEqual(set(spectrum.cells), {("Asset", "Income")})
        # 100 of 150 gross weight was the artifact, and it is reported, not hidden.
        self.assertAlmostEqual(spectrum.self_loop_share, 100 / 150, places=9)
        self.assertAlmostEqual(
            sum(c.weight_share for c in spectrum.cells.values()), 1.0, places=9
        )

    def test_invalid_level_is_rejected(self):
        with self.assertRaises(ValueError):
            type_spectrum(peer_map("alpha"), level="account")


class DivergenceTests(unittest.TestCase):
    def test_an_entity_does_not_diverge_from_itself(self):
        self.assertAlmostEqual(divergence(peer_spectrum("alpha"), peer_spectrum("alpha")), 0.0)

    def test_divergence_is_symmetric_and_bounded(self):
        a, g = peer_spectrum("alpha"), peer_spectrum("gamma")
        self.assertAlmostEqual(divergence(a, g), divergence(g, a), places=12)
        self.assertGreaterEqual(divergence(a, g), 0.0)
        self.assertLessEqual(divergence(a, g), 1.0)

    def test_disjoint_entities_diverge_completely(self):
        accounts = {
            "1000": Account("1000", "Bank", "Bank"),
            "4000": Account("4000", "Sales", "Income"),
            "6000": Account("6000", "Rent", "Expense"),
            "2100": Account("2100", "Card", "Credit Card"),
        }
        sales = Transaction("A", DAY, [
            Line("A", DAY, "1000", "debit", 100.0),
            Line("A", DAY, "4000", "credit", 100.0),
        ])
        spend = Transaction("B", DAY, [
            Line("B", DAY, "6000", "debit", 100.0),
            Line("B", DAY, "2100", "credit", 100.0),
        ])
        one = type_spectrum(build_logic_map(accounts, [sales]), label="one")
        two = type_spectrum(build_logic_map(accounts, [spend]), label="two")
        self.assertAlmostEqual(divergence(one, two), 1.0, places=9)

    def test_like_entities_are_closer_than_unlike_ones(self):
        """alpha and beta run the same way; gamma funds itself differently."""
        alpha, beta, gamma = (peer_spectrum(n) for n in ("alpha", "beta", "gamma"))
        self.assertLess(divergence(alpha, beta), divergence(alpha, gamma))
        self.assertLess(divergence(alpha, beta), divergence(beta, gamma))

    def test_scale_does_not_drive_the_comparison(self):
        """beta is 2.4x alpha by weight yet sits next to it in type space."""
        alpha_map, beta_map = peer_map("alpha"), peer_map("beta")
        self.assertGreater(beta_map.total_weight, 2 * alpha_map.total_weight)
        self.assertLess(divergence(peer_spectrum("alpha"), peer_spectrum("beta")), 0.05)

    def test_no_account_identifier_is_shared_between_the_peers(self):
        """The comparison genuinely crosses charts of accounts."""
        ids = [set(peer_map(n).accounts) for n in ("alpha", "beta", "gamma")]
        self.assertEqual(ids[0] & ids[1], set())
        self.assertEqual(ids[0] & ids[2], set())
        self.assertEqual(ids[1] & ids[2], set())

    def test_matrix_covers_every_pair_closest_first(self):
        spectra = [peer_spectrum(n) for n in ("alpha", "beta", "gamma")]
        matrix = divergence_matrix(spectra)
        self.assertEqual(len(matrix), 3)
        self.assertEqual(matrix[0][:2], ("alpha", "beta"))
        self.assertEqual([d for *_, d in matrix], sorted(d for *_, d in matrix))


class PooledTests(unittest.TestCase):
    def test_group_is_a_distribution(self):
        group = pooled([peer_spectrum("alpha"), peer_spectrum("beta")])
        self.assertAlmostEqual(sum(c.weight_share for c in group.cells.values()), 1.0, places=9)

    def test_each_peer_counts_equally_regardless_of_size(self):
        alpha, beta = peer_spectrum("alpha"), peer_spectrum("beta")
        group = pooled([alpha, beta])
        for pair in group.pairs():
            self.assertAlmostEqual(
                group.share(pair), (alpha.share(pair) + beta.share(pair)) / 2, places=9
            )

    def test_empty_peer_group_is_rejected(self):
        with self.assertRaises(ValueError):
            pooled([])


class BenchmarkRowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.alpha = peer_spectrum("alpha")
        cls.beta = peer_spectrum("beta")
        cls.gamma = peer_spectrum("gamma")
        cls.rows = benchmark(cls.gamma, [cls.alpha, cls.beta])

    def test_one_row_per_pair_either_side_uses(self):
        expected = self.gamma.pairs() | self.alpha.pairs() | self.beta.pairs()
        self.assertEqual({(r.debit, r.credit) for r in self.rows}, expected)

    def test_rows_are_ordered_by_size_of_gap(self):
        gaps = [abs(r.delta) for r in self.rows]
        self.assertEqual(gaps, sorted(gaps, reverse=True))

    def test_card_funding_shows_as_the_headline_difference(self):
        """gamma settles operating costs on a card; its peers use the bank."""
        by_pair = {(r.debit, r.credit): r for r in self.rows}
        self.assertEqual(by_pair[("Expense", "Liability")].signal, "over")
        self.assertEqual(by_pair[("Expense", "Asset")].signal, "absent")
        self.assertGreater(by_pair[("Expense", "Liability")].delta, 0)
        self.assertLess(by_pair[("Expense", "Asset")].delta, 0)

    def test_absent_means_peers_do_it_and_the_subject_does_not(self):
        for row in self.rows:
            if row.signal == "absent":
                self.assertEqual(row.subject_share, 0.0)
                self.assertGreater(row.peers_present, 0)

    def test_unique_means_the_subject_does_it_alone(self):
        rows = benchmark(self.gamma, [self.alpha])
        for row in rows:
            if row.signal == "unique":
                self.assertGreater(row.subject_share, 0.0)
                self.assertEqual(row.peers_present, 0)

    def test_peer_stats_count_absent_peers_as_zero(self):
        """Averaging only over peers that use a pair would flatter the subject."""
        for row in self.rows:
            self.assertEqual(row.peers_total, 2)
            if row.peers_present < row.peers_total:
                self.assertEqual(row.peer_min, 0.0)

    def test_benchmarking_against_no_peers_is_rejected(self):
        with self.assertRaises(ValueError):
            benchmark(self.gamma, [])

    def test_an_entity_benchmarked_against_itself_is_all_in_line(self):
        for row in benchmark(self.alpha, [self.alpha]):
            self.assertEqual(row.signal, "in line")
            self.assertAlmostEqual(row.delta, 0.0, places=12)


if __name__ == "__main__":
    unittest.main()
