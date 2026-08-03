"""Excel edge-list parsing, exercised without openpyxl.

`load_excel_reference` needs the third-party reader, but everything that decides
what a row *means* — column resolution, coercion, skipping, accumulation — is pure
and takes row tuples. These tests cover that half, so the loader is not wholly
untested in environments where openpyxl is unavailable.
"""

from __future__ import annotations

import unittest

from alm.io_excel import (
    FALLBACK_EDGE_COLUMNS,
    parse_account_rows,
    parse_edge_rows,
    resolve_edge_columns,
)
from alm.models import EdgeKey


class ResolveEdgeColumnsTests(unittest.TestCase):
    def test_resolves_from_a_descriptive_header(self):
        header = (
            "row",
            "Re-Split Debit Node",
            "Re-Split Credit Node",
            "Edge Sum",
            "Edge Transaction Depth",
        )
        self.assertEqual(
            resolve_edge_columns(header),
            {"debit": 1, "credit": 2, "weight": 3, "depth": 4},
        )

    def test_resolves_from_export_style_headers_at_other_offsets(self):
        header = ("debit_account_id", "credit_account_id", "weight_sum", "depth")
        self.assertEqual(
            resolve_edge_columns(header),
            {"debit": 0, "credit": 1, "weight": 2, "depth": 3},
        )

    def test_header_matching_is_case_and_space_insensitive(self):
        header = ("", "  DEBIT   node ", "Credit Node", "EDGE   SUM", "Depth")
        self.assertEqual(
            resolve_edge_columns(header),
            {"debit": 1, "credit": 2, "weight": 3, "depth": 4},
        )

    def test_falls_back_when_the_header_names_nothing(self):
        self.assertEqual(resolve_edge_columns(("", "", "", "", "")), FALLBACK_EDGE_COLUMNS)

    def test_falls_back_when_the_header_is_incomplete(self):
        # Depth is unnamed, so the whole positional layout is used rather than a
        # half-resolved mapping that would silently read the wrong column.
        header = ("row", "Debit Node", "Credit Node", "Edge Sum", "")
        self.assertEqual(resolve_edge_columns(header), FALLBACK_EDGE_COLUMNS)

    def test_falls_back_when_there_is_no_header(self):
        self.assertEqual(resolve_edge_columns(None), FALLBACK_EDGE_COLUMNS)

    def test_a_column_is_never_claimed_twice(self):
        # "credit" appears in both labels; the first is taken by debit-matching
        # only if it matches debit, so each field lands on a distinct column.
        header = ("x", "Debit Node", "Credit Node", "Edge Sum", "Depth")
        resolved = resolve_edge_columns(header)
        self.assertEqual(len(set(resolved.values())), 4)


class ParseEdgeRowsTests(unittest.TestCase):
    cols = FALLBACK_EDGE_COLUMNS

    def parse(self, rows, accounts=None):
        return parse_edge_rows(rows, self.cols, accounts if accounts is not None else {})

    def test_reads_endpoints_weight_and_depth(self):
        edges = self.parse([(None, "Bank", "Sales", 100.0, 3)])
        stat = edges[EdgeKey("Bank", "Sales")]
        self.assertAlmostEqual(stat.weight_sum, 100.0)
        self.assertEqual(stat.depth, 3)
        self.assertEqual(stat.pair_instances, 3)

    def test_admits_accounts_seen_only_on_the_edge_sheet(self):
        accounts = {}
        self.parse([(None, "Bank", "Sales", 100.0, 1)], accounts)
        self.assertEqual(set(accounts), {"Bank", "Sales"})
        self.assertEqual(accounts["Bank"].account_type, "Unknown")

    def test_does_not_overwrite_a_known_account_type(self):
        accounts = parse_account_rows([("Bank", "Bank")])
        self.parse([(None, "Bank", "Sales", 100.0, 1)], accounts)
        self.assertEqual(accounts["Bank"].account_type, "Bank")

    def test_repeated_keys_accumulate(self):
        edges = self.parse(
            [
                (None, "Bank", "Sales", 100.0, 2),
                (None, "Bank", "Sales", 50.0, 1),
            ]
        )
        stat = edges[EdgeKey("Bank", "Sales")]
        self.assertAlmostEqual(stat.weight_sum, 150.0)
        self.assertEqual(stat.depth, 3)

    def test_skips_rows_that_carry_no_edge(self):
        edges = self.parse(
            [
                (),
                None,
                (None, None, "Sales", 100.0, 1),      # no debit endpoint
                (None, "Bank", "   ", 100.0, 1),      # blank credit endpoint
                (None, "Bank", "Sales", 0.0, 1),      # zero weight
                (None, "Bank", "Sales", -5.0, 1),     # negative weight
                (None, "Bank", "Sales", 100.0, 0),    # zero depth
                (None, "Bank", "Sales"),              # short row
                (None, "Bank", "Sales", "n/a", 1),    # uncoercible weight
            ]
        )
        self.assertEqual(edges, {})

    def test_coerces_text_numerics_and_trims_endpoints(self):
        edges = self.parse([(None, "  Bank  ", "Sales\n", "100.5", "2")])
        stat = edges[EdgeKey("Bank", "Sales")]
        self.assertAlmostEqual(stat.weight_sum, 100.5)
        self.assertEqual(stat.depth, 2)

    def test_self_loop_rows_are_kept_and_flagged(self):
        edges = self.parse([(None, "Bank", "Bank", 100.0, 1)])
        (key,) = edges
        self.assertTrue(key.is_self_loop)

    def test_respects_a_resolved_column_mapping(self):
        edges = parse_edge_rows(
            [("Bank", "Sales", 100.0, 4)],
            {"debit": 0, "credit": 1, "weight": 2, "depth": 3},
            {},
        )
        self.assertEqual(edges[EdgeKey("Bank", "Sales")].depth, 4)


class ParseAccountRowsTests(unittest.TestCase):
    def test_reads_name_and_type(self):
        accounts = parse_account_rows([("1000 Bank", "Bank"), ("4000 Sales", "Income")])
        self.assertEqual(accounts["1000 Bank"].account_type, "Bank")
        self.assertEqual(accounts["4000 Sales"].name, "4000 Sales")

    def test_missing_or_blank_type_becomes_unknown(self):
        accounts = parse_account_rows([("1000 Bank",), ("4000 Sales", "  ")])
        self.assertEqual(accounts["1000 Bank"].account_type, "Unknown")
        self.assertEqual(accounts["4000 Sales"].account_type, "Unknown")

    def test_skips_rows_without_a_name(self):
        accounts = parse_account_rows([(), None, (None, "Bank"), ("   ", "Bank")])
        self.assertEqual(accounts, {})


if __name__ == "__main__":
    unittest.main()
