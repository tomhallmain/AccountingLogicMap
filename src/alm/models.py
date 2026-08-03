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


@dataclass
class EdgeStat:
    key: EdgeKey
    weight_sum: float = 0.0
    depth: int = 0  # number of transactions that produced this edge

    @property
    def mean_weight(self) -> float:
        return self.weight_sum / self.depth if self.depth else 0.0


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
    signal: str
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
