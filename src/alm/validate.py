from __future__ import annotations

from dataclasses import dataclass

from .models import BALANCE_TOLERANCE, Account, Line, Transaction, group_lines


@dataclass
class ValidationError:
    txn_id: str
    message: str


def build_transactions(
    lines: list[Line],
    accounts: dict[str, Account],
    *,
    tolerance: float = BALANCE_TOLERANCE,
    require_known_accounts: bool = True,
) -> tuple[list[Transaction], list[ValidationError]]:
    """Group lines into transactions and validate double-entry axioms."""
    errors: list[ValidationError] = []
    txns: list[Transaction] = []

    for txn_id, txn_lines in group_lines(lines).items():
        if require_known_accounts:
            for ln in txn_lines:
                if ln.account_id not in accounts:
                    errors.append(
                        ValidationError(
                            txn_id,
                            f"unknown account_id {ln.account_id!r}",
                        )
                    )
        sides = {ln.side for ln in txn_lines}
        if sides - {"debit", "credit"}:
            errors.append(
                ValidationError(txn_id, f"invalid side values: {sorted(sides - {'debit', 'credit'})}")
            )
        for ln in txn_lines:
            if ln.amount <= 0:
                errors.append(
                    ValidationError(txn_id, f"non-positive amount {ln.amount} on {ln.account_id}")
                )

        debits = [ln for ln in txn_lines if ln.side == "debit"]
        credits = [ln for ln in txn_lines if ln.side == "credit"]
        if not debits or not credits:
            errors.append(
                ValidationError(
                    txn_id,
                    f"need ≥1 debit and ≥1 credit (debits={len(debits)}, credits={len(credits)})",
                )
            )
            continue

        dr = sum(ln.amount for ln in debits)
        cr = sum(ln.amount for ln in credits)
        if abs(dr - cr) > tolerance:
            errors.append(
                ValidationError(
                    txn_id,
                    f"unbalanced: debits={dr:.6f} credits={cr:.6f} diff={dr - cr:.6f}",
                )
            )
            continue

        # Only emit txn if no errors were recorded for this id so far in this pass
        txn_errors = [e for e in errors if e.txn_id == txn_id]
        if txn_errors:
            continue

        dates = {ln.date for ln in txn_lines}
        txn_date = min(dates)
        txns.append(Transaction(txn_id=txn_id, date=txn_date, lines=list(txn_lines)))

    return txns, errors
