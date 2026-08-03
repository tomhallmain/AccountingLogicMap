# Reference entity fixture

A synthetic reference entity: 190 distinct edges over an 82-account chart, at a
scale the small sample in `data/sample/` does not reach. Account labels are
structural placeholders (`1001 Bank 1`, `4001 Income 1`, …) carrying their
account type, which is all the type-pair logic needs.

| File | Contents |
|------|----------|
| `reference_accounts.tsv` | `account_id`, `name`, `account_type` |
| `reference_edges.tsv` | aggregated edges plus the expected results for each |

## `reference_edges.tsv`

| Column | Meaning |
|--------|---------|
| `debit_account_id` / `credit_account_id` | Edge endpoints |
| `weight_sum` | Total rewritten weight on the edge |
| `depth` | Contributing transactions |
| `expected_norm` | Normed blend for that edge |
| `expected_p_from_debit` | Conditional probability given the debit node (3dp) |
| `expected_p_from_credit` | Conditional probability given the credit node (3dp) |

## Expected globals

Derivable from `weight_sum` and `depth`, and asserted by the parity test:

```text
total_weight       = 6007237.44      Σ weight_sum
total_depth        = 2241            Σ depth
total_mean_weight  = 1453364.406     Σ (weight_sum / depth)
```

The normed blend is `average(w/total_weight, c/total_depth, (w/c)/total_mean_weight)` —
three shares, each summing to 1 across edges. Note `total_mean_weight` is **not**
`total_weight / total_depth`; see `alm.aggregate.map_globals`.

## Caveat

The placeholder labels carry no name-based signal, so this fixture exercises the
arithmetic (rewrite → aggregate → score → predict), not the clearing /
uncategorised heuristics in `anomalies.CLEARING_HINTS`.
