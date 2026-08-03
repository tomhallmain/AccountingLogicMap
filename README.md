# Accounting Logic Map

Python proof of concept for the characteristic debit–credit graph described in:

- [`docs/Accounting Logic Map — Concept Definition.md`](docs/Accounting%20Logic%20Map%20—%20Concept%20Definition.md)
- [`docs/Accounting Logic Map — Python Proof Spec.md`](docs/Accounting%20Logic%20Map%20—%20Python%20Proof%20Spec.md)

## Setup

```bash
cd AccountingLogicMap
python -m pip install -e ".[dev]"
```

Or without install:

```bash
set PYTHONPATH=src
pip install openpyxl   # only needed for build-from-excel
```

## Run the proof (sample entity)

```bash
python -m alm build --accounts data/sample/accounts.tsv --transactions data/sample/transactions.tsv --out out/baseline
python -m alm build --accounts data/sample/accounts.tsv --transactions data/sample/transactions_open.tsv --out out/open --label open

python -m alm verify --map out/baseline --candidates data/sample/candidates.tsv --out out/verify
python -m alm predict --map out/baseline --account "1000 Bank" --side debit --top 10
python -m alm anomalies --baseline out/baseline --open out/open --out out/anomalies

python -m alm eval --map out/baseline --out out/eval ^
  --candidates data/sample/candidates.tsv ^
  --holdout data/sample/holdout.tsv ^
  --baseline out/baseline --open-map out/open ^
  --expected-anomalies data/sample/expected_anomalies.tsv
```

On PowerShell, use backticks for line continuation instead of `^`.

## Periods (25-month history)

`data/history/` is a 25-month synthetic ledger — long enough for period averaging
to mean anything. Two worked examples:

**1. Windowed build.** One ledger, sliced into a closed baseline and an open
period, instead of two hand-curated files. Bounds are inclusive ISO dates:

```bash
python -m alm build --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --to 2024-12-31 --out out/hist/baseline --label closed

python -m alm build --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --from 2025-01-01 --out out/hist/open --label open
```

The baseline keeps 1172 of 1217 lines and reports `24 month period(s) 2023-01 .. 2024-12`.
Because `2025-01` is genuinely outside the map, `data/history/holdout.tsv` is a
real prediction holdout:

```bash
python -m alm eval --map out/hist/baseline --holdout data/history/holdout.tsv --out out/hist/eval
# predict_hit@5_from_debit  [all] hit_rate=1.000  random=0.263
# predict_hit@5_from_credit [all] hit_rate=0.923  random=0.263
```

**2. Per-period activity and forward expectation.** The projection from concept §7,
`Ê(P₁) = mean of the trailing n closed periods`, with the open period's variance
against it:

```bash
python -m alm periods --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --granularity month --baseline-periods 12 --out out/hist/periods
# forward expectation for 2025-01 from trailing 12 closed period(s) 2024-01 .. 2024-12:
#   weight   expected=141058.44  actual=111956.49  variance=-29101.95 (-20.6%)
#   txns     expected=23.3       actual=22
```

`--granularity` also accepts `quarter` and `year`.

## Reference entity

`data/reference/` ships a synthetic reference entity — an aggregated edge list at
larger scale than `data/sample/` (190 edges, 82 accounts), together with the
expected norm and probability values for every edge.
`tests/test_reference_parity.py` asserts the pipeline reproduces them, which is
what pins the scoring chain.

Build a map straight from it — no Excel, no raw journals:

```bash
python -m alm build-from-edges --edges data/reference/reference_edges.tsv \
  --accounts data/reference/reference_accounts.tsv --out out/reference
# 190 distinct edges; total_weight=6007237.44 total_depth=2241
# WARNING 5 self-loop edge(s) carry 18.4% of weight — rewrite artifacts, not value flows
```

An Excel edge list can also be loaded directly, if you have one:

```bash
python -m alm build-from-excel --xlsx <workbook> --out out/excel_ref   # needs openpyxl
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Outputs

Map directories under `out/` contain `meta.tsv`, `accounts.tsv`, `edges.tsv`, `spectrum.tsv`, and `node_activity.tsv`. Command-specific TSVs are written beside them (`verify_results.tsv`, `anomaly_edges.tsv`, `eval_summary.tsv`, …).
