# Accounting Logic Map

Python proof of concept for the characteristic debit–credit graph described in:

- [`docs/Accounting Logic Map — Concept Definition.md`](docs/Accounting%20Logic%20Map%20—%20Concept%20Definition.md)
- [`docs/Accounting Logic Map — Python Proof Spec.md`](docs/Accounting%20Logic%20Map%20—%20Python%20Proof%20Spec.md)

Double-entry books form a directed graph of value movement. `alm` rewrites posted
journals into that graph, aggregates it into a ranked signature of the entity, and
puts the signature to three uses:

| Use | Question it answers | Command |
|-----|---------------------|---------|
| Verify | Does this posting fit how the entity has moved value? | `verify` |
| Predict | What is the likely counterpart to a half-known entry? | `predict` |
| Detect | Has the structure of activity changed between two windows? | `anomalies` |

There is no UI and no service dependency. Every command writes TSV artifacts and logs
a summary to stderr. The core runs on the standard library alone.

## Setup

Python 3.10 or later.

```bash
cd AccountingLogicMap
python -m pip install -e ".[dev]"
```

To run without installing, set `PYTHONPATH=src`. Only the optional Excel loader needs
a third-party package, `openpyxl`, available as the `excel` extra.

## Quick start

The demo runs the whole walkthrough end to end — sample verify, predict, anomalies
and eval; 25 months of history with seasonality; natural-balance checks; and the
reference edge-list build — with commentary on stderr:

```bash
python -m alm demo
```

Artifacts land under `out/`. Paths can be overridden with `--out`, `--sample`,
`--history` and `--reference`.

## Commands

### Sample entity

Build a baseline map and an open-window map, then apply the three uses to them. The
open window repeats the baseline pattern with anomalies injected — a new loan edge, a
clearing surge, and a core sales edge that disappears.

```bash
python -m alm build --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions.tsv --out out/baseline
python -m alm build --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions_open.tsv --out out/open

python -m alm verify --map out/baseline --candidates data/sample/candidates.tsv --out out/verify
python -m alm predict --map out/baseline --account "1000 Bank" --side debit --top 10
python -m alm anomalies --baseline out/baseline --open out/open --out out/anomalies

python -m alm eval --map out/baseline --out out/eval \
  --candidates data/sample/candidates.tsv --holdout data/sample/holdout.tsv \
  --baseline out/baseline --open-map out/open \
  --expected-anomalies data/sample/expected_anomalies.tsv
```

`eval` scores the success criteria: verification separation, prediction hit-rate
against a random baseline, and recovery of the anomalies injected into the open
window.

### Periods and balances

A 25-month synthetic ledger exercises the time axis. A baseline is a date-bounded
slice of one ledger, so the same file serves as both closed history and open period.

```bash
# Windowed build: closed months only
python -m alm build --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --to 2024-12-31 --out out/hist/baseline --label closed

# Per-period activity, and the forward expectation for the open period
python -m alm periods --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --granularity month --baseline-periods 12 --out out/hist/periods

# Seasonal prediction: rank against the same month in prior years
python -m alm predict --map out/hist/baseline --account "1000 Bank" \
  --side credit --top 10 --season 2025-01

# Accounts sitting opposite their natural balance, with contra accounts inferred
python -m alm balances --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --min-consecutive 2 --out out/hist/balances
```

`--granularity` accepts `month`, `quarter` and `year`. `build`, `periods` and
`balances` all take `--from` and `--to` as inclusive ISO dates.

### Pre-aggregated edge lists

A map can also be built from edges aggregated elsewhere, which reproduces a
spreadsheet aggregation without needing the journals behind it. The input is one row
per distinct debit–credit pair, carrying both endpoints, the summed weight, and the
contributing transaction depth.

```bash
python -m alm build-from-edges --edges data/reference/reference_edges.tsv \
  --accounts data/reference/reference_accounts.tsv --out out/reference
```

`data/reference/` holds a 190-edge, 82-account entity in that form together with the
expected result for each edge, pinning the scoring arithmetic at a scale the sample
entity does not reach.

The same four values can be read from an Excel workbook carrying an aggregated edge
sheet named `rw` and an account-type sheet named `ca` (needs `openpyxl`):

```bash
python -m alm build-from-excel --xlsx <workbook.xlsx> --out out/excel_ref
```

## Outputs

Each map directory under `out/` contains:

| File | Contents |
|------|----------|
| `meta.tsv` | Window label, counts, global totals, period range |
| `accounts.tsv` | Accounts used, with types |
| `edges.tsv` | One row per distinct edge: weight, depth, the three shares, normed score, rank, ambiguous share, self-loop flag |
| `spectrum.tsv` | The same rows ranked by normed score |
| `node_activity.tsv` | Per-account debit and credit weight, and incident norm |
| `edge_periods.tsv` | Per-period edge mass, written where the source carries dates |

Command results sit beside them: `verify_results.tsv`, `anomaly_edges.tsv`,
`eval_summary.tsv`, `eval_detail.tsv`, `periods.tsv` and `balances.tsv`.

## Tests

```bash
python -m unittest discover -s tests -v
```

70 tests, covering weight conservation through the rewrite, scoring parity against the
reference entity, the three use-case paths, period windowing and seasonal
conditioning, and natural-balance inference.
