"""write_map_dir → load_map_dir fidelity.

Every command except `build` reads a map directory from disk, so the reader is on
the critical path for verify, predict, anomalies and eval. These tests assert that
a reloaded map carries the same numbers as the one that was written, including the
per-period mass that seasonal prediction depends on.
"""

from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import date
from pathlib import Path

from alm.aggregate import build_logic_map
from alm.io_tsv import load_accounts, load_lines, load_map_dir, write_map_dir
from alm.models import Line, LogicMap, Transaction
from alm.predict import predict_counterparts
from alm.validate import build_transactions


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
HISTORY = Path(__file__).resolve().parents[1] / "data" / "history"


def build_map(data_dir: Path, label: str) -> LogicMap:
    accounts = load_accounts(data_dir / "accounts.tsv")
    lines = load_lines(data_dir / "transactions.tsv")
    txns, errors = build_transactions(lines, accounts)
    assert not errors, errors
    return build_logic_map(accounts, txns, window_label=label)


class TestMapDirRoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.original = build_map(SAMPLE, "sample")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.map_dir = Path(cls._tmp.name) / "baseline"
        write_map_dir(cls.original, cls.map_dir)
        cls.reloaded = load_map_dir(cls.map_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_globals_survive(self) -> None:
        self.assertAlmostEqual(
            self.reloaded.total_weight, self.original.total_weight, places=4
        )
        self.assertEqual(self.reloaded.total_depth, self.original.total_depth)
        self.assertAlmostEqual(
            self.reloaded.total_mean_weight, self.original.total_mean_weight, places=4
        )

    def test_counts_and_labels_survive(self) -> None:
        self.assertEqual(self.reloaded.window_label, self.original.window_label)
        self.assertEqual(self.reloaded.txn_count, self.original.txn_count)
        self.assertEqual(self.reloaded.line_count, self.original.line_count)
        self.assertEqual(self.reloaded.granularity, self.original.granularity)
        self.assertEqual(self.reloaded.accounts.keys(), self.original.accounts.keys())

    def test_every_edge_survives_with_its_stats(self) -> None:
        self.assertEqual(set(self.reloaded.edges), set(self.original.edges))
        for key, stat in self.original.edges.items():
            got = self.reloaded.edges[key]
            self.assertAlmostEqual(got.weight_sum, stat.weight_sum, places=4, msg=str(key))
            self.assertEqual(got.depth, stat.depth, msg=str(key))
            self.assertEqual(got.pair_instances, stat.pair_instances, msg=str(key))
            self.assertAlmostEqual(
                got.ambiguous_share, stat.ambiguous_share, places=4, msg=str(key)
            )
            self.assertEqual(got.key.is_self_loop, stat.key.is_self_loop)

    def test_scored_order_and_values_survive(self) -> None:
        self.assertEqual(len(self.reloaded.scored), len(self.original.scored))
        for got, want in zip(self.reloaded.scored, self.original.scored):
            self.assertEqual(got.key, want.key)
            self.assertEqual(got.rank, want.rank)
            self.assertAlmostEqual(got.norm, want.norm, places=5)
            self.assertAlmostEqual(got.share_w, want.share_w, places=5)
            self.assertAlmostEqual(got.share_c, want.share_c, places=5)
            self.assertAlmostEqual(got.share_m, want.share_m, places=5)

    def test_predictions_are_identical_after_reload(self) -> None:
        account = self.original.scored[0].key.debit_account_id
        before = predict_counterparts(self.original, account, "debit", top_k=5)
        after = predict_counterparts(self.reloaded, account, "debit", top_k=5)
        self.assertEqual([r.account_id for r in before], [r.account_id for r in after])
        for b, a in zip(before, after):
            self.assertAlmostEqual(b.probability, a.probability, places=6)


class TestPeriodMassRoundTrip(unittest.TestCase):
    """The history ledger carries dates, so per-period mass must survive."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.original = build_map(HISTORY, "history")
        cls._tmp = tempfile.TemporaryDirectory()
        cls.map_dir = Path(cls._tmp.name) / "hist"
        write_map_dir(cls.original, cls.map_dir)
        cls.reloaded = load_map_dir(cls.map_dir)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmp.cleanup()

    def test_periods_survive(self) -> None:
        self.assertEqual(self.reloaded.periods, self.original.periods)
        self.assertTrue(self.reloaded.periods)

    def test_per_period_mass_survives(self) -> None:
        for key, stat in self.original.edges.items():
            got = self.reloaded.edges[key]
            self.assertEqual(got.period_weights.keys(), stat.period_weights.keys())
            for period, weight in stat.period_weights.items():
                self.assertAlmostEqual(got.period_weights[period], weight, places=4)
                self.assertEqual(got.period_depths[period], stat.period_depths[period])

    def test_seasonal_prediction_is_identical_after_reload(self) -> None:
        account = self.original.scored[0].key.credit_account_id
        periods = [p for p in self.original.periods if p.endswith("-01")]
        before = predict_counterparts(
            self.original, account, "credit", top_k=5, periods=periods
        )
        after = predict_counterparts(
            self.reloaded, account, "credit", top_k=5, periods=periods
        )
        self.assertEqual([r.account_id for r in before], [r.account_id for r in after])


class TestLoadMapDirFallbacks(unittest.TestCase):
    """load_map_dir derives what meta.tsv does not carry."""

    def setUp(self) -> None:
        self.original = build_map(SAMPLE, "sample")
        self._tmp = tempfile.TemporaryDirectory()
        self.map_dir = Path(self._tmp.name) / "baseline"
        write_map_dir(self.original, self.map_dir)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _blank_meta_columns(self, *columns: str) -> None:
        path = self.map_dir / "meta.tsv"
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
            fields = list(rows[0].keys())
        for row in rows:
            for column in columns:
                row[column] = ""
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_globals_derived_when_meta_omits_them(self) -> None:
        self._blank_meta_columns("total_weight", "total_depth", "total_mean_weight")
        reloaded = load_map_dir(self.map_dir)
        self.assertAlmostEqual(reloaded.total_weight, self.original.total_weight, places=4)
        self.assertEqual(reloaded.total_depth, self.original.total_depth)
        self.assertAlmostEqual(
            reloaded.total_mean_weight, self.original.total_mean_weight, places=4
        )

    def test_pair_instances_falls_back_to_depth_on_older_maps(self) -> None:
        """A map directory written before the column existed still loads."""
        path = self.map_dir / "edges.tsv"
        with path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f, delimiter="\t"))
        fields = [c for c in rows[0].keys() if c != "pair_instances"]
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fields, delimiter="\t", lineterminator="\n")
            writer.writeheader()
            writer.writerows({k: r[k] for k in fields} for r in rows)

        reloaded = load_map_dir(self.map_dir)
        for key, stat in reloaded.edges.items():
            self.assertEqual(stat.pair_instances, stat.depth, msg=str(key))

    def test_period_file_absent_falls_back_to_the_meta_endpoints(self) -> None:
        """Without per-period mass there is nothing to reconstruct the series from.

        The edges still load; `periods` degrades to the first/last labels recorded
        in meta.tsv, which is enough to report the window but not to condition a
        seasonal prediction — that needs edge_periods.tsv.
        """
        (self.map_dir / "edge_periods.tsv").unlink()
        reloaded = load_map_dir(self.map_dir)
        self.assertEqual(set(reloaded.edges), set(self.original.edges))
        self.assertEqual(
            reloaded.periods, [self.original.periods[0], self.original.periods[-1]]
        )
        self.assertTrue(all(not s.period_weights for s in reloaded.edges.values()))


class TestSyntheticRoundTrip(unittest.TestCase):
    """A hand-built 2×2 journal: pair_instances is 1 per edge, depth 1, no ambiguity loss."""

    def test_two_by_two_journal_round_trips(self) -> None:
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        ids = list(accounts)[:4]
        lines = [
            Line("T1", date(2024, 1, 5), ids[0], "debit", 60.0),
            Line("T1", date(2024, 1, 5), ids[1], "debit", 40.0),
            Line("T1", date(2024, 1, 5), ids[2], "credit", 70.0),
            Line("T1", date(2024, 1, 5), ids[3], "credit", 30.0),
        ]
        txn = Transaction(txn_id="T1", date=date(2024, 1, 5), lines=lines)
        logic_map = build_logic_map(accounts, [txn], window_label="t")

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m"
            write_map_dir(logic_map, out)
            reloaded = load_map_dir(out)

        self.assertEqual(len(reloaded.edges), 4)
        self.assertAlmostEqual(
            sum(s.weight_sum for s in reloaded.edges.values()), 100.0, places=6
        )
        for key in logic_map.edges:
            self.assertIn(key, reloaded.edges)
            self.assertAlmostEqual(reloaded.edges[key].ambiguous_share, 1.0, places=6)

    def test_repeated_pair_within_one_journal_keeps_pair_instances(self) -> None:
        """pair_instances exceeds depth only when one journal emits a key twice.

        Two debit lines on the same account against one credit account do exactly
        that: depth 1, two emissions. Reconstructing pair_instances as depth on
        load — as the reader used to — would erase the distinction.
        """
        accounts = load_accounts(SAMPLE / "accounts.tsv")
        dr, cr = list(accounts)[:2]
        lines = [
            Line("T1", date(2024, 1, 5), dr, "debit", 60.0),
            Line("T1", date(2024, 1, 5), dr, "debit", 40.0),
            Line("T1", date(2024, 1, 5), cr, "credit", 100.0),
        ]
        txn = Transaction(txn_id="T1", date=date(2024, 1, 5), lines=lines)
        logic_map = build_logic_map(accounts, [txn], window_label="t")

        (key,) = list(logic_map.edges)
        self.assertEqual(logic_map.edges[key].depth, 1)
        self.assertEqual(logic_map.edges[key].pair_instances, 2)
        # One line on the credit side pins the pairing, so nothing is ambiguous.
        self.assertAlmostEqual(logic_map.edges[key].ambiguous_share, 0.0, places=6)

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "m"
            write_map_dir(logic_map, out)
            reloaded = load_map_dir(out)

        self.assertEqual(reloaded.edges[key].depth, 1)
        self.assertEqual(reloaded.edges[key].pair_instances, 2)


if __name__ == "__main__":
    unittest.main()
