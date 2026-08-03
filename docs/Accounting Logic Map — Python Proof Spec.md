# Accounting Logic Map — Python Proof Spec

**Companion to:** [`Accounting Logic Map — Concept Definition.md`](./Accounting%20Logic%20Map%20%E2%80%94%20Concept%20Definition.md)

**Purpose.** Specify how to prove the concept in Python: package layout, data contracts, algorithms, CLI surface, TSV outputs, evaluation harness, and an ordered build plan. Prefer a small stdlib-first CLI with optional `openpyxl` only for loading the reference Excel edge list.

---

## 1. Claim under test

Given balanced journal lines for an entity, a Python pipeline can:

1. Rewrite transactions into aggregated DR→CR edges and a ranked characteristic spectrum.
2. **Verify** candidate postings against that spectrum (explainable pass / warn / fail).
3. **Predict** likely counterpart accounts from a partial observation.
4. **Detect** structural anomalies between a baseline window and an open window.

UI is out of scope: terminal logs + TSV artifacts only.

---

## 2. Non-goals (v1)

- Minimal exact-cover JE splitter (averaging rewrite only).
- Contacts, multi-currency, inventory lots, accrual chain reconstruction.
- Training neural models; all scores are deterministic graph statistics.
- Replacing the general ledger or posting into QBO/Xero.
- Dense square Excel-style matrices on disk (use sparse long-form TSV instead).

---

## 3. Tech choices

| Choice | Decision |
|--------|----------|
| Language | Python 3.10+ |
| Dependencies | stdlib for core; `openpyxl` optional, for the Excel edge-list path |
| Packaging | `src/alm/` package + `python -m alm` entry |
| Tests | `unittest` or `pytest` (either fine; keep tests fast and deterministic) |
| Config | CLI flags; no YAML required for v1 |
| Logging | `logging` to stderr; progress + summaries; never dump full matrices to the console |

---

## 4. Repository layout

```text
AccountingLogicMap/
  docs/
    Accounting Logic Map — Concept Definition.md
    Accounting Logic Map — Python Proof Spec.md   # this file
  data/
    sample/
      accounts.tsv          # account_id, name, account_type
      transactions.tsv      # journal lines (baseline)
      transactions_open.tsv # optional open-window lines
      candidates.tsv        # transactions for verify
      holdout.tsv           # edges for prediction eval
      expected_anomalies.tsv
    reference/              # larger reference entity + expected results
      reference_accounts.tsv
      reference_edges.tsv
  src/alm/
    __init__.py
    __main__.py             # python -m alm
    cli.py
    models.py               # dataclasses
    validate.py             # balance / axiom checks
    rewrite.py              # DR×CR averaging
    aggregate.py            # edge collapse + globals
    score.py                # normed spectrum
    verify.py
    predict.py
    anomalies.py
    io_tsv.py
    io_excel.py             # optional
  out/                      # gitignored generated TSV + logs
  tests/
    test_rewrite.py
    test_aggregate.py
    test_verify_predict.py
    test_anomalies.py
    test_reference_parity.py
    test_eval_outputs.py
  requirements.txt          # openpyxl optional extra, or note in README
  README.md                 # how to run the proof
```

---

## 5. Data contracts

All TSV: UTF-8, tab-separated, header row, `.` decimal, ISO dates `YYYY-MM-DD`.

### 5.1 `accounts.tsv`

| Column | Type | Notes |
|--------|------|--------|
| `account_id` | str | Stable key (may equal name if no code) |
| `name` | str | Display name |
| `account_type` | str | e.g. Bank, Expense, Income, … |

### 5.2 `transactions.tsv` (journal lines)

| Column | Type | Notes |
|--------|------|--------|
| `txn_id` | str | Groups lines into one transaction |
| `date` | date | Posted date |
| `account_id` | str | FK → accounts |
| `side` | `debit` \| `credit` | |
| `amount` | float | Strictly `> 0` |
| `memo` | str | Optional; ignored by v1 math |

**Invariants (reject or skip with error log):**

- Each `txn_id` has ≥1 debit and ≥1 credit.
- Per `txn_id`, `sum(debit amounts) == sum(credit amounts)` within tolerance `1e-6` (configurable).
- Unknown `account_id` → error (do not invent accounts).

### 5.3 Pre-aggregated edges (optional Excel / TSV path)

For parity with the workbook without raw journals:

| Column | Maps to |
|--------|---------|
| `debit_account` | Re-Split Debit Node |
| `credit_account` | Re-Split Credit Node |
| `edge_sum` | Edge Sum |
| `depth` | Edge Transaction Depth |

`build-from-excel` reads the same shape from an Excel workbook's aggregated-edge sheet (+ an account-type sheet) when `openpyxl` is installed. `data/reference/` is the TSV equivalent.

---

## 6. Domain objects

```text
Account(account_id, name, account_type)
Line(txn_id, date, account_id, side, amount)
Transaction(txn_id, date, lines[])          # validated balanced
EdgeKey(debit_account_id, credit_account_id)
EdgeStat(key, weight_sum, depth, ...)       # depth = # contributing txns (≥1 pair emitted)
LogicMap(
  accounts,
  edges: dict[EdgeKey, EdgeStat],
  total_weight,
  total_depth,
  total_mean_weight,                        # Σ (weight_sum / depth); see §7.4
  window_label
)
```

Sparse matrices are views over `edges`, not separate dense arrays.

---

## 7. Algorithms

### 7.1 Validate

For each `txn_id`, enforce axioms from the concept doc §3.2 (lines, sides, positive amounts, balance). Emit structured errors; fail the build command if any baseline txn is invalid (candidates may be reported instead of aborting—see verify).

### 7.2 Rewrite (exact-cover averaging)

For each valid transaction with total weight \(W\):

\[
w(dr_j, cr_k) = \frac{w(dr_j)\,w(cr_k)}{W}
\]

Emit one weighted pair per DR×CR combination. Proof: \(\sum_{j,k} w(dr_j,cr_k) = W\).

Unit tests must cover: 2-line, 2×2, unbalanced rejection, weight conservation.

### 7.3 Aggregate

Collapse by `EdgeKey`:

- `weight_sum +=` rewritten weight  
- `depth += 1` per **transaction** that produced that edge (not per pair instance inside one txn—document this choice in code comments; matches “transaction depth” in the workbook spirit)

Globals (`aggregate.map_globals`):

- `total_weight = sum(weight_sum)`
- `total_depth = sum(depth)`
- `total_mean_weight = sum(weight_sum / depth for edges with depth > 0)`

### 7.4 Normed edge score

Per edge (mirror the prototype blend). Each term is a **share of its own global
total**, so all three are on the same scale and each sums to 1 across edges:

```text
s_w = weight_sum / total_weight
s_c = depth / total_depth
s_m = (weight_sum / depth) / total_mean_weight
norm = average(s_w, s_c, s_m)           # skip terms safely if denominators 0
```

Rank edges by `norm` descending → characteristic spectrum.

> **Do not** use `total_weight / total_depth` as the `s_m` denominator. It is the
> global mean weight per instance, not a normalizing total; on the reference
> entity it is ≈542× smaller than `total_mean_weight`, which makes `s_m` an
> unbounded ratio that swamps the other two terms. Symptom: `norm > 1`.
> Covered by `tests/test_reference_parity.py`.

Optional account-level score: sum of incident edge norms (or max); used for “hot accounts” log lines.

### 7.5 Verify

Input: `LogicMap` + candidate transaction(s).

1. Validate balance; unbalanced → `fail` reason `unbalanced`.
2. Rewrite to edges.
3. For each edge, compute:
   - `seen`: key in map
   - `weight_percentile` / rank among edges (or share of node activity)
   - `type_pair`: `(B(dr), B(cr))`
   - heuristics:
     - unseen + uncommon type pair → warn/fail
     - unseen + common type pair (e.g. Expense←Bank) → warn soft
     - seen + top-quartile for either node → pass support
4. Aggregate edge findings → transaction verdict: `pass` | `warn` | `fail` with bullet reasons.

Keep thresholds as named constants (e.g. `RARE_EDGE_RANK_FRAC = 0.9`) so evaluation can tune without redesign.

### 7.6 Predict

Input: `account_id`, `side` (`debit`|`credit`), optional `amount`, optional `top_k`.

- If `side=debit`: rank credit counterparts among edges with that debit account by `weight_sum` (and report `depth`, `norm`, type).
- If `side=credit`: rank debit counterparts symmetrically.
- Probabilities = counterpart weight / sum(weights on that node-side).
- If `amount` given, annotate typical mean (`weight_sum/depth`) distance (log only; no hard filter required in v1).

### 7.7 Anomalies (baseline vs open)

Build two maps: `baseline`, `open`.

Emit ranked structural deltas:

| Signal | Definition |
|--------|------------|
| `new_edge` | in open, not in baseline |
| `missing_edge` | in baseline top-N, absent or near-zero in open |
| `rank_shift` | large change in norm rank / share |
| `clearing_surge` | edges involving accounts whose name/type looks Uncategorized/Clearing/Discrepancy (simple substring / type rules) |

Sort by absolute Δ share of total weight (or Δ norm). Log top K; write full table to TSV.

---

## 8. CLI surface

```text
python -m alm build \
  --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions.tsv \
  --out out/baseline

python -m alm build \
  --accounts ... --transactions data/sample/transactions_open.tsv \
  --out out/open

python -m alm build-from-excel \
  --xlsx <workbook> \
  --out out/excel_ref

python -m alm verify \
  --map out/baseline \
  --candidates data/sample/candidates.tsv \
  --out out/verify

python -m alm predict \
  --map out/baseline \
  --account "1000 Bank" \
  --side credit \
  --top 10

python -m alm anomalies \
  --baseline out/baseline \
  --open out/open \
  --out out/anomalies \
  --top 25

python -m alm eval \
  --map out/baseline \
  --holdout data/sample/holdout.tsv \
  --out out/eval
```

`build` writes the map directory; other commands read it.

---

## 9. Map directory + TSV artifacts

Each `--out <dir>` from `build` contains:

| File | Contents |
|------|----------|
| `meta.tsv` | window label, txn count, line count, edge count, totals, generated_at |
| `accounts.tsv` | copy/normalized accounts used |
| `edges.tsv` | debit_id, credit_id, weight_sum, depth, mean_weight, share_w, share_c, norm, rank |
| `spectrum.tsv` | same as edges sorted by norm (or top slice); convenience |
| `node_activity.tsv` | account_id, as_debit_weight, as_credit_weight, incident_norm |

Command outputs:

| Command | Extra TSVs |
|---------|------------|
| `verify` | `verify_results.tsv` — txn_id, verdict, reasons, edge details (one row per candidate edge or JSON-ish reasons column) |
| `predict` | stdout table; optional `--out predict.tsv` |
| `anomalies` | `anomaly_edges.tsv` |
| `eval` | `eval_summary.tsv`, `eval_detail.tsv` |

`eval_summary.tsv` holds heterogeneous metric rows (verify, predict, anomaly),
each family carrying different keys. Its header must be the **union** of keys
across all rows; deriving it from the first row alone blanks every column that
row happens to lack.

Console: short banner, counts, top 10 spectrum edges, and command-specific highlights. No full matrix dumps.

---

## 10. Sample data requirements

Ship a **small synthetic entity** (≈15–30 accounts, ≈40–80 txns) that includes:

- Common edges: Bank↔Sales, Expense←Bank, Expense←Card, A/R↔Revenue, A/P↔Expense, loan payment.
- At least one 3+ line journal to exercise averaging.
- `candidates.tsv`: mix of normal, rare-but-valid type, and deliberately absurd pairs.
- `transactions_open.tsv`: baseline pattern **plus** injected anomalies (new loan edge, clearing surge, missing core sales edge).
- Optional `holdout.tsv`: true counterparts for prediction eval.

Separately, `data/reference/` ships a synthetic reference entity (190 edges, 82
accounts) with the expected norm and probability values for every edge. It
proves scale without needing raw journals, and is the parity contract for §7.4 —
see `data/reference/README.md`.

---

## 11. Evaluation (`alm eval`) — success criteria

Automate the concept doc §10 checks as much as possible.

### 11.1 Verification

On labeled candidates (`expected_verdict` column optional):

- Normal held-out / in-pattern txns → majority `pass` (or `warn` only for thin depth).
- Absurd type pairs → majority `fail` or hard `warn`.
- Report precision-style summary in `eval_summary.tsv`.

### 11.2 Prediction

For each holdout edge `(dr, cr)`:

- Condition on debit → check credit rank ≤ K (default K=3 and K=5).
- Condition on credit → check debit rank ≤ K.
- Baselines: uniform random among accounts; optional type-only prior if implemented.
- **Pass bar (demo):** hit-rate@5 clearly above random on frequent edges (depth ≥ 3 in map).

Because the pass bar is stated only for frequent edges, `eval` must report two
cohorts and label them in a `cohort` column:

| Cohort | Membership |
|--------|------------|
| `all` | every holdout edge |
| `frequent` | holdout edges whose map depth ≥ `PREDICT_FREQUENT_DEPTH` (3) |

A cohort with no members reports `n=0` and `above_random=False` — never a
vacuous pass.

**Holdout independence.** Hit-rate only measures generalisation if the holdout
edges were excluded from the map. When every holdout edge is already present,
the number measures recall of learned edges; `eval` logs a warning in that case.
The shipped `data/sample/holdout.tsv` is in exactly that state — see §17.

### 11.3 Anomalies

Given open window with known injected signals, top-25 anomaly list must include those injections (document the expected IDs in `data/sample/README` or eval fixtures).

### 11.4 Scale smoke

`build-from-excel` completes without OOM, writes `edges.tsv` with non-zero counts, logs top edges. No accuracy claim vs Excel formulas beyond “same edge keys and comparable sums” if a golden compare is added later.

---

## 12. Logging conventions

```text
INFO  build: loaded N accounts, M lines, T transactions
INFO  build: rewrite ok; conserved weight within tol
INFO  build: E distinct edges; total_weight=... total_depth=...
INFO  spectrum top:
        1. DR | CR   weight=... depth=... norm=...
        ...
INFO  wrote out/baseline/*.tsv
```

Errors for invariant breaks include `txn_id` and amounts. Use `WARNING` for skipped optional files / missing openpyxl.

---

## 13. Testing plan

Tests live under `tests/` and are part of the proof (not optional).

| Test module | Must prove |
|-------------|------------|
| `test_rewrite` | Weight conservation; 2-line identity; 2×2 four edges; reject unbalanced |
| `test_aggregate` | Collapse sums/depths; globals; norm ranking order on tiny fixture |
| `test_verify_predict` | Known edge → pass; nonsense → fail/warn; predict top contains fixture counterpart |
| `test_anomalies` | Injected new/missing edges appear in anomaly output |
| `test_reference_parity` | Globals, normed blend, and predict probabilities match the spreadsheet prototype on `data/reference/` |
| `test_eval_outputs` | `eval_summary.tsv` keeps every metric family's columns; predict cohorts computed |

Run: `python -m unittest discover -s tests -v`

Optional smoke: Excel loader via `build-from-excel` when openpyxl is installed (covered in README e2e, not a hard CI dependency).

---

## 14. Build plan (implementation todos)

Ordered work matching the proof; each step should leave the CLI runnable for what’s done so far.

1. **Core rewrite + aggregation + scoring**  
   `models`, `validate`, `rewrite`, `aggregate`, `score` + unit tests.

2. **Sample journal data + loaders**  
   `data/sample/*`, `io_tsv`, optional `io_excel` for `rw`/`ca`.

3. **CLI `build` + terminal logs + TSV writers**  
   `cli` / `__main__`, `out/` artifacts from §9.

4. **`verify`, `predict`, `anomalies` commands**  
   Implement §7.5–7.7 and their TSV/log output.

5. **End-to-end run + `eval` success checks**  
   Scripted path: build baseline → build open → verify → predict → anomalies → eval; document expected results in README.

---

## 15. README acceptance checklist

A reviewer can prove the concept by:

```text
pip install -e .          # or PYTHONPATH=src
python -m alm build --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions.tsv --out out/baseline
python -m alm verify --map out/baseline --candidates data/sample/candidates.tsv --out out/verify
python -m alm predict --map out/baseline --account <id> --side credit --top 10
python -m alm anomalies --baseline out/baseline --open out/open --out out/anomalies
python -m alm eval --map out/baseline --holdout data/sample/holdout.tsv --out out/eval
```

and seeing terminal summaries plus TSVs that match §9–§11.

---

## 16. Definition of done

- [ ] Sample entity builds a non-empty spectrum from journal lines.
- [ ] Excel reference path builds from `rw` when openpyxl is available.
- [ ] Verify / predict / anomalies commands produce explainable terminal + TSV output.
- [ ] `eval` reports verification separation, prediction hit-rate@K above random on frequent edges, and recovery of injected anomalies.
- [ ] Tests cover rewrite conservation and the three use-case smoke paths.
- [ ] No UI; no required services; concept definition remains the behavioral source of truth.

---

## 17. Later extensions (do not block v1)

- Minimal transaction splitter before rewrite.  
- Type-pair prior matrix from concept tables.  
- Period-aware maps and seasonality in predict.  
- Contact-conditioned edges.  
- A genuinely held-out prediction fixture. `data/sample/holdout.tsv` currently
  contains only edges that are also in the baseline, so §11.2's hit-rate reports
  recall rather than generalisation (asserted in `test_eval_outputs` so the note
  cannot go stale).

Done, previously listed here: golden numeric compare against the prototype's
aggregated sums — now `tests/test_reference_parity.py`.
