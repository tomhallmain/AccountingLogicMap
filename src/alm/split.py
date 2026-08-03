"""Minimal rewrite: split a journal into balanced subsets before averaging.

Concept §3.3. The averaging rewrite pairs every debit with every credit, which
is correct when a journal records one event and an over-estimate when it packs
several. Splitting first pairs only lines that settle against each other, so the
edges a packed journal contributes are the ones it actually posted.

The rule that makes this safe is that a split is taken only when it is forced.
Averaging is honest about its uncertainty — the ambiguous share records exactly
how much of an edge's weight the product had to estimate. A splitter that picked
one arbitrary pairing out of several equally valid ones would replace a measured
estimate with an unmeasured guess, which is worse. So a balanced subset is
emitted only when no competing subset of the same size overlaps it; where the
pairings compete, the lines stay together and averaging handles them.
"""

from __future__ import annotations

from itertools import combinations

from .models import BALANCE_TOLERANCE, SPLIT_MAX_LINES, Line, Transaction


def _signed_total(lines: list[Line]) -> float:
    """Debits positive, credits negative. A balanced set sums to zero."""
    return sum(ln.amount if ln.side == "debit" else -ln.amount for ln in lines)


def _balanced_subsets(
    lines: list[Line], size: int, tolerance: float
) -> list[frozenset[int]]:
    """Index sets of the given size that balance on their own.

    Line amounts are positive, so a set summing to zero necessarily holds at
    least one debit and one credit; no separate side check is needed.
    """
    found: list[frozenset[int]] = []
    for combo in combinations(range(len(lines)), size):
        if abs(_signed_total([lines[i] for i in combo])) <= tolerance:
            found.append(frozenset(combo))
    return found


def _pairwise_disjoint(subsets: list[frozenset[int]]) -> bool:
    seen: set[int] = set()
    for subset in subsets:
        if seen & subset:
            return False
        seen |= subset
    return True


def split_lines(
    lines: list[Line],
    *,
    tolerance: float = BALANCE_TOLERANCE,
    max_lines: int = SPLIT_MAX_LINES,
) -> list[list[Line]]:
    """Partition balanced journal lines into the finest forced balanced groups.

    Returns `[lines]` unchanged when no split is forced, so the caller can treat
    the result uniformly. Group order and the order of lines within a group
    follow the input, which keeps the output deterministic.
    """
    if len(lines) > max_lines:
        # The subset search is exponential in line count. Beyond the cap the
        # journal is averaged whole, which is the documented default anyway.
        return [lines]
    return _split(lines, tolerance)


def _split(lines: list[Line], tolerance: float) -> list[list[Line]]:
    n = len(lines)
    # Proper subsets only: size n is the journal itself, which is balanced by
    # construction and would recurse forever.
    for size in range(2, n):
        subsets = _balanced_subsets(lines, size, tolerance)
        if not subsets:
            continue
        if not _pairwise_disjoint(subsets):
            # Several ways to carve out a subset this size, and they compete for
            # the same lines. Which one is right is exactly what the journal does
            # not say, so stop and let averaging record the uncertainty.
            return [lines]

        groups = [[lines[i] for i in sorted(subset)] for subset in subsets]
        used = frozenset().union(*subsets)
        rest = [lines[i] for i in range(n) if i not in used]
        if rest:
            groups.extend(_split(rest, tolerance))
        return groups
    return [lines]


def split_transaction(
    txn: Transaction,
    *,
    tolerance: float = BALANCE_TOLERANCE,
    max_lines: int = SPLIT_MAX_LINES,
) -> list[Transaction]:
    """A transaction as the balanced sub-transactions it decomposes into.

    Each carries the parent's id and date, so downstream depth counting still
    attributes every edge to one source transaction rather than to the pieces.
    """
    groups = split_lines(txn.lines, tolerance=tolerance, max_lines=max_lines)
    if len(groups) == 1:
        return [txn]
    return [
        Transaction(txn_id=txn.txn_id, date=txn.date, lines=group) for group in groups
    ]
