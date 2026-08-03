# Accounting Logic Map

Python proof of concept for the characteristic debit–credit graph described in:

- [`docs/Accounting Logic Map — Concept Definition.md`](docs/Accounting%20Logic%20Map%20—%20Concept%20Definition.md)
- [`docs/Accounting Logic Map — Python Proof Spec.md`](docs/Accounting%20Logic%20Map%20—%20Python%20Proof%20Spec.md)

## Setup

```bash
cd AccountingLogicMap
python -m pip install -e ".[dev]"
```

Or without install: `set PYTHONPATH=src` (and `pip install openpyxl` only if you need `build-from-excel`).

## Demo

Run the full walkthrough — sample verify/predict/anomalies/eval, 25-month periods and seasonality, natural-balance checks, and the reference edge-list build — with commentary on stderr:

```bash
python -m alm demo
```

Artifacts land under `out/`. Optional overrides: `--out`, `--sample`, `--history`, `--reference`.

## Individual commands

```bash
# Sample entity
python -m alm build --accounts data/sample/accounts.tsv --transactions data/sample/transactions.tsv --out out/baseline
python -m alm verify --map out/baseline --candidates data/sample/candidates.tsv --out out/verify
python -m alm predict --map out/baseline --account "1000 Bank" --side debit --top 10
python -m alm anomalies --baseline out/baseline --open out/open --out out/anomalies
python -m alm eval --map out/baseline --out out/eval \
  --candidates data/sample/candidates.tsv --holdout data/sample/holdout.tsv \
  --baseline out/baseline --open-map out/open \
  --expected-anomalies data/sample/expected_anomalies.tsv

# 25-month history (windowed build, forward expectation, seasonal predict, balances)
python -m alm build --accounts data/history/accounts.tsv --transactions data/history/transactions.tsv \
  --to 2024-12-31 --out out/hist/baseline --label closed
python -m alm periods --accounts data/history/accounts.tsv --transactions data/history/transactions.tsv \
  --granularity month --baseline-periods 12 --out out/hist/periods
python -m alm predict --map out/hist/baseline --account "1000 Bank" --side credit --top 10 --season 2025-01
python -m alm balances --accounts data/history/accounts.tsv --transactions data/history/transactions.tsv \
  --min-consecutive 2 --out out/hist/balances

# Reference edge list (parity-pinned scoring; no Excel required)
python -m alm build-from-edges --edges data/reference/reference_edges.tsv \
  --accounts data/reference/reference_accounts.tsv --out out/reference
```

`--granularity` also accepts `quarter` and `year`. Excel workbooks (needs openpyxl): `python -m alm build-from-excel --xlsx <workbook> --out out/excel_ref`.

## Tests

```bash
python -m unittest discover -s tests -v
```

## Outputs

Map directories under `out/` contain `meta.tsv`, `accounts.tsv`, `edges.tsv`, `spectrum.tsv`, `node_activity.tsv`, and (when period data exists) `edge_periods.tsv`. Command-specific TSVs (`verify_results.tsv`, `anomaly_edges.tsv`, `eval_summary.tsv`, …) sit beside them.
