"""Minimal rewrite: split a journal into balanced subsets before averaging.

Concept §3.3. The averaging rewrite pairs every debit with every credit, which
is correct when a journal records one event and an over-estimate when it packs
several. Splitting first pairs only lines that settle against each other, so the
edges a packed journal contributes are the ones it actually posted.

Wide journals are the ones that need this most. A hundred-line entry is almost
always a catch-up posting, where someone has brought a period's activity onto
the books in one document for convenience. Such an entry is a bundle of
unrelated events by construction, and averaging across it produces a dense block
of edges that were never posted. So the search has to scale with journal width
rather than give up on it.

Two properties keep it honest:

**A subset is emitted only when it is forced.** Where several balanced subsets
of the same size compete for the same lines, the journal does not record which
pairing occurred, and choosing one would substitute an unmeasured guess for a
measured estimate. Contested lines stay together and averaging handles them,
which is the honest treatment because averaging reports its own uncertainty
through the ambiguous share.

**Refusal is per subset, not per journal.** One ambiguous cluster inside a
catch-up entry says nothing about the clean pairs beside it. The clean pairs are
emitted and the cluster is left whole, rather than the ambiguity blocking the
whole document.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from itertools import combinations
from math import comb, log10

from .models import (
    BALANCE_TOLERANCE,
    SPLIT_MAX_COMBINATIONS,
    SPLIT_MAX_LINES,
    SPLIT_MAX_SUBSET_LINES,
    SPLIT_MAX_SUBSETS_PER_SIZE,
    Line,
    Transaction,
)

def _decimals(tolerance: float) -> int:
    """Places to quantize amounts to, derived from the balance tolerance.

    Both passes match totals by dictionary lookup rather than by comparing every
    pair, and floats do not hash within a tolerance. Rounding to the tolerance's
    own precision — 6 places at the 1e-6 default — makes the lookup agree with
    the balance check to the accuracy the check itself claims, and sits well
    below any real currency precision.
    """
    return max(0, int(round(-log10(tolerance)))) if tolerance > 0 else 6


def _uncontested(subsets: list[frozenset[int]]) -> list[frozenset[int]]:
    """Subsets that share no line with any other subset in the list.

    A line appearing in exactly one subset is uncontested; a subset all of whose
    lines are uncontested is forced, because no competing subset of the same size
    can claim any part of it. Uncontested subsets are pairwise disjoint by
    construction, so the whole set can be emitted together.
    """
    seen = Counter(i for subset in subsets for i in subset)
    return [s for s in subsets if all(seen[i] == 1 for i in s)]


def _forced_pairs(lines: list[Line], decimals: int) -> list[frozenset[int]]:
    """Forced two-line events, in time linear in journal width.

    A two-line balanced subset is a debit and a credit of equal amount, so the
    pairs need no enumeration: group line indexes by amount and side, then keep
    the amounts carrying exactly one line on each side. Any amount with two
    debits or two credits yields pairs that compete, and those lines are left
    for the caller to leave alone.

    This is the pass that makes wide journals tractable. A catch-up entry is
    mostly clean amount matches, so it decomposes here without ever reaching the
    combinatorial search below.
    """
    debits: dict[float, list[int]] = defaultdict(list)
    credits: dict[float, list[int]] = defaultdict(list)
    for i, line in enumerate(lines):
        bucket = debits if line.side == "debit" else credits
        bucket[round(line.amount, decimals)].append(i)

    pairs: list[frozenset[int]] = []
    for amount, dr in debits.items():
        cr = credits.get(amount)
        if cr and len(dr) == 1 and len(cr) == 1:
            pairs.append(frozenset((dr[0], cr[0])))
    return pairs


def _side_cost(n_debits: int, n_credits: int, size: int) -> int:
    """Combinations the matched search examines for one subset size."""
    return sum(
        comb(n_debits, d) + comb(n_credits, size - d)
        for d in range(1, size)
        if d <= n_debits and size - d <= n_credits
    )


def _forced_subsets_of_size(
    lines: list[Line],
    size: int,
    debit_idx: list[int],
    credit_idx: list[int],
    decimals: int,
    max_subsets: int,
) -> list[frozenset[int]]:
    """Forced balanced subsets of one size, matching debit sums to credit sums.

    A balanced subset of `size` lines is some `d` debits and `size - d` credits
    whose totals agree, so the sides can be enumerated separately and joined on
    the shared total. That costs C(debits, d) + C(credits, size-d) per split
    rather than C(lines, size) — for a 20-line journal at size 8, roughly two
    thousand combinations instead of a hundred and twenty-six thousand.

    Line amounts are positive, so every subset found necessarily holds at least
    one line of each side; balance alone identifies a candidate event. Totals
    are matched as quantized keys for the same reason amounts are in the pair
    pass.
    """
    found: list[frozenset[int]] = []
    for n_debits in range(1, size):
        n_credits = size - n_debits
        if n_debits > len(debit_idx) or n_credits > len(credit_idx):
            continue

        by_total: dict[float, list[tuple[int, ...]]] = defaultdict(list)
        for combo in combinations(credit_idx, n_credits):
            total = round(sum(lines[i].amount for i in combo), decimals)
            by_total[total].append(combo)

        for combo in combinations(debit_idx, n_debits):
            total = round(sum(lines[i].amount for i in combo), decimals)
            for credits in by_total.get(total, ()):
                found.append(frozenset(combo + credits))
                if len(found) > max_subsets:
                    # This many balanced subsets of one size can only overlap
                    # heavily, so none of them is forced. Give up on the size
                    # rather than pay to enumerate the rest.
                    return []

    return _uncontested(found)


def _smallest_forced(
    lines: list[Line],
    tolerance: float,
    max_subset_lines: int,
    max_combinations: int,
    max_subsets: int,
) -> list[frozenset[int]]:
    """Forced subsets at the smallest size that yields any.

    Ascending size gives the finest partition and finds the common two-line
    settlement before any larger cover.
    """
    decimals = _decimals(tolerance)
    pairs = _forced_pairs(lines, decimals)
    if pairs:
        return pairs

    debit_idx = [i for i, line in enumerate(lines) if line.side == "debit"]
    credit_idx = [i for i, line in enumerate(lines) if line.side != "debit"]

    # Proper subsets only: size n is the journal itself, which balances by
    # construction and would recurse forever.
    for size in range(3, min(max_subset_lines, len(lines) - 1) + 1):
        if _side_cost(len(debit_idx), len(credit_idx), size) > max_combinations:
            # Beyond the search budget. Larger sizes only cost more, so stop:
            # the remaining lines stay together, which is the conservative
            # outcome and the one averaging already handles.
            break
        found = _forced_subsets_of_size(
            lines, size, debit_idx, credit_idx, decimals, max_subsets
        )
        if found:
            return found
    return []


def split_lines(
    lines: list[Line],
    *,
    tolerance: float = BALANCE_TOLERANCE,
    max_lines: int = SPLIT_MAX_LINES,
    max_subset_lines: int = SPLIT_MAX_SUBSET_LINES,
    max_combinations: int = SPLIT_MAX_COMBINATIONS,
    max_subsets: int = SPLIT_MAX_SUBSETS_PER_SIZE,
) -> list[list[Line]]:
    """Partition balanced journal lines into the finest forced balanced groups.

    Returns `[lines]` unchanged when nothing is forced, so the caller can treat
    the result uniformly. Group order follows discovery and line order within a
    group follows the input, which keeps the output deterministic.
    """
    if len(lines) > max_lines:
        return [lines]

    groups: list[list[Line]] = []
    rest = list(lines)
    # Removing a forced subset can free lines that were previously contested, so
    # the search restarts from the smallest size after every carve.
    while len(rest) > 2:
        found = _smallest_forced(
            rest, tolerance, max_subset_lines, max_combinations, max_subsets
        )
        if not found:
            break
        used: set[int] = set()
        for subset in found:
            groups.append([rest[i] for i in sorted(subset)])
            used |= subset
        rest = [line for i, line in enumerate(rest) if i not in used]

    if rest:
        groups.append(rest)
    return groups


def split_transaction(
    txn: Transaction,
    *,
    tolerance: float = BALANCE_TOLERANCE,
    max_lines: int = SPLIT_MAX_LINES,
    max_subset_lines: int = SPLIT_MAX_SUBSET_LINES,
    max_combinations: int = SPLIT_MAX_COMBINATIONS,
    max_subsets: int = SPLIT_MAX_SUBSETS_PER_SIZE,
) -> list[Transaction]:
    """A transaction as the balanced sub-transactions it decomposes into.

    Each carries the parent's id and date, so downstream depth counting still
    attributes every edge to one source transaction rather than to the pieces.
    """
    groups = split_lines(
        txn.lines,
        tolerance=tolerance,
        max_lines=max_lines,
        max_subset_lines=max_subset_lines,
        max_combinations=max_combinations,
        max_subsets=max_subsets,
    )
    if len(groups) == 1:
        return [txn]
    return [
        Transaction(txn_id=txn.txn_id, date=txn.date, lines=group) for group in groups
    ]
