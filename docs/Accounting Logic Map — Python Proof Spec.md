# Accounting Logic Map — Python Proof Spec

**Companion to:** [`Accounting Logic Map — Concept Definition.md`](./Accounting%20Logic%20Map%20%E2%80%94%20Concept%20Definition.md)

**Purpose.** Specify how to prove the concept in Python: package layout, data contracts, algorithms, CLI surface, TSV outputs, evaluation harness, and module responsibilities. The implementation is a small stdlib-first CLI, with `openpyxl` required only for reading pre-aggregated edges out of an Excel workbook.

---

## 1. Claim under test

Given balanced journal lines for an entity, a Python pipeline can:

1. Rewrite transactions into aggregated DR→CR edges and a ranked characteristic spectrum.
2. **Verify** candidate postings against that spectrum, with an explainable pass / warn / fail verdict.
3. **Predict** likely counterpart accounts from a partial observation.
4. **Detect** structural anomalies between a baseline window and an open window.

UI is out of scope: terminal logs and TSV artifacts only.

---

## 2. Non-goals (v1)

- Minimal exact-cover journal splitter; the averaging rewrite only.
- Contacts, multi-currency, inventory lots, accrual chain reconstruction.
- Trained models of any kind; all scores are deterministic graph statistics.
- Replacing the general ledger or posting into QBO or Xero.
- Dense square Excel-style matrices on disk; sparse long-form TSV instead.

---

## 3. Tech choices

| Choice | Decision |
|--------|----------|
| Language | Python 3.10+ |
| Dependencies | stdlib for core; `openpyxl` optional, for the Excel edge-list path |
| Packaging | `src/alm/` package with a `python -m alm` entry point |
| Tests | `unittest`, run via `python -m unittest discover -s tests`; fast and deterministic |
| Config | CLI flags; no configuration file in v1 |
| Logging | `logging` to stderr, carrying progress and summaries; never full matrix dumps to the console |

---

## 4. Repository layout

```text
AccountingLogicMap/
  pyproject.toml
  requirements.txt
  README.md                 # how to run the proof
  docs/
    Accounting Logic Map — Concept Definition.md
    Accounting Logic Map — Python Proof Spec.md   # this file
  data/
    sample/
      README.md
      accounts.tsv          # account_id, name, account_type
      transactions.tsv      # journal lines (baseline)
      transactions_open.tsv # open-window lines with injected anomalies
      candidates.tsv        # transactions for verify
      holdout.tsv           # edges for prediction eval
      expected_anomalies.tsv
    reference/              # larger reference entity + expected results
      README.md
      reference_accounts.tsv
      reference_edges.tsv
    history/                # 25-month synthetic ledger for period work
      README.md
      accounts.tsv
      transactions.tsv
      holdout.tsv           # edges from the open month, excluded from the baseline
  src/alm/
    __init__.py
    __main__.py             # python -m alm
    cli.py
    models.py               # dataclasses + tuning constants
    validate.py             # balance / axiom checks
    rewrite.py              # DR×CR averaging
    aggregate.py            # edge collapse + globals
    score.py                # normed spectrum
    verify.py
    predict.py
    anomalies.py
    eval.py                 # success-criteria metrics
    io_tsv.py
    io_excel.py             # optional
    periods.py              # period keys, windowing, forward expectation
    balances.py             # natural balance + contra inference
  out/                      # gitignored generated TSV + logs
  tests/
    __init__.py
    test_rewrite.py
    test_aggregate.py
    test_verify_predict.py
    test_anomalies.py
    test_reference_parity.py
    test_eval_outputs.py
    test_periods.py
    test_balances.py
```

---

## 5. Data contracts

All TSV: UTF-8, tab-separated, header row, `.` decimal separator, ISO dates `YYYY-MM-DD`.

### 5.1 `accounts.tsv`

| Column | Type | Notes |
|--------|------|--------|
| `account_id` | str | Stable key; may equal the name where no code exists |
| `name` | str | Display name |
| `account_type` | str | Bank, Expense, Income, and so on |

### 5.2 `transactions.tsv` (journal lines)

| Column | Type | Notes |
|--------|------|--------|
| `txn_id` | str | Groups lines into one transaction |
| `date` | date | Posted date |
| `account_id` | str | FK → accounts |
| `side` | `debit` \| `credit` | |
| `amount` | float | Strictly `> 0` |
| `memo` | str | Optional; ignored by v1 math |

**Invariants (reject or skip with an error log):**

- Each `txn_id` has at least one debit and one credit.
- Per `txn_id`, `sum(debit amounts) == sum(credit amounts)` within tolerance `1e-6` (configurable).
- Unknown `account_id` is an error; accounts are never invented.

### 5.3 Pre-aggregated edges (TSV or Excel path)

A map can be built from an already-aggregated edge list, which allows a spreadsheet aggregation to be reproduced without access to the raw journals behind it. The minimum shape is four columns:

| Column | Meaning |
|--------|---------|
| `debit_account` | Debit endpoint of the edge |
| `credit_account` | Credit endpoint of the edge |
| `edge_sum` | Total rewritten weight on the edge |
| `depth` | Contributing transaction count |

`build-from-edges` reads this as TSV with no third-party dependency; `data/reference/` ships an entity in exactly that form, with expected results per edge. The loader accepts both the export and map-directory column namings, and accumulates repeated keys rather than overwriting them.

**Excel form.** `build-from-excel` reads the same four values out of a workbook when `openpyxl` is installed. It expects two sheets:

| Sheet | Extracted as |
|-------|--------------|
| `rw` | One aggregated edge per row from row 2 down: debit endpoint, credit endpoint, edge sum, and depth in columns B–E. Rows with a missing endpoint, a non-positive sum, or zero depth are skipped. |
| `ca` | An account-type lookup, account name in column A and type in column B. Accounts appearing only on `rw` are admitted with type `Unknown`. |

Cached values are read, not formulas, so the workbook must have been calculated before export. Any further columns on the edge sheet are ignored; concept §8 records which of them the concept accounts for.

---

## 6. Domain objects

```text
Account(account_id, name, account_type)
Line(txn_id, date, account_id, side, amount)
Transaction(txn_id, date, lines[])          # validated balanced
EdgeKey(debit_account_id, credit_account_id)
EdgeKey.is_self_loop                        # debit_account_id == credit_account_id
EdgeStat(key, weight_sum, depth,            # depth = # contributing txns (≥1 pair emitted)
         pair_instances,                    # DR×CR emissions; > depth means multi-line sources
         ambiguous_weight,                  # weight from journals with >1 line on BOTH sides
         period_weights, period_depths)     # per-period mass; sums back to weight_sum/depth
ScoredEdge(key, weight_sum, depth, mean_weight,
           share_w, share_c, share_m, norm, rank,
           ambiguous_share, is_self_loop)
LogicMap(
  accounts,
  edges: dict[EdgeKey, EdgeStat],
  total_weight,
  total_depth,
  total_mean_weight,                        # Σ (weight_sum / depth); see §7.4
  window_label,
  granularity, periods,                     # period axis carried with the map
  txn_count, line_count,
  scored: list[ScoredEdge]                  # populated by score.score_map
)
```

Command results reuse a second set of records: `EdgeFinding` and `VerifyResult` (§7.5), `PredictRow` (§7.6), and `AnomalyRow` (§7.7).

Tuning constants live in `models.py` so that evaluation can adjust them without redesign: `BALANCE_TOLERANCE`, `RARE_EDGE_RANK_FRAC`, `PREDICT_DEFAULT_TOP_K`, `PREDICT_FREQUENT_DEPTH`, `ANOMALY_DEFAULT_TOP_K`, `EVAL_HIT_K`, `DEFAULT_BASELINE_PERIODS`, and the anomaly thresholds in §7.7.

Sparse matrices are views over `edges`, not separate dense arrays.

---

## 7. Algorithms

### 7.1 Validate

For each `txn_id`, enforce the axioms from concept §3.2: line counts, sides, positive amounts, balance. Emit structured errors and fail the build command if any baseline transaction is invalid. Candidates are reported rather than aborting the run; see §7.5.

### 7.2 Rewrite (exact-cover averaging)

For each valid transaction with total weight $W$:

$$
w(dr_j, cr_k) = \frac{w(dr_j)\,w(cr_k)}{W}
$$

Emit one weighted pair per DR×CR combination. Conservation follows: $\sum_{j,k} w(dr_j,cr_k) = W$.

Two properties of the product need explicit handling downstream:

- **Self-loops.** Where one account appears on both sides, an `(a, a)` edge is emitted.
  Keep it, since conservation depends on the full product, and flag it via
  `EdgeKey.is_self_loop`. Concept §3.3.1 explains why it is never a posting.
- **Pairing ambiguity.** `has_ambiguous_pairing(txn)` is true only when both sides
  have more than one line. An `(n,1)` journal apportions exactly
  (`w(dr_j, cr_1) = w(dr_j)`), so it involves no estimation. Only the many-to-many
  case can introduce a pair that was never posted, and its weight accumulates into
  `EdgeStat.ambiguous_weight`.

Unit tests cover 2-line, 2×2, unbalanced rejection, weight conservation, self-loop
emission, and the `(n,1)`-is-not-ambiguous boundary.

### 7.3 Aggregate

Collapse by `EdgeKey`:

- `weight_sum +=` rewritten weight
- `depth += 1` per **transaction** that produced that edge, not per pair instance inside one transaction. This choice is documented in code comments and matches the transaction-depth definition used by the spreadsheet prototype.
- `pair_instances += 1` per emitted pair
- `ambiguous_weight +=` rewritten weight where the source journal had more than one line on both sides

`ambiguous_share = ambiguous_weight / weight_sum` is the per-edge confidence signal. A value of 0 means every contributing pairing was fixed by the journals; a value of 1 means the edge exists only because the rewrite paired lines that may never have been related.

Globals (`aggregate.map_globals`):

- `total_weight = sum(weight_sum)`
- `total_depth = sum(depth)`
- `total_mean_weight = sum(weight_sum / depth for edges with depth > 0)`

### 7.4 Normed edge score

Per edge, mirroring the prototype blend. Each term is a **share of its own global
total**, so all three are on the same scale and each sums to 1 across edges:

```text
s_w = weight_sum / total_weight
s_c = depth / total_depth
s_m = (weight_sum / depth) / total_mean_weight
norm = average(s_w, s_c, s_m)           # terms with a zero denominator are skipped
```

Rank edges by `norm` descending to obtain the characteristic spectrum.

> **Do not** use `total_weight / total_depth` as the `s_m` denominator. That is the
> global mean weight per instance, not a normalizing total. On the reference entity
> it is roughly 542× smaller than `total_mean_weight`, which makes `s_m` an unbounded
> ratio that swamps the other two terms. The symptom is `norm > 1`. Guarded by
> `tests/test_reference_parity.py`.

An optional account-level score sums the incident edge norms, or takes their maximum, for the high-activity account log lines.

### 7.5 Verify

Input: a `LogicMap` plus one or more candidate transactions.

1. Reject non-positive line weights with a `fail`. This runs *before* the balance
   check: a negative line can balance, and would otherwise reach the rewrite and
   produce a negative edge weight, which concept §3.2 declares invalid. No rewrite
   is performed.
2. Validate balance; unbalanced transactions `fail` with reason `unbalanced`.
3. Rewrite to edges. Self-loop edges are decided first and never fall through to the
   type table (concept §3.3.1): a two-line self-transfer is a `fail`; a self-loop
   inside a larger journal is recorded as an artifact and casts no vote.
4. For each remaining edge, compute:
   - `seen`: whether the key is in the map
   - `weight_percentile` or rank among edges, or share of node activity
   - `type_pair`: `(B(dr), B(cr))`
   - heuristics:
     - unseen edge with an uncommon type pair → warn or fail
     - unseen edge with a common type pair, such as Expense ← Bank → soft warn
     - seen edge in the top quartile for either node → supporting evidence
5. Aggregate the edge findings into a transaction verdict — `pass`, `warn`, or `fail` — with bullet reasons.

Thresholds are named constants, such as `RARE_EDGE_RANK_FRAC = 0.9`, so evaluation can tune them without redesign.

### 7.6 Predict

Input: `account_id`, `side` (`debit` or `credit`), optional `amount`, optional `top_k`.

- With `side=debit`, rank credit counterparts among edges carrying that debit account by `weight_sum`, reporting `depth`, `norm`, and type.
- With `side=credit`, rank debit counterparts symmetrically.
- Probabilities are counterpart weight ÷ sum of weights on that node-side. This matches `expected_p_from_debit` and `expected_p_from_credit` in `data/reference/` on all 190 edges.
- Where `amount` is given, annotate the distance from the typical mean (`weight_sum/depth`). This is logged only; v1 applies no hard filter.
- Optional `periods` restricts the mass to a set of period keys. Counterparts with no
  activity in those periods drop out rather than ranking at zero. `periods=None`
  reproduces the whole-window behaviour exactly.

**Seasonal conditioning.** `periods.seasonal_periods(target, available)` returns the
same slot in prior years: `2025-01` → `2023-01, 2024-01`; `2025-Q1` → `2023-Q1,
2024-Q1`. Year granularity has no within-year slot and yields nothing. The target is
excluded by default, since conditioning a prediction for a period on itself is
circular. CLI: `predict --season 2025-01`. Where no prior-year period matches, log a
warning and fall back to the whole window rather than returning nothing.

### 7.7 Anomalies (baseline vs open)

Build two maps, `baseline` and `open`, then emit ranked structural deltas:

| Signal | Definition |
|--------|------------|
| `new_edge` | Present in open, absent from baseline |
| `missing_edge` | In the baseline top `BASELINE_TOP_FRAC` (25%) **and** carrying ≥ `MISSING_EDGE_MIN_SHARE` (1%) of baseline weight, then absent or below `NEAR_ZERO_SHARE` in open |
| `rank_shift` | Percentile-rank move ≥ `RANK_SHIFT_MIN_PCTILE` (15%) **and** \|Δ share\| ≥ `RANK_SHIFT_MIN_DELTA_SHARE` (2%) |
| `clearing_surge` | Edges touching accounts whose name or type matches Uncategorized, Clearing, or Discrepancy patterns |

Two rules keep these signals meaningful:

- **Qualify by fraction, not by count.** A fixed "top 30" means *every edge* on a
  20-edge map, which reduces `missing_edge` to noise. Pairing the rank cutoff with a
  materiality floor keeps a depth-1 edge disappearing from registering as a
  structural signal.
- **Compare percentile ranks, not raw ranks.** Baseline and open maps rarely have the
  same edge count, so an edge can move from 14th of 20 to 9th of 13 without changing
  at all. Requiring a material Δ share alongside the rank move removes that artifact.

Emit **one row per edge**, listing every qualifier it tripped in a `signals` column, so that an edge which is both `new_edge` and `clearing_surge` does not consume two top-K slots.

Sort by absolute Δ share of total weight, or by Δ norm. Log the top K and write the full table to TSV.

### 7.8 Periods

Every line carries a date, so period handling needs no new input contract.

`periods.period_key(day, granularity)` returns a label that sorts chronologically
as a string: `2024-03` (month), `2024-Q1` (quarter), `2024` (year).

`periods.filter_lines(lines, start=, end=)` slices a window. Bounds are **inclusive**
and applied to lines *before* validation, so a window that cuts a journal in half
yields an unbalanced transaction and is rejected, which is the correct outcome.

`periods.period_activity(txns, granularity=)` gives per-period `txn_count`,
`line_count`, and `weight`. Weight is the transaction debit total, which is the
rewrite's conserved quantity, so period weights sum to the map's `total_weight`.

`periods.forward_expectation(stats, baseline_periods=)` implements the concept
doc's projection:

```text
expected(P_open) = mean(weight over the trailing n closed periods)
variance         = actual(P_open) - expected(P_open)
```

The last period in `stats` is the open one. The window is capped at the periods
available and never padded. Default `n = DEFAULT_BASELINE_PERIODS = 12`; the paper
suggests 12–18 months, and fewer periods make the mean too noisy to read against.

### 7.9 Natural balance (`balances`)

Implements concept §6.1. Lives in `alm.balances`, independent of the edge map, since
it reads position rather than flow.

1. `period_balances(txns, granularity=)` — closing balance per account per period,
   signed debit-positive, cumulative to each period end. The period series is
   **contiguous** (`periods.period_span`) rather than limited to periods with
   activity: an account sitting the wrong way through a dormant month is still
   sitting the wrong way, and a gap would break the run-length count.
2. `infer_contra(accounts, closing)` — scores hierarchy (+2), coverage-weighted
   lifetime persistence (+2), and name (+1); contra at ≥2. Concept §6.1 explains why
   peer minority is deliberately unscored and why coverage is required alongside
   consistency.
3. `unnatural_balances(...)` — reports accounts whose latest closing balance sits
   opposite their effective natural side, with `periods_off`, `consecutive_off`, and
   severity. Bank and Credit Card are `high`, being impossible cash positions;
   anything off-side for ≥3 consecutive periods escalates to `high`.

`--min-consecutive N` suppresses transient cases. Output `balances.tsv` carries the
findings *and* the inferred contras, because the contras explain which accounts are
absent from the findings list.

---

## 8. CLI surface

```text
# Full end-to-end walkthrough: sample entity, 25-month history, reference edge list
python -m alm demo [--out out] [--sample data/sample] \
  [--history data/history] [--reference data/reference]

python -m alm build \
  --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions.tsv \
  --out out/baseline [--label LABEL] [--granularity month|quarter|year]

python -m alm build \
  --accounts ... --transactions data/sample/transactions_open.tsv \
  --out out/open

python -m alm verify \
  --map out/baseline \
  --candidates data/sample/candidates.tsv \
  --out out/verify

python -m alm predict \
  --map out/baseline \
  --account "1000 Bank" \
  --side credit \
  --top 10 [--amount N] [--season 2025-01] [--out predict.tsv]

python -m alm anomalies \
  --baseline out/baseline \
  --open out/open \
  --out out/anomalies \
  --top 25

python -m alm eval \
  --map out/baseline \
  --out out/eval \
  [--candidates data/sample/candidates.tsv] \
  [--holdout data/sample/holdout.tsv] \
  [--baseline out/baseline --open-map out/open] \
  [--expected-anomalies data/sample/expected_anomalies.tsv] \
  [--top 25]

# Period windowing: one ledger, sliced into closed baseline and open period
python -m alm build \
  --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --to 2024-12-31 --out out/hist/baseline --label closed

python -m alm periods \
  --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --granularity month --baseline-periods 12 --out out/hist/periods

python -m alm balances \
  --accounts data/history/accounts.tsv \
  --transactions data/history/transactions.tsv \
  --min-consecutive 2 --out out/hist/balances

# Pre-aggregated edge list, no Excel required
python -m alm build-from-edges \
  --edges data/reference/reference_edges.tsv \
  --accounts data/reference/reference_accounts.tsv \
  --out out/reference

# Pre-aggregated edge list from an Excel workbook with rw / ca sheets (requires openpyxl)
python -m alm build-from-excel --xlsx <workbook.xlsx> --out out/excel_ref
```

`build`, `periods`, and `balances` accept `--from` and `--to` as inclusive ISO dates, plus `--granularity`. The selected window is recorded in `meta.tsv`.

`build`, `build-from-edges`, and `build-from-excel` write a map directory; the other commands read one.

---

## 9. Map directory + TSV artifacts

Each `--out <dir>` from `build` contains:

| File | Contents |
|------|----------|
| `meta.tsv` | window label, txn/line/edge counts, totals, granularity, period count and first/last period, generated_at |
| `accounts.tsv` | normalized copy of the accounts used |
| `edges.tsv` | debit_account_id, credit_account_id, weight_sum, depth, mean_weight, share_w, share_c, share_m, norm, rank, ambiguous_share, is_self_loop |
| `edge_periods.tsv` | debit_account_id, credit_account_id, period, weight, depth — per-period mass, so it survives a round-trip and `predict --season` works against a saved map |
| `spectrum.tsv` | the same rows and columns as `edges.tsv`, sorted by norm; provided for convenience |
| `node_activity.tsv` | account_id, account_type, as_debit_weight, as_credit_weight, incident_norm |

Command outputs:

| Command | Extra TSVs |
|---------|------------|
| `verify` | `verify_results.tsv` — txn_id, verdict, expected_verdict, reasons, edge_count, edges |
| `predict` | stdout table; `--out predict.tsv` optional |
| `anomalies` | `anomaly_edges.tsv` — one row per edge; `signals` is a comma-joined list, alongside baseline/open shares, ranks, and Δ share |
| `eval` | `eval_summary.tsv`, `eval_detail.tsv` |
| `periods` | `periods.tsv` — a `period` row per period plus a final `forward_expectation` row, distinguished by the `kind` column |
| `balances` | `balances.tsv` — `unnatural_balance` rows plus `inferred_contra` rows, distinguished by the `kind` column |

`eval_summary.tsv` holds heterogeneous metric rows for verify, predict, and anomaly families, each carrying different keys. Its header must be the **union** of keys across all rows; deriving it from the first row alone blanks every column that row happens to lack.

Console output: a short banner, counts, the top 10 spectrum edges, and command-specific highlights. No full matrix dumps.

---

## 10. Sample data requirements

`data/sample/` ships a **small synthetic entity** of roughly 15–30 accounts and 40–80 transactions, including:

- Common edges: Bank↔Sales, Expense←Bank, Expense←Card, A/R↔Revenue, A/P↔Expense, loan payment.
- At least one journal with **more than one line on both sides**. An `(n,1)` journal
  does not exercise averaging at all, since its apportionment is exact.
- At least one journal touching the same account on both sides, so that the self-loop
  path and `ambiguous_share = 1.0` edges are covered by fixture data.
- `candidates.tsv`: a mix of normal, rare-but-valid, and deliberately invalid type pairs.
- `transactions_open.tsv`: the baseline pattern plus injected anomalies — a new loan edge, a clearing surge, and a missing core sales edge.
- `holdout.tsv`: true counterparts for prediction evaluation.

`data/history/` ships a 25-month synthetic ledger for period work, including two edges that occur in one season only, so that seasonal conditioning is exercised by distinct counterparts rather than by an amount shift. Its `holdout.tsv` is drawn from a month the baseline build excludes, which makes it the genuinely held-out prediction fixture (§11.2).

`data/reference/` ships a synthetic reference entity of 190 edges over 82 accounts, with the expected norm and probability values for every edge. It demonstrates scale without raw journals and is the parity contract for §7.4; see `data/reference/README.md`.

---

## 11. Evaluation (`alm eval`) — success criteria

Automates the concept doc §10 checks as far as possible.

### 11.1 Verification

On labeled candidates, using the optional `expected_verdict` column:

- Normal held-out or in-pattern transactions → majority `pass`, or `warn` only where depth is thin.
- Invalid type pairs → majority `fail` or hard `warn`.
- A precision-style summary is reported in `eval_summary.tsv`.

### 11.2 Prediction

For each holdout edge `(dr, cr)`:

- Condition on debit, then check that the credit ranks within K, default K=3 and K=5.
- Condition on credit, then check that the debit ranks within K.
- Baselines: uniform random among accounts, plus an optional type-only prior where implemented.
- **Pass bar (demo):** hit-rate@5 clearly above random on frequent edges, meaning depth ≥ 3 in the map.

Because the pass bar is stated only for frequent edges, `eval` reports two cohorts and labels them in a `cohort` column:

| Cohort | Membership |
|--------|------------|
| `all` | every holdout edge |
| `frequent` | holdout edges whose map depth ≥ `PREDICT_FREQUENT_DEPTH` (3) |

A cohort with no members reports `n=0` and `above_random=False`, never a vacuous pass.

**Holdout independence.** Hit-rate measures generalisation only where the holdout edges were excluded from the map. Where every holdout edge is already present, the number measures recall of learned edges instead, and `eval` logs a warning. `data/sample/holdout.tsv` is in that state by construction; `data/history/holdout.tsv` is the genuinely held-out fixture, drawn from a month the baseline build excludes.

### 11.3 Anomalies

Given an open window with known injected signals, the top-25 anomaly list must include those injections. Expected signals are supplied by `--expected-anomalies`, with `data/sample/expected_anomalies.tsv` as the shipped fixture.

### 11.4 Scale smoke

`build-from-edges` completes on the 190-edge reference entity, reproduces its globals exactly (`total_weight = 6,007,237.44`, `total_depth = 2241`, `total_mean_weight = 1,453,364.406`), writes `edges.tsv` with non-zero counts, and logs the top edges and the 18.4% self-loop share. This discharges the scale check without a third-party dependency. `build-from-excel` covers the same path from a workbook where `openpyxl` is installed, with no accuracy claim beyond matching edge keys and comparable sums.

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

Errors for invariant breaks include the `txn_id` and the amounts. Use `WARNING` for skipped optional files and for a missing `openpyxl`.

---

## 13. Testing plan

Tests live under `tests/` and are part of the proof, not optional. The suite is 70 tests and runs in well under a second.

| Test module | Must prove |
|-------------|------------|
| `test_rewrite` | Weight conservation; 2-line identity; 2×2 four edges; unbalanced rejection; self-loop emission; `(n,1)` is not ambiguous |
| `test_aggregate` | Collapse sums and depths; globals; norm ranking order on a tiny fixture; ambiguous-weight split; self-loop flag |
| `test_verify_predict` | Known edge passes; nonsense fails or warns; predict top contains the fixture counterpart; negative line rejected before rewrite; self-transfer fails; in-journal self-loop casts no vote |
| `test_anomalies` | Injected new and missing edges appear in the output; qualifiers do not flood a small map; `rank_shift` requires a material move; one row per edge |
| `test_reference_parity` | Globals, normed blend, and predict probabilities match the expected values shipped in `data/reference/`; the wrong `s_m` denominator is guarded |
| `test_eval_outputs` | `eval_summary.tsv` keeps every metric family's columns; predict cohorts computed; empty cohort never passes vacuously; holdout-leakage assertion |
| `test_balances` | Natural side per type; parent resolution with and without account codes; name alone is not contra; coverage separates a contra from an occasional dip; fixture end-to-end, where the contra is silent and the overdrawn bank is `high` |
| `test_periods` | Period keys sort and bound correctly; windows never split a journal; period weights sum to the map total; forward expectation is the trailing mean, capped not padded; prediction beats random on transactions outside the map; seasonal conditioning reranks in-season counterparts and drops out-of-season ones |

Run: `python -m unittest discover -s tests -v`

The Excel loader is exercised through `build-from-excel` where `openpyxl` is installed. It is an optional end-to-end step, not a CI dependency; `build-from-edges` covers the same code path without it.

---

## 14. Module map

| Module | Responsibility | Spec section |
|--------|----------------|--------------|
| `models` | Dataclasses and tuning constants | §6 |
| `validate` | Double-entry axioms; groups lines into transactions | §7.1 |
| `rewrite` | DR×CR averaging, self-loop and ambiguity flags | §7.2 |
| `aggregate` | Edge collapse and map globals | §7.3 |
| `score` | Normed blend and spectrum ranking | §7.4 |
| `verify` | Candidate scoring and verdicts | §7.5 |
| `predict` | Conditional counterpart ranking, optional period filter | §7.6 |
| `anomalies` | Baseline-vs-open structural deltas | §7.7 |
| `periods` | Period keys, windowing, forward expectation, seasonal slots | §7.8 |
| `balances` | Natural balance and contra inference | §7.9 |
| `eval` | Success-criteria metrics across the three uses | §11 |
| `io_tsv` | All TSV readers and writers, including map directories | §5, §9 |
| `io_excel` | Optional workbook edge-list loader | §5.3 |
| `cli` / `__main__` | Argument parsing, logging, command bodies, `demo` | §8, §12 |

---

## 15. README acceptance checklist

A reviewer can prove the concept by running:

```text
pip install -e .          # or PYTHONPATH=src
python -m alm demo        # full walkthrough, or the individual commands below

python -m alm build --accounts data/sample/accounts.tsv \
  --transactions data/sample/transactions.tsv --out out/baseline
python -m alm verify --map out/baseline --candidates data/sample/candidates.tsv --out out/verify
python -m alm predict --map out/baseline --account <id> --side credit --top 10
python -m alm anomalies --baseline out/baseline --open out/open --out out/anomalies
python -m alm eval --map out/baseline --holdout data/sample/holdout.tsv --out out/eval
```

and seeing terminal summaries plus TSVs matching §9–§11.

---

## 16. Definition of done

- [x] Sample entity builds a non-empty spectrum from journal lines.
- [x] Verify, predict, and anomalies commands produce explainable terminal and TSV output.
- [x] `eval` reports verification separation, prediction hit-rate@K above random on frequent edges, and recovery of injected anomalies.
- [x] Tests cover rewrite conservation and the three use-case smoke paths.
- [x] No UI, no required services; the concept definition remains the behavioral source of truth.
- [x] The reference edge-list path builds at scale and reproduces the expected globals exactly, via `build-from-edges`.
- [ ] The Excel path builds a map from a workbook's `rw` and `ca` sheets (§5.3). Unverified, since `openpyxl` is unavailable in the development environment. `build-from-edges` covers the same parity contract from TSV, so this box gates only the workbook reader itself.

---

## 17. Open extensions

| Extension | Notes |
|-----------|-------|
| Minimal transaction splitter before rewrite | Concept §3.3; would reduce ambiguous share on multi-event journals |
| Full type-pair prior matrix from the concept tables | `verify.COMMON_TYPE_PAIRS` implements a heuristic subset today |
| Contact-conditioned edges | Requires the contacts set $Q$, which is outside the v1 input contract |
| Dollar materiality weighting for anomaly ranking | Concept §7; ranking is by structural size today |
