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

The baseline keeps 1404 of 1469 lines and reports `24 month period(s) 2023-01 .. 2024-12`.
Because `2025-01` is genuinely outside the map, `data/history/holdout.tsv` is a
real prediction holdout:

```bash
python -m alm eval --map out/hist/baseline --holdout data/history/holdout.tsv --out out/hist/eval
# predict_hit@5_from_debit  [all] hit_rate=1.000  random=0.208  (n=20)
# predict_hit@5_from_credit [all] hit_rate=0.800  random=0.208  (n=20)
```

**2. Per-period activity and forward expectation.** The projection from concept §7,
`Ê(P₁) = mean of the trailing n closed periods`, with the open period's variance
against it:

```bash
python -m alm periods --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --granularity month --baseline-periods 12 --out out/hist/periods
# forward expectation for 2025-01 from trailing 12 closed period(s) 2024-01 .. 2024-12:
#   weight   expected=162497.51  actual=162768.77  variance=+271.26 (+0.2%)
#   txns     expected=29.4       actual=32
```

**3. Seasonal prediction.** Averaging a counterpart distribution over the whole
window buries anything that only happens part of the year. `--season` conditions on
the same month in prior years instead:

```bash
python -m alm predict --map out/hist/baseline --account "1000 Bank" --side credit --top 10
#  8. 6100 Fuel   p=0.019       10. 6400 Office   p=0.010

python -m alm predict --map out/hist/baseline --account "1000 Bank" --side credit --top 10 --season 2025-01
# conditioning on season 2025-01 → periods 2023-01, 2024-01
#  5. 6100 Fuel   p=0.027        6400 Office absent

python -m alm predict --map out/hist/baseline --account "1000 Bank" --side credit --top 10 --season 2025-07
# conditioning on season 2025-07 → periods 2023-07, 2024-07
#  5. 6400 Office  p=0.055       6100 Fuel absent
```

The garage buys bulk heating fuel direct from the bank in winter and season supplies
in summer. Unconditioned, both sit near the bottom of the ranking; conditioned, the
in-season one rises and the out-of-season one drops out entirely.

**4. Natural-balance quality signal.** Does each account's balance sit on the side
its type implies? Contra accounts legitimately do not, so they are inferred rather
than flagged:

```bash
python -m alm balances --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv --min-consecutive 2 --out out/hist/balances
# contra 1510 Accum Depreciation (score 5)
#     - sits opposite its parent '1500 Equipment'
#     - on the credit side in all 25 periods it carried a balance, covering 100% of its life
#     - name matches a known contra form
# WARNING [high] 1010 Bank Payroll (Bank) expects a debit balance,
#                held credit -8607.36 for 6 consecutive period(s) to 2025-01
```

Accumulated Depreciation is a Fixed Asset carrying a credit balance for 25 straight
periods and is *not* reported; the payroll clearing bank went overdrawn after a
short funding transfer and was never trued up, so it is. See §Natural balance in the
concept doc for how the two are told apart.

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
