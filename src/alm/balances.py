"""Natural-balance quality signal.

The paper's cheapest available check: does an account's balance match the
characteristic direction of its type? A bank account with a credit balance is
overdrawn — technically possible, but sitting that way "for the whole course of a
monthly period or more implies at least an unacceptable lag in data accuracy or
completeness."

The complication is contra accounts. Accumulated Depreciation is a Fixed Asset
that always carries a credit balance, because it exists to reduce a sibling asset
on the same side of the sheet. Flagging it every period would bury the real
signal. Nothing in the input marks contras, so they are *inferred* — from where
the account sits in the chart, how it behaves against accounts of its own type,
and how long it has behaved that way.

The discriminator is persistence. A contra account has been on the "wrong" side
its entire life, by construction. A data-quality problem starts at some point.
Peer minority alone cannot tell the two apart, which is why it never decides on
its own.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .models import Account, Transaction
from .periods import period_key, period_span

BALANCE_ZERO_TOLERANCE = 0.005  # half a cent

# Characteristic balance direction per account type — the paper's B̃.
NATURAL_SIDE: dict[str, str] = {
    "Bank": "debit",
    "Accounts receivable (A/R)": "debit",
    "Other Current Assets": "debit",
    "Fixed Assets": "debit",
    "Other Assets": "debit",
    "Inventory": "debit",
    "Expenses": "debit",
    "Expense": "debit",
    "Other Expense": "debit",
    "Cost of Goods Sold": "debit",
    "Accounts payable (A/P)": "credit",
    "Credit Card": "credit",
    "Other Current Liabilities": "credit",
    "Long Term Liabilities": "credit",
    "Equity": "credit",
    "Income": "credit",
    "Other Income": "credit",
}

# Corroborating only — never sufficient on its own, since a name is not evidence
# about the books.
CONTRA_NAME_HINTS = (
    "accumulated depreciation",
    "accumulated amortization",
    "accumulated amortisation",
    "allowance for",
    "contra",
    "discount",
    "returns and allowances",
    "treasury stock",
)

CONTRA_SCORE_THRESHOLD = 2
MIN_PERIODS_FOR_LIFETIME_EVIDENCE = 3
# A contra carries a balance continuously once it exists — depreciation accrues
# every period. An account that is usually flat and dips the wrong way now and
# then is a clearing or timing problem, so require the off-side balance to cover
# most of the account's life before treating persistence as structural.
MIN_LIFETIME_COVERAGE = 0.6


def _flip(side: str) -> str:
    return "credit" if side == "debit" else "debit"


def natural_side(account: Account) -> str | None:
    """Characteristic direction from the account type alone, before contra logic."""
    return NATURAL_SIDE.get(account.account_type.strip())


def side_of(balance: float) -> str:
    if balance > BALANCE_ZERO_TOLERANCE:
        return "debit"
    if balance < -BALANCE_ZERO_TOLERANCE:
        return "credit"
    return "zero"


def _strip_code(label: str) -> str:
    """Drop a leading account number: '1500 Equipment' -> 'Equipment'."""
    head, _, tail = label.strip().partition(" ")
    return tail.strip() if tail and head.rstrip(".-").isdigit() else label.strip()


def _labels(account: Account) -> set[str]:
    """Every name this account might be referred to by, code or no code."""
    out = set()
    for text in (account.account_id, account.name):
        text = text.strip()
        out.add(text)
        out.add(_strip_code(text))
        if ":" in text:
            leaf = text.rsplit(":", 1)[1].strip()
            out.add(leaf)
            out.add(_strip_code(leaf))
    return {label.casefold() for label in out if label}


def parent_of(account: Account, accounts: dict[str, Account]) -> Account | None:
    """Resolve `Parent:Child` naming to the parent account, if it exists.

    QBO and Xero both express sub-accounts this way, and a contra is
    characteristically a child of the balance it reduces. The parent is matched
    with or without its account number, since charts are inconsistent about
    whether the code is part of the name.
    """
    for text in (account.name, account.account_id):
        if ":" not in text:
            continue
        parent_label = _strip_code(text.rsplit(":", 1)[0]).casefold()
        if not parent_label:
            continue
        for other in accounts.values():
            if other.account_id == account.account_id:
                continue
            if parent_label in _labels(other):
                return other
    return None


def period_balances(
    txns: list[Transaction], *, granularity: str = "month"
) -> dict[str, dict[str, float]]:
    """Closing balance per account per period, signed debit-positive.

    Balances are cumulative to each period end — natural balance is a statement
    about position, not about the period's activity.
    """
    movement: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    periods: set[str] = set()
    for txn in txns:
        key = period_key(txn.date, granularity)
        periods.add(key)
        for line in txn.lines:
            delta = line.amount if line.side == "debit" else -line.amount
            movement[line.account_id][key] += delta

    # Contiguous series, so dormant periods still carry the prior balance and
    # run-length counts over the series stay honest.
    ordered = (
        period_span(min(periods), max(periods), granularity) if periods else []
    )
    closing: dict[str, dict[str, float]] = {}
    for account_id, by_period in movement.items():
        running = 0.0
        out: dict[str, float] = {}
        for key in ordered:
            running += by_period.get(key, 0.0)
            out[key] = running
        closing[account_id] = out
    return closing


@dataclass
class ContraVerdict:
    account_id: str
    is_contra: bool
    score: int
    reasons: list[str] = field(default_factory=list)


def infer_contra(
    accounts: dict[str, Account],
    closing: dict[str, dict[str, float]],
) -> dict[str, ContraVerdict]:
    """Decide which accounts are structurally contra, without a manual flag.

    Three pieces of evidence, weighted so that no single weak one decides:

      +2  sits opposite a parent account of the same type (hierarchy)
      +2  has been opposite its type's natural side in every period it carried a
          balance, over at least MIN_PERIODS_FOR_LIFETIME_EVIDENCE periods
      +1  name matches a known contra form (corroboration only)

    Peer comparison is deliberately *not* scored. An account whose balance sits
    opposite its same-type peers is equally consistent with a contra and with an
    error; only lifetime persistence separates them.
    """
    verdicts: dict[str, ContraVerdict] = {}

    for account_id, account in accounts.items():
        base = natural_side(account)
        by_period = closing.get(account_id, {})
        score = 0
        reasons: list[str] = []

        if base is None:
            verdicts[account_id] = ContraVerdict(account_id, False, 0, ["unknown account type"])
            continue

        sides = [side_of(v) for v in by_period.values()]
        nonzero = [s for s in sides if s != "zero"]

        # (1) hierarchy: opposite the parent it reduces
        parent = parent_of(account, accounts)
        if parent is not None and nonzero:
            parent_sides = [
                side_of(v) for v in closing.get(parent.account_id, {}).values()
            ]
            parent_nonzero = [s for s in parent_sides if s != "zero"]
            if (
                parent_nonzero
                and parent.account_type.strip() == account.account_type.strip()
                and nonzero[-1] != parent_nonzero[-1]
            ):
                score += 2
                reasons.append(f"sits opposite its parent {parent.account_id!r}")

        # (2) lifetime persistence on the non-natural side.
        # Coverage matters as much as consistency: an account that is flat most
        # months and dips the wrong way occasionally is a timing problem, even
        # though every non-zero balance it ever held was on the "wrong" side.
        ordered = sorted(by_period)
        first_active = next(
            (i for i, p in enumerate(ordered) if side_of(by_period[p]) != "zero"), None
        )
        lifetime = len(ordered) - first_active if first_active is not None else 0
        coverage = len(nonzero) / lifetime if lifetime else 0.0
        if (
            len(nonzero) >= MIN_PERIODS_FOR_LIFETIME_EVIDENCE
            and coverage >= MIN_LIFETIME_COVERAGE
            and all(s == _flip(base) for s in nonzero)
        ):
            score += 2
            reasons.append(
                f"on the {_flip(base)} side in all {len(nonzero)} periods it carried a "
                f"balance, covering {coverage:.0%} of its life"
            )

        # (3) name corroboration
        blob = f"{account.account_id} {account.name}".lower()
        if any(hint in blob for hint in CONTRA_NAME_HINTS):
            score += 1
            reasons.append("name matches a known contra form")

        verdicts[account_id] = ContraVerdict(
            account_id=account_id,
            is_contra=score >= CONTRA_SCORE_THRESHOLD,
            score=score,
            reasons=reasons,
        )
    return verdicts


def expected_side(account: Account, verdict: ContraVerdict | None) -> str | None:
    """Natural side after contra inference — a contra expects the opposite."""
    base = natural_side(account)
    if base is None:
        return None
    if verdict is not None and verdict.is_contra:
        return _flip(base)
    return base


@dataclass
class BalanceFinding:
    account_id: str
    account_type: str
    expected_side: str
    actual_side: str
    balance: float
    period: str
    periods_off: int
    consecutive_off: int
    contra_inferred: bool
    severity: str
    note: str


def unnatural_balances(
    accounts: dict[str, Account],
    txns: list[Transaction],
    *,
    granularity: str = "month",
    min_consecutive: int = 1,
) -> tuple[list[BalanceFinding], dict[str, ContraVerdict]]:
    """Accounts whose closing balance sits opposite their expected side.

    Reported at the latest period, with how long the condition has held. A single
    period off-side may be timing; several in a row is the signal the paper
    describes.
    """
    closing = period_balances(txns, granularity=granularity)
    contra = infer_contra(accounts, closing)

    findings: list[BalanceFinding] = []
    for account_id, by_period in closing.items():
        account = accounts.get(account_id)
        if account is None:
            continue
        verdict = contra.get(account_id)
        want = expected_side(account, verdict)
        if want is None:
            continue

        ordered = sorted(by_period)
        sides = {p: side_of(by_period[p]) for p in ordered}
        off = [p for p in ordered if sides[p] not in (want, "zero")]
        if not off:
            continue

        last = ordered[-1]
        if sides[last] in (want, "zero"):
            continue  # resolved by the end of the window

        consecutive = 0
        for period in reversed(ordered):
            if sides[period] in (want, "zero"):
                break
            consecutive += 1
        if consecutive < min_consecutive:
            continue

        # A bank or card on the wrong side is the paper's worked example and the
        # most actionable case: it means the recorded cash position is impossible.
        severity = "high" if account.account_type.strip() in {"Bank", "Credit Card"} else "medium"
        if consecutive >= 3 and severity != "high":
            severity = "high"

        findings.append(
            BalanceFinding(
                account_id=account_id,
                account_type=account.account_type,
                expected_side=want,
                actual_side=sides[last],
                balance=by_period[last],
                period=last,
                periods_off=len(off),
                consecutive_off=consecutive,
                contra_inferred=bool(verdict and verdict.is_contra),
                severity=severity,
                note=(
                    f"{account.account_type} expects a {want} balance; "
                    f"held a {sides[last]} balance for {consecutive} consecutive period(s)"
                ),
            )
        )

    findings.sort(key=lambda f: (f.severity != "high", -f.consecutive_off, f.account_id))
    return findings, contra
