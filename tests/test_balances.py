"""Natural-balance quality signal, including contra inference.

The hard part is not spotting a wrong-side balance — it is not crying wolf over
contra accounts, which sit on the opposite side by construction. These tests pin
the discriminator: coverage-weighted lifetime persistence plus chart hierarchy,
never a name or a peer comparison on its own.
"""

from __future__ import annotations

import unittest
from datetime import date
from pathlib import Path

from alm.balances import (
    BALANCE_ZERO_TOLERANCE,
    infer_contra,
    natural_side,
    parent_of,
    period_balances,
    side_of,
    unnatural_balances,
)
from alm.io_tsv import load_accounts, load_lines
from alm.models import Account, Line, Transaction
from alm.validate import build_transactions

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data" / "history"


def _acct(aid, name, atype):
    return Account(account_id=aid, name=name, account_type=atype)


def _txn(i, day, legs):
    lines = [Line(f"T{i}", day, a, s, amt) for a, s, amt in legs]
    return Transaction(txn_id=f"T{i}", date=day, lines=lines)


class NaturalSideTests(unittest.TestCase):
    def test_asset_and_expense_types_are_debit(self):
        for atype in ("Bank", "Fixed Assets", "Expenses", "Cost of Goods Sold"):
            self.assertEqual(natural_side(_acct("x", "x", atype)), "debit", atype)

    def test_liability_equity_and_income_types_are_credit(self):
        for atype in ("Credit Card", "Long Term Liabilities", "Equity", "Income"):
            self.assertEqual(natural_side(_acct("x", "x", atype)), "credit", atype)

    def test_unknown_type_has_no_natural_side(self):
        self.assertIsNone(natural_side(_acct("x", "x", "Mystery")))

    def test_zero_band_is_neither_side(self):
        self.assertEqual(side_of(0.0), "zero")
        self.assertEqual(side_of(BALANCE_ZERO_TOLERANCE / 2), "zero")
        self.assertEqual(side_of(1.0), "debit")
        self.assertEqual(side_of(-1.0), "credit")


class HierarchyTests(unittest.TestCase):
    def test_parent_resolves_with_or_without_the_account_code(self):
        accounts = {
            "1500 Equipment": _acct("1500 Equipment", "Shop Equipment", "Fixed Assets"),
            "1510 Accum Depreciation": _acct(
                "1510 Accum Depreciation", "Equipment:Accumulated Depreciation", "Fixed Assets"
            ),
        }
        parent = parent_of(accounts["1510 Accum Depreciation"], accounts)
        self.assertIsNotNone(parent)
        self.assertEqual(parent.account_id, "1500 Equipment")

    def test_no_colon_means_no_parent(self):
        accounts = {"1000 Bank": _acct("1000 Bank", "Operating Bank", "Bank")}
        self.assertIsNone(parent_of(accounts["1000 Bank"], accounts))


class ContraInferenceTests(unittest.TestCase):
    def test_name_alone_does_not_make_an_account_contra(self):
        """A name is a label, not evidence about the books."""
        accounts = {"6000 Discount": _acct("6000 Discount", "Volume Discount", "Expenses")}
        closing = {"6000 Discount": {"2024-01": 500.0, "2024-02": 900.0}}
        verdict = infer_contra(accounts, closing)["6000 Discount"]
        self.assertEqual(verdict.score, 1)
        self.assertFalse(verdict.is_contra)

    def test_persistent_off_side_balance_covering_its_life_is_contra(self):
        accounts = {"1510 AD": _acct("1510 AD", "Accum Depr", "Fixed Assets")}
        closing = {"1510 AD": {f"2024-{m:02d}": -100.0 * m for m in range(1, 7)}}
        verdict = infer_contra(accounts, closing)["1510 AD"]
        self.assertTrue(verdict.is_contra)

    def test_occasional_dip_is_not_contra_even_if_never_positive(self):
        """The discriminator that matters.

        This account is flat most months and negative in a few. Every non-zero
        balance it ever held was on the 'wrong' side, so consistency alone would
        call it contra — coverage is what says otherwise.
        """
        periods = {f"2024-{m:02d}": 0.0 for m in range(1, 11)}
        periods.update({"2024-11": -400.0, "2024-12": -900.0})
        accounts = {"1200 Clearing": _acct("1200 Clearing", "Clearing", "Bank")}
        verdict = infer_contra(accounts, {"1200 Clearing": periods})["1200 Clearing"]
        self.assertFalse(verdict.is_contra, verdict.reasons)

    def test_short_history_is_not_enough_evidence(self):
        accounts = {"1510 AD": _acct("1510 AD", "Accum Depr", "Fixed Assets")}
        closing = {"1510 AD": {"2024-01": -100.0, "2024-02": -200.0}}
        self.assertFalse(infer_contra(accounts, closing)["1510 AD"].is_contra)


class BalanceComputationTests(unittest.TestCase):
    def test_balances_are_cumulative_to_each_period_end(self):
        txns = [
            _txn(1, date(2024, 1, 5), [("1000 Bank", "debit", 100.0), ("4000 Sales", "credit", 100.0)]),
            _txn(2, date(2024, 2, 5), [("6000 Rent", "debit", 30.0), ("1000 Bank", "credit", 30.0)]),
        ]
        closing = period_balances(txns)
        self.assertAlmostEqual(closing["1000 Bank"]["2024-01"], 100.0)
        self.assertAlmostEqual(closing["1000 Bank"]["2024-02"], 70.0)

    def test_accounts_carry_forward_through_inactive_periods(self):
        txns = [
            _txn(1, date(2024, 1, 5), [("1000 Bank", "debit", 100.0), ("4000 Sales", "credit", 100.0)]),
            _txn(2, date(2024, 3, 5), [("6000 Rent", "debit", 10.0), ("1000 Bank", "credit", 10.0)]),
        ]
        closing = period_balances(txns)
        self.assertAlmostEqual(closing["1000 Bank"]["2024-02"], 100.0)


class HistoryFixtureTests(unittest.TestCase):
    """End to end on the 25-month fixture, which contains one of each case."""

    CONTRA = "1510 Accum Depreciation"
    BROKEN = "1010 Bank Payroll"

    @classmethod
    def setUpClass(cls):
        cls.accounts = load_accounts(HISTORY / "accounts.tsv")
        txns, errors = build_transactions(load_lines(HISTORY / "transactions.tsv"), cls.accounts)
        assert not errors, errors
        cls.txns = txns
        cls.findings, cls.contra = unnatural_balances(cls.accounts, txns, min_consecutive=1)

    def test_accumulated_depreciation_is_inferred_contra_on_all_three_signals(self):
        verdict = self.contra[self.CONTRA]
        self.assertTrue(verdict.is_contra)
        self.assertGreaterEqual(verdict.score, 4)
        joined = " ".join(verdict.reasons)
        self.assertIn("parent", joined)
        self.assertIn("covering", joined)

    def test_the_contra_carries_a_credit_balance_yet_is_not_flagged(self):
        """The whole point: it is off its type's side and must not be reported."""
        closing = period_balances(self.txns)
        self.assertEqual(side_of(closing[self.CONTRA]["2025-01"]), "credit")
        self.assertEqual(natural_side(self.accounts[self.CONTRA]), "debit")
        self.assertNotIn(self.CONTRA, [f.account_id for f in self.findings])

    def test_the_overdrawn_bank_is_flagged_high(self):
        flagged = {f.account_id: f for f in self.findings}
        self.assertIn(self.BROKEN, flagged)
        finding = flagged[self.BROKEN]
        self.assertEqual(finding.severity, "high")
        self.assertEqual(finding.expected_side, "debit")
        self.assertEqual(finding.actual_side, "credit")
        self.assertFalse(finding.contra_inferred)
        self.assertGreaterEqual(finding.consecutive_off, 2)

    def test_min_consecutive_filters_transient_cases(self):
        strict, _ = unnatural_balances(self.accounts, self.txns, min_consecutive=99)
        self.assertEqual(strict, [])

    def test_healthy_accounts_are_silent(self):
        flagged = {f.account_id for f in self.findings}
        for account_id in ("1000 Bank", "4000 Vehicle Sales", "2600 Loan", "6000 Rent"):
            self.assertNotIn(account_id, flagged)


if __name__ == "__main__":
    unittest.main()
