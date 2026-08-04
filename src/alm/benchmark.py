"""Cross-entity comparison and benchmarking.

Concept §6.2. Account identifiers are entity-specific, so two entities' edge
distributions cannot be compared directly: one entity's `1000 Bank` and another's
`10100 Operating` are the same thing under different names. Account types are the
bridge. Projecting each map's edges onto type pairs gives a distribution over the
same axis for every entity, and because the map is already expressed in shares,
the projections are comparable across entities of any size.

Two granularities are available. Base groups — Asset, Liability, Equity, Income,
Expense — compare across any chart of accounts, since every product's type
vocabulary maps onto them. Raw account types are finer but only comparable where
the entities happen to share type labels.

Self-loop edges are excluded before projection, following concept §3.3.1: a
self-loop's type pair is identical on both sides by construction, so including
them would load the diagonal with rewrite artifacts and read as reclassification
activity the entity never posted. The share dropped is reported rather than
silently discarded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

from .models import LogicMap

# Base groups from concept §6. The vocabulary matches `balances.NATURAL_SIDE`,
# which classifies the same types by balance direction rather than by role.
BASE_GROUP: dict[str, str] = {
    "Bank": "Asset",
    "Accounts receivable (A/R)": "Asset",
    "Other Current Assets": "Asset",
    "Fixed Assets": "Asset",
    "Other Assets": "Asset",
    "Inventory": "Asset",
    "Accounts payable (A/P)": "Liability",
    "Credit Card": "Liability",
    "Other Current Liabilities": "Liability",
    "Long Term Liabilities": "Liability",
    "Equity": "Equity",
    "Income": "Income",
    "Other Income": "Income",
    "Expenses": "Expense",
    "Expense": "Expense",
    "Other Expense": "Expense",
    "Cost of Goods Sold": "Expense",
}

UNCLASSIFIED = "Unclassified"
LEVELS = ("group", "type")


def base_group(account_type: str) -> str:
    """Base group for an account type, or `Unclassified` where unknown.

    Unknown types are kept rather than dropped, so an unmapped chart shows up as
    a visible block of unclassified activity instead of quietly changing the
    denominators.
    """
    return BASE_GROUP.get(account_type.strip(), UNCLASSIFIED)


def _axis(account_type: str, level: str) -> str:
    if level == "group":
        return base_group(account_type)
    return account_type.strip() or UNCLASSIFIED


@dataclass
class TypeCell:
    """One type pair's presence in one entity."""

    debit: str
    credit: str
    weight: float = 0.0
    depth: int = 0
    edge_count: int = 0
    weight_share: float = 0.0
    depth_share: float = 0.0


@dataclass
class EntitySpectrum:
    """A map projected onto type pairs, as shares that sum to 1."""

    label: str
    level: str
    cells: dict[tuple[str, str], TypeCell] = field(default_factory=dict)
    self_loop_share: float = 0.0
    unclassified_share: float = 0.0
    account_count: int = 0
    edge_count: int = 0

    def share(self, pair: tuple[str, str]) -> float:
        cell = self.cells.get(pair)
        return cell.weight_share if cell else 0.0

    def pairs(self) -> set[tuple[str, str]]:
        return set(self.cells)


def type_spectrum(
    logic_map: LogicMap, *, label: str | None = None, level: str = "group"
) -> EntitySpectrum:
    """Project a map's edges onto type pairs.

    Weight and depth are each renormalized over the retained edges, so the result
    is a distribution comparable with any other entity's regardless of scale.
    """
    if level not in LEVELS:
        raise ValueError(f"level must be one of {LEVELS}")

    spectrum = EntitySpectrum(
        label=label or logic_map.window_label,
        level=level,
        account_count=len(logic_map.accounts),
        edge_count=len(logic_map.edges),
    )

    self_loop_weight = 0.0
    unclassified_weight = 0.0
    for key, stat in logic_map.edges.items():
        if key.is_self_loop:
            # Concept §3.3.1: decided before any account-type reasoning.
            self_loop_weight += stat.weight_sum
            continue

        debit = _axis(logic_map.account_type(key.debit_account_id), level)
        credit = _axis(logic_map.account_type(key.credit_account_id), level)
        if UNCLASSIFIED in (debit, credit):
            unclassified_weight += stat.weight_sum

        cell = spectrum.cells.get((debit, credit))
        if cell is None:
            cell = TypeCell(debit=debit, credit=credit)
            spectrum.cells[(debit, credit)] = cell
        cell.weight += stat.weight_sum
        cell.depth += stat.depth
        cell.edge_count += 1

    total_weight = sum(c.weight for c in spectrum.cells.values())
    total_depth = sum(c.depth for c in spectrum.cells.values())
    for cell in spectrum.cells.values():
        cell.weight_share = cell.weight / total_weight if total_weight else 0.0
        cell.depth_share = cell.depth / total_depth if total_depth else 0.0

    gross = total_weight + self_loop_weight
    spectrum.self_loop_share = self_loop_weight / gross if gross else 0.0
    spectrum.unclassified_share = (
        unclassified_weight / total_weight if total_weight else 0.0
    )
    return spectrum


def divergence(a: EntitySpectrum, b: EntitySpectrum) -> float:
    """Total variation distance between two type spectra, in [0, 1].

    Half the summed absolute difference in share across every type pair either
    entity uses. It reads directly: 0 means the two entities move value across
    the same type pairs in the same proportions, and 0.4 means 40% of one
    entity's flow would have to move to a different type pair to match the other.
    """
    return 0.5 * sum(
        abs(a.share(pair) - b.share(pair)) for pair in a.pairs() | b.pairs()
    )


def pooled(spectra: list[EntitySpectrum], *, label: str = "peer group") -> EntitySpectrum:
    """The peer group as one distribution: the mean share per type pair.

    Averaging shares rather than summing weights keeps a large peer from
    dominating the group — every peer contributes equally, which is what makes
    the result a description of the group rather than of its biggest member.
    """
    if not spectra:
        raise ValueError("pooled() needs at least one spectrum")

    out = EntitySpectrum(label=label, level=spectra[0].level)
    n = len(spectra)
    for pair in set().union(*(s.pairs() for s in spectra)):
        cell = TypeCell(debit=pair[0], credit=pair[1])
        cell.weight_share = sum(s.share(pair) for s in spectra) / n
        cell.depth_share = sum(
            s.cells[pair].depth_share for s in spectra if pair in s.cells
        ) / n
        cell.edge_count = sum(s.cells[pair].edge_count for s in spectra if pair in s.cells)
        out.cells[pair] = cell
    return out


@dataclass
class BenchmarkRow:
    debit: str
    credit: str
    subject_share: float
    peer_mean: float
    peer_median: float
    peer_min: float
    peer_max: float
    delta: float  # subject_share - peer_median
    peers_present: int
    peers_total: int
    signal: str


def benchmark(
    subject: EntitySpectrum, peers: list[EntitySpectrum]
) -> list[BenchmarkRow]:
    """Position one entity's type spectrum against a peer group's.

    One row per type pair either side uses, sorted by the size of the gap, so
    the reader sees where the entity differs before seeing where it agrees.
    Peer statistics are taken over every peer, counting a peer that never uses a
    pair as a zero — omitting it would flatter the subject by comparing only
    against peers that behave as it does.
    """
    if not peers:
        raise ValueError("benchmark() needs at least one peer")

    rows: list[BenchmarkRow] = []
    for pair in subject.pairs() | set().union(*(p.pairs() for p in peers)):
        peer_shares = [p.share(pair) for p in peers]
        present = sum(1 for p in peers if pair in p.cells)
        subject_share = subject.share(pair)
        med = median(peer_shares)

        if subject_share and not present:
            signal = "unique"  # the entity does this and no peer does
        elif present and not subject_share:
            signal = "absent"  # peers do this and the entity does not
        elif subject_share > med:
            signal = "over"
        elif subject_share < med:
            signal = "under"
        else:
            signal = "in line"

        rows.append(
            BenchmarkRow(
                debit=pair[0],
                credit=pair[1],
                subject_share=subject_share,
                peer_mean=sum(peer_shares) / len(peer_shares),
                peer_median=med,
                peer_min=min(peer_shares),
                peer_max=max(peer_shares),
                delta=subject_share - med,
                peers_present=present,
                peers_total=len(peers),
                signal=signal,
            )
        )

    rows.sort(key=lambda r: (-abs(r.delta), r.debit, r.credit))
    return rows


def divergence_matrix(
    spectra: list[EntitySpectrum],
) -> list[tuple[str, str, float]]:
    """Pairwise distance between every pair of entities, closest first."""
    out: list[tuple[str, str, float]] = []
    for i, a in enumerate(spectra):
        for b in spectra[i + 1 :]:
            out.append((a.label, b.label, divergence(a, b)))
    out.sort(key=lambda row: row[2])
    return out
