"""Period slicing and forward expectation.

The entity image is period-indexed (concept §7): a baseline is built from closed
periods and the open period is measured against it. Everything here is derived
from the `date` already carried on every line — no extra input contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .models import DEFAULT_BASELINE_PERIODS, Line, Transaction

GRANULARITIES = ("month", "quarter", "year")


def period_key(day: date, granularity: str = "month") -> str:
    """Sortable period label. Lexical order equals chronological order."""
    if granularity == "month":
        return f"{day.year:04d}-{day.month:02d}"
    if granularity == "quarter":
        return f"{day.year:04d}-Q{(day.month - 1) // 3 + 1}"
    if granularity == "year":
        return f"{day.year:04d}"
    raise ValueError(f"unknown granularity {granularity!r}; expected one of {GRANULARITIES}")


def filter_lines(
    lines: list[Line],
    *,
    start: date | None = None,
    end: date | None = None,
) -> list[Line]:
    """Keep lines whose date falls in [start, end], both inclusive.

    Filtering happens on lines rather than transactions so the caller can slice
    before validation. A transaction straddling the boundary would be split and
    then fail the balance check — which is the correct outcome: a window that
    cuts a journal in half does not describe a real set of books.
    """
    out = lines
    if start is not None:
        out = [ln for ln in out if ln.date >= start]
    if end is not None:
        out = [ln for ln in out if ln.date <= end]
    return out


@dataclass
class PeriodStat:
    period: str
    txn_count: int = 0
    line_count: int = 0
    weight: float = 0.0

    @property
    def mean_txn_weight(self) -> float:
        return self.weight / self.txn_count if self.txn_count else 0.0


def period_activity(
    txns: list[Transaction], *, granularity: str = "month"
) -> list[PeriodStat]:
    """Per-period activity totals, chronologically ordered.

    Weight is the transaction total (debit side), matching the rewrite's
    conserved quantity, so period weights sum to the map's total_weight.
    """
    stats: dict[str, PeriodStat] = {}
    for txn in txns:
        key = period_key(txn.date, granularity)
        stat = stats.setdefault(key, PeriodStat(period=key))
        stat.txn_count += 1
        stat.line_count += len(txn.lines)
        stat.weight += txn.debit_total()
    return [stats[k] for k in sorted(stats)]


@dataclass
class ForwardExpectation:
    open_period: str
    baseline_periods: list[str]
    expected_weight: float
    actual_weight: float
    expected_txn_count: float
    actual_txn_count: int

    @property
    def weight_variance(self) -> float:
        return self.actual_weight - self.expected_weight

    @property
    def weight_variance_pct(self) -> float:
        return self.weight_variance / self.expected_weight if self.expected_weight else 0.0


def forward_expectation(
    stats: list[PeriodStat],
    *,
    baseline_periods: int = DEFAULT_BASELINE_PERIODS,
) -> ForwardExpectation | None:
    """Project the open period from the trailing closed periods.

    The paper's simple forward-looking state, in activity terms:

        Ê(P₁) = (1/n) Σ_{-n..-1} E(P)

    i.e. the average of the n most recent closed periods. The last period in
    `stats` is treated as open and measured against that projection. Returns
    None when there is nothing to project from.
    """
    if len(stats) < 2:
        return None
    *closed, open_stat = stats
    window = closed[-baseline_periods:]
    if not window:
        return None
    n = len(window)
    return ForwardExpectation(
        open_period=open_stat.period,
        baseline_periods=[s.period for s in window],
        expected_weight=sum(s.weight for s in window) / n,
        actual_weight=open_stat.weight,
        expected_txn_count=sum(s.txn_count for s in window) / n,
        actual_txn_count=open_stat.txn_count,
    )
