# Sample entity fixtures

Synthetic used-car / garage books for the Accounting Logic Map proof.

| File | Role |
|------|------|
| `accounts.tsv` | Chart of accounts + types |
| `transactions.tsv` | Baseline window (characteristic sales, COGS, expenses, loan) |
| `transactions_open.tsv` | Open window with injected anomalies |
| `candidates.tsv` | Verify set with `expected_verdict` |
| `holdout.tsv` | Known edges for prediction hit-rate |
| `expected_anomalies.tsv` | Injected signals eval should recover |

**Injected open-window anomalies**

1. **missing_edge** — no `1000 Bank | 4000 Vehicle Sales` activity (core sales edge disappears).
2. **new_edge / clearing_surge** — large `1200 Clearing | 1000 Bank` postings.
3. **new_edge** — `1000 Bank | 2500 New Floor Plan` financing draw.
