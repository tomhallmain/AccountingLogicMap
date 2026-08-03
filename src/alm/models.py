from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Iterator


BALANCE_TOLERANCE = 1e-6
RARE_EDGE_RANK_FRAC = 0.9
PREDICT_DEFAULT_TOP_K = 10
ANOMALY_DEFAULT_TOP_K = 25
EVAL_HIT_K = (3, 5)
PREDICT_FREQUENT_DEPTH = 3  # spec §11.2 pass bar applies to edges at/above this depth

# Trailing closed periods used to project the open period. The paper suggests
# 12-18 months; fewer makes the average too noisy to read a variance against.
DEFAULT_BASELINE_PERIODS = 12

# Anomaly qualifiers. Rank cutoffs are fractions of the map, not absolute counts,
# so they stay meaningful on maps of any size; each is paired with a materiality
# floor so rank churn on tiny edges cannot masquerade as a structural signal.
BASELINE_TOP_FRAC = 0.25
MISSING_EDGE_MIN_SHARE = 0.01
RANK_SHIFT_MIN_PCTILE = 0.15
RANK_SHIFT_MIN_DELTA_SHARE = 0.02
NEAR_ZERO_SHARE = 1e-6


@dataclass(frozen=True)
class Account:
    account_id: str
    name: str
    account_type: str


@dataclass(frozen=True)
class Line:
    txn_id: str
    date: date
    account_id: str
    side: str  # "debit" | "credit"
    amount: float
    memo: str = ""


@dataclass
class Transaction:
    txn_id: str
    date: date
    lines: list[Line] = field(default_factory=list)

    def debit_lines(self) -> list[Line]:
        return [ln for ln in self.lines if ln.side == "debit"]

    def credit_lines(self) -> list[Line]:
        return [ln for ln in self.lines if ln.side == "credit"]

    def debit_total(self) -> float:
        return sum(ln.amount for ln in self.debit_lines())

    def credit_total(self) -> float:
        return sum(ln.amount for ln in self.credit_lines())


@dataclass(frozen=True)
class EdgeKey:
    debit_account_id: str
    credit_account_id: str

    def label(self) -> str:
        return f"{self.debit_account_id} | {self.credit_account_id}"

    @property
    def is_self_loop(self) -> bool:
        """Same account on both sides.

        The DR×CR product emits these whenever one account is debited and
        credited in the same journal. They are rewrite artifacts, not value
        movements: no account funded another. They are retained (dropping them
        would break weight conservation) but must never be read as postings.
        """
        return self.debit_account_id == self.credit_account_id


@dataclass
class EdgeStat:
    key: EdgeKey
    weight_sum: float = 0.0
    depth: int = 0  # number of transactions that produced this edge
    pair_instances: int = 0  # DR×CR pairs emitted for this edge
    ambiguous_weight: float = 0.0  # weight from journals with >1 line on both sides
    period_weights: dict[str, float] = field(default_factory=dict)
    period_depths: dict[str, int] = field(default_factory=dict)

    def weight_in(self, periods: Iterable[str] | None) -> float:
        """Edge weight restricted to a set of periods; full weight when None."""
        if periods is None:
            return self.weight_sum
        return sum(self.period_weights.get(p, 0.0) for p in periods)

    def depth_in(self, periods: Iterable[str] | None) -> int:
        if periods is None:
            return self.depth
        return sum(self.period_depths.get(p, 0) for p in periods)

    @property
    def mean_weight(self) -> float:
        return self.weight_sum / self.depth if self.depth else 0.0

    @property
    def ambiguous_share(self) -> float:
        """Fraction of this edge's weight the rewrite had to guess at.

        The paper's "proportion of reduced hyperedges". A journal with one line
        on either side pins its pairings exactly; only when both sides carry
        several lines can the Cartesian product invent a pair that never
        happened. A high share means treat the edge as weak evidence.
        """
        return self.ambiguous_weight / self.weight_sum if self.weight_sum else 0.0


@dataclass
class ScoredEdge:
    key: EdgeKey
    weight_sum: float
    depth: int
    mean_weight: float
    share_w: float
    share_c: float
    share_m: float
    norm: float
    rank: int
    ambiguous_share: float = 0.0
    is_self_loop: bool = False


@dataclass
class LogicMap:
    accounts: dict[str, Account]
    edges: dict[EdgeKey, EdgeStat]
    total_weight: float
    total_depth: int
    total_mean_weight: float  # Σ over edges of (weight_sum / depth); workbook st!B3
    window_label: str
    txn_count: int = 0
    line_count: int = 0
    scored: list[ScoredEdge] = field(default_factory=list)
    granularity: str = "month"
    periods: list[str] = field(default_factory=list)

    def account_type(self, account_id: str) -> str:
        acct = self.accounts.get(account_id)
        return acct.account_type if acct else "Unknown"

    def edge_rank_index(self) -> dict[EdgeKey, ScoredEdge]:
        return {se.key: se for se in self.scored}

    def iter_edges_from_debit(self, account_id: str) -> Iterator[EdgeStat]:
        for key, stat in self.edges.items():
            if key.debit_account_id == account_id:
                yield stat

    def iter_edges_from_credit(self, account_id: str) -> Iterator[EdgeStat]:
        for key, stat in self.edges.items():
            if key.credit_account_id == account_id:
                yield stat


@dataclass
class EdgeFinding:
    key: EdgeKey
    weight: float
    seen: bool
    rank: int | None
    norm: float | None
    share_w: float | None
    debit_type: str
    credit_type: str
    note: str


@dataclass
class VerifyResult:
    txn_id: str
    verdict: str  # pass | warn | fail
    reasons: list[str]
    findings: list[EdgeFinding]
    expected_verdict: str | None = None


@dataclass
class PredictRow:
    account_id: str
    account_type: str
    weight_sum: float
    depth: int
    probability: float
    norm: float | None
    mean_weight: float


@dataclass
class AnomalyRow:
    signals: list[str]  # one row per edge; an edge can trip several qualifiers
    debit_account_id: str
    credit_account_id: str
    baseline_share_w: float
    open_share_w: float
    delta_share_w: float
    baseline_rank: int | None
    open_rank: int | None
    note: str


def group_lines(lines: Iterable[Line]) -> dict[str, list[Line]]:
    grouped: dict[str, list[Line]] = {}
    for ln in lines:
        grouped.setdefault(ln.txn_id, []).append(ln)
    return grouped
