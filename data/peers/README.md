# Peer entity fixtures

Three synthetic consulting firms, for cross-entity comparison and benchmarking
(concept §6.2). They exist to make one point concrete: entities with **no account
identifier in common** are still comparable, because account types are a shared
axis and the map is already expressed in shares.

| Entity | Accounts | Transactions | Scale | How it funds itself |
|--------|----------|--------------|-------|---------------------|
| `alpha` | 10 | 67 | 1× | Revenue through receivables, costs settled from the bank |
| `beta` | 10 | 67 | 2.4× | The same, at more than twice the size |
| `gamma` | 11 | 79 | 0.6× | Costs settled on a credit card, plus an equipment loan |

Each ships `accounts.tsv` and `transactions.tsv` in the standard journal-line
contract, so each builds a normal map with `alm build`.

## What makes them a test rather than a demo

Three things differ between the entities on purpose, because each is an obstacle
a naive comparison would trip over:

- **Account identifiers are disjoint.** `alpha` numbers accounts `1000 Operating
  Account`, `beta` uses `A-CASH Main Bank`, `gamma` uses `101 Checking`. No
  identifier appears in two entities, so nothing can be matched by key.
- **Type labels differ for the same thing.** `alpha` and `gamma` say `Expense`
  where `beta` says `Expenses`. Base groups absorb this; raw type labels do not,
  which is why `--level group` is the default.
- **Scale differs by a factor of four.** `beta` moves more than twice the weight
  of `alpha` and four times that of `gamma`. If the comparison were not
  share-based, size would dominate it.

## Expected result

`alpha` and `beta` run the same way and sit almost on top of each other; `gamma`
sells the same services but funds them differently and separates cleanly:

```text
alpha  vs beta    0.006
gamma  vs alpha   0.121
gamma  vs beta    0.123
```

Benchmarking `gamma` against the other two identifies why, rather than only
reporting that it differs: `Expense ← Liability` is over-weighted, `Expense ←
Asset` is absent entirely, and `Liability ← Asset` is over-weighted by the card
paydowns and loan payments.

```bash
for e in alpha beta gamma; do
  python -m alm build --accounts data/peers/$e/accounts.tsv \
    --transactions data/peers/$e/transactions.tsv --out out/peers/$e --label $e
done
python -m alm benchmark --subject out/peers/gamma \
  --peers out/peers/alpha out/peers/beta --out out/peers/benchmark
```

Pinned by `tests/test_benchmark.py`.
