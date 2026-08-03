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

**Baseline journals that exercise the rewrite**

| Txn | Shape | Why it is there |
|-----|-------|-----------------|
| `T049` | 2 debits × 2 credits | The only shape where DR×CR must *infer* pairings. Creates `6300 Utilities \| 2100 Card` and `6200 Advertising \| 2100 Card` at `ambiguous_share = 1.0`. |
| `T050` | convenience JE: A/R reapplication + a card fee | Touches `1100 AR` on both sides, producing the self-loop edge `1100 AR \| 1100 AR`, plus two textbook false edges (`1100 AR \| 2100 Card`, `6400 Office \| 1100 AR`) that pair lines from the two unrelated halves. |

The rest of the baseline is 1×1 or `(2,1)`, which apportion exactly.

**Injected open-window anomalies**

1. **missing_edge** — no `1000 Bank | 4000 Vehicle Sales` activity (core sales edge disappears).
2. **new_edge / clearing_surge** — large `1200 Clearing | 1000 Bank` postings.
3. **new_edge** — `1000 Bank | 2500 New Floor Plan` financing draw.
