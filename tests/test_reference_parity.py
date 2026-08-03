"""Parity against the reference entity.

`data/reference/` carries expected results computed independently of this
implementation, so they are the contract for the normed blend and the
conditional probabilities. Without this, nothing pins the scoring chain and a
wrong denominator can pass every other test.

Fixture: data/reference/README.md
"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from alm.aggregate import logic_map_from_edge_stats, map_globals
from alm.io_tsv import load_accounts
from alm.models import EdgeKey, EdgeStat
from alm.predict import predict_counterparts
from alm.score import score_map

REFERENCE = Path(__file__).resolve().parents[1] / "data" / "reference"

EXPECTED_TOTAL_WEIGHT = 6007237.44
EXPECTED_TOTAL_DEPTH = 2241
EXPECTED_TOTAL_MEAN_WEIGHT = 1453364.406  # stored to 3dp


class ReferenceParityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with (REFERENCE / "reference_edges.tsv").open(newline="", encoding="utf-8") as f:
            cls.rows = list(csv.DictReader(f, delimiter="\t"))
        accounts = load_accounts(REFERENCE / "reference_accounts.tsv")
        edges: dict[EdgeKey, EdgeStat] = {}
        for r in cls.rows:
            key = EdgeKey(r["debit_account_id"], r["credit_account_id"])
            edges[key] = EdgeStat(
                key=key, weight_sum=float(r["weight_sum"]), depth=int(r["depth"])
            )
        cls.edges = edges
        cls.map = score_map(
            logic_map_from_edge_stats(accounts, edges, window_label="reference")
        )

    def test_fixture_is_the_full_edge_list(self):
        self.assertEqual(len(self.rows), 190)
        self.assertEqual(len(self.edges), 190, "duplicate edge keys would collapse rows")

    def test_globals_match_reference(self):
        total_weight, total_depth, total_mean_weight = map_globals(self.edges)
        self.assertAlmostEqual(total_weight, EXPECTED_TOTAL_WEIGHT, places=2)
        self.assertEqual(total_depth, EXPECTED_TOTAL_DEPTH)
        self.assertAlmostEqual(total_mean_weight, EXPECTED_TOTAL_MEAN_WEIGHT, places=2)

    def test_total_mean_weight_is_not_the_global_mean(self):
        """Guard against reintroducing the wrong blend denominator.

        total_weight / total_depth is ~2680 on this data; the correct denominator
        is ~1.45e6. Using the former leaves the third blend term ~542x too large,
        which collapses the ranking into mean-edge-size.
        """
        _, _, total_mean_weight = map_globals(self.edges)
        global_mean = EXPECTED_TOTAL_WEIGHT / EXPECTED_TOTAL_DEPTH
        self.assertGreater(total_mean_weight / global_mean, 500)

    def test_normed_blend_matches_reference(self):
        scored = {se.key: se for se in self.map.scored}
        worst = 0.0
        for r in self.rows:
            key = EdgeKey(r["debit_account_id"], r["credit_account_id"])
            worst = max(worst, abs(scored[key].norm - float(r["expected_norm"])))
        self.assertLess(worst, 1e-9, f"max deviation from expected norm = {worst}")

    def test_norm_is_a_share_not_a_ratio(self):
        """Each blend term is a share summing to 1, so norm must be <= 1."""
        for se in self.map.scored:
            self.assertLessEqual(se.norm, 1.0, f"{se.key.label()} norm={se.norm}")
        self.assertAlmostEqual(sum(se.norm for se in self.map.scored), 1.0, places=6)

    def test_top_edge_is_the_core_sales_edge(self):
        """Bank <- Income should lead the spectrum on these books.

        Under the wrong denominator a single depth-1 cleanup edge took this slot.
        """
        top = self.map.scored[0].key
        self.assertEqual(top.debit_account_id, "1001 Bank 1")
        self.assertEqual(top.credit_account_id, "4001 Income 1")

    def test_predict_matches_reference_probabilities(self):
        """`predict` reproduces the expected conditional probabilities.

        Exact on all 190 edges, though neither the concept doc nor the spec says
        so. Pinned here so a refactor of predict cannot quietly break parity.
        """
        for r in self.rows:
            dr, cr = r["debit_account_id"], r["credit_account_id"]
            from_debit = [
                p
                for p in predict_counterparts(self.map, dr, "debit", top_k=999)
                if p.account_id == cr
            ]
            from_credit = [
                p
                for p in predict_counterparts(self.map, cr, "credit", top_k=999)
                if p.account_id == dr
            ]
            self.assertTrue(from_debit and from_credit, f"{dr} | {cr} not reachable")
            self.assertAlmostEqual(
                from_debit[0].probability, float(r["expected_p_from_debit"]), places=3
            )
            self.assertAlmostEqual(
                from_credit[0].probability, float(r["expected_p_from_credit"]), places=3
            )


if __name__ == "__main__":
    unittest.main()
