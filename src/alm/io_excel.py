from __future__ import annotations

from pathlib import Path
from typing import Iterable, Sequence

from .aggregate import logic_map_from_edge_stats
from .models import Account, EdgeKey, EdgeStat, LogicMap
from .score import score_map

DEFAULT_EDGE_SHEET = "rw"
DEFAULT_ACCOUNT_SHEET = "ca"

# Header text (lowercased, whitespace-collapsed) that identifies each edge column.
# Matching is by substring, so "Re-Split Debit Node" and "debit_account_id" both
# resolve to the debit endpoint.
EDGE_HEADER_HINTS: dict[str, tuple[str, ...]] = {
    "debit": ("debit",),
    "credit": ("credit",),
    "weight": ("edge sum", "weight_sum", "weight", "sum"),
    "depth": ("depth", "transaction count", "count"),
}

# Column positions used when the header row does not identify the columns.
FALLBACK_EDGE_COLUMNS = {"debit": 1, "credit": 2, "weight": 3, "depth": 4}

Row = Sequence[object | None]


def _norm(value: object | None) -> str:
    return " ".join(str(value).split()).lower() if value is not None else ""


def resolve_edge_columns(header: Row | None) -> dict[str, int]:
    """Map debit/credit/weight/depth to column indexes on the edge sheet.

    Resolved from the header row where it names the columns, so a workbook whose
    aggregate sits at different offsets still loads. Falls back to the positional
    layout when a header is absent or does not identify every column.
    """
    if not header:
        return dict(FALLBACK_EDGE_COLUMNS)

    cells = [_norm(c) for c in header]
    resolved: dict[str, int] = {}
    for field, hints in EDGE_HEADER_HINTS.items():
        for idx, cell in enumerate(cells):
            if idx in resolved.values() or not cell:
                continue
            if any(hint in cell for hint in hints):
                resolved[field] = idx
                break

    if set(resolved) != set(EDGE_HEADER_HINTS):
        return dict(FALLBACK_EDGE_COLUMNS)
    return resolved


def parse_account_rows(rows: Iterable[Row]) -> dict[str, Account]:
    """Account name in the first column, account type in the second."""
    accounts: dict[str, Account] = {}
    for row in rows:
        if not row or row[0] is None:
            continue
        name = str(row[0]).strip()
        if not name:
            continue
        acct_type = str(row[1]).strip() if len(row) > 1 and row[1] is not None else "Unknown"
        accounts[name] = Account(account_id=name, name=name, account_type=acct_type or "Unknown")
    return accounts


def parse_edge_rows(
    rows: Iterable[Row],
    columns: dict[str, int],
    accounts: dict[str, Account],
) -> dict[EdgeKey, EdgeStat]:
    """Aggregated edges from data rows, skipping ones that carry no usable edge.

    Repeated keys accumulate rather than overwrite, matching the TSV edge loader:
    a workbook may list the same pair on more than one row.
    """
    edges: dict[EdgeKey, EdgeStat] = {}
    width = max(columns.values()) + 1

    for row in rows:
        if not row or len(row) < width:
            continue
        debit_cell, credit_cell = row[columns["debit"]], row[columns["credit"]]
        if debit_cell is None or credit_cell is None:
            continue
        debit, credit = str(debit_cell).strip(), str(credit_cell).strip()
        if not debit or not credit:
            continue

        try:
            weight = float(row[columns["weight"]] or 0)
            depth = int(float(row[columns["depth"]] or 0))
        except (TypeError, ValueError):
            continue
        if weight <= 0 or depth <= 0:
            continue

        key = EdgeKey(debit, credit)
        prior = edges.get(key)
        edges[key] = EdgeStat(
            key=key,
            weight_sum=weight + (prior.weight_sum if prior else 0.0),
            depth=depth + (prior.depth if prior else 0),
            pair_instances=depth + (prior.pair_instances if prior else 0),
        )
        for aid in (debit, credit):
            if aid not in accounts:
                accounts[aid] = Account(account_id=aid, name=aid, account_type="Unknown")

    return edges


def load_excel_reference(
    xlsx_path: Path,
    *,
    window_label: str = "excel_ref",
    edge_sheet: str = DEFAULT_EDGE_SHEET,
    account_sheet: str = DEFAULT_ACCOUNT_SHEET,
) -> LogicMap:
    """Load pre-aggregated edges from a workbook's edge and account-type sheets.

    Reads cached values rather than formulas, so the workbook must have been
    calculated before it was saved.
    """
    try:
        import openpyxl
    except ImportError as exc:
        raise ImportError(
            "openpyxl is required for build-from-excel; pip install openpyxl"
        ) from exc

    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        accounts: dict[str, Account] = {}
        if account_sheet in wb.sheetnames:
            accounts = parse_account_rows(
                wb[account_sheet].iter_rows(min_row=1, values_only=True)
            )

        if edge_sheet not in wb.sheetnames:
            raise ValueError(
                f"workbook has no {edge_sheet!r} sheet "
                f"(found: {', '.join(wb.sheetnames)})"
            )

        rows = list(wb[edge_sheet].iter_rows(min_row=1, values_only=True))
    finally:
        wb.close()

    header = rows[0] if rows else None
    edges = parse_edge_rows(rows[1:], resolve_edge_columns(header), accounts)
    if not edges:
        raise ValueError(f"no usable edges on sheet {edge_sheet!r} of {xlsx_path}")

    logic_map = logic_map_from_edge_stats(
        accounts,
        edges,
        window_label=window_label,
        txn_count=0,
        line_count=0,
    )
    return score_map(logic_map)
