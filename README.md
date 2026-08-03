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

## Excel reference (optional)

```bash
python -m alm build-from-excel --xlsx "docs/Accounting Logic Map test.xlsx" --out out/excel_ref
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Outputs

Map directories under `out/` contain `meta.tsv`, `accounts.tsv`, `edges.tsv`, `spectrum.tsv`, and `node_activity.tsv`. Command-specific TSVs are written beside them (`verify_results.tsv`, `anomaly_edges.tsv`, `eval_summary.tsv`, …).
