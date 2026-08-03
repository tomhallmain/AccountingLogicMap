# History fixture — 25 months

Synthetic garage books spanning **2023-01 … 2025-01**: 605 transactions, 1251
lines, 19 accounts. Generated deterministically.

`data/sample/` is deliberately small and exists to exercise specific corner cases
(self-loops, ambiguous pairings, verify verdicts, injected anomalies). Three
months is far too short for period averaging to say anything — a mean over three
observations has no useful variance to read against. This fixture exists so the
period work in concept §7 is demonstrated on a history long enough for it to mean
something.

| File | Role |
|------|------|
| `accounts.tsv` | Same chart of accounts as `data/sample/` |
| `transactions.tsv` | 25 months of journal lines |
| `holdout.tsv` | Edges from the open month (2025-01), for prediction eval |

## Shape of the data

Each month contains a repeating operating pattern, so period statistics are
comparable across the series:

- 2–4 cash vehicle sales, each with its cost of sale
- usually one credit sale (`1100 AR` → settled from `1000 Bank` about 9 days later)
- 1–3 inventory acquisitions on the floor plan
- 1–3 parts sales with matching parts cost
- fixed monthly rent, utilities, and a card payment
- a floor-plan payment as a `(2,1)` journal — principal + interest against bank
- 2–4 fuel and 1–2 office charges on the card
- a `2×2` quarter-end split in March, June, September and December
- an occasional owner contribution

Overlaid on that: a mild upward trend (~1.2% per month) and a seasonal lift in
March–August, so the forward expectation has real variance to report rather than
noise around a flat line.

**Seasonal edges.** Amount seasonality alone would not exercise `predict --season`,
since the same counterparts appear either way. Two edges therefore occur in one
season only:

| Edge | Months | Story |
|------|--------|-------|
| `6100 Fuel \| 1000 Bank` | Dec, Jan, Feb | bulk heating / plow fuel delivered and paid direct |
| `6400 Office \| 1000 Bank` | Jun, Jul, Aug | season supplies paid direct |

Both accounts otherwise settle against the card, so the seasonal edge is genuinely
distinct rather than an amount shift. Utilities also run high in winter and low in
summer. The open month, `2025-01`, is a winter month — so the winter edge is in the
holdout.

## Closed / open split

The last month, **2025-01**, is the open period. Builds for the baseline exclude
it:

```bash
python -m alm build --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --to 2024-12-31 --out out/hist/baseline --label closed
```

`holdout.tsv` is the set of distinct edges produced by the 24 transactions in
2025-01 — transactions the baseline map has never seen. That is what makes the
prediction hit-rate a generalisation measure.

Note that all 15 holdout edge types also occur in the baseline. **This is not
leakage.** A going concern repeats its edges every month; that recurrence is
precisely the regularity the map claims to capture. What makes the holdout honest
is that the *transactions* were excluded, which `tests/test_periods.py` asserts
directly by comparing transaction ids.
