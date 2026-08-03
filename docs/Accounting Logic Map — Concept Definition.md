# Accounting Logic Map — Concept Definition

**Purpose of this document.** Define the idea being proven in enough detail to implement and evaluate a coding demo, without requiring the original paper, workbook, or source ledger. It covers what the map is, how it is built, and how it supports verification of posted activity, prediction of near-term postings, and anomaly / trend insight at any business scale.

---

## 1. One-sentence claim

Double-entry books are a directed bipartite graph of value movement (debit ↔ credit). If you rewrite posted transactions into that graph and aggregate it over time, the resulting **characteristic edge distribution** is a compact, explainable signature of the business—usable to check new postings, forecast likely counterparts, and surface structural anomalies.

---

## 2. What problem this solves

Accounting systems store transactions as multi-line journals. Humans (and most tools) reason about them one document at a time. That works for posting, but it is a weak basis for:

- asking whether a new posting *fits* this entity’s normal pattern,
- guessing the missing side of a half-known event (e.g. bank feed line with no category),
- noticing when the *shape* of activity has drifted even when totals still “look fine.”

The Accounting Logic Map treats the ledger as a graph and reduces it so those questions become measurable comparisons against a learned baseline—not a black-box score, but ranked debit–credit relationships with amounts, frequencies, and account-type context.

---

## 3. Core model

### 3.1 Entity image (minimal)

An accounting entity \(E\) is represented by at least:

| Symbol | Meaning |
|--------|---------|
| \(A\) | Chart of accounts |
| \(B\) | Account-type map (Bank, A/R, Expense, …) binding each \(a \in A\) to natural balance and role |
| \(T\) | Posted transactions; each \(T_i\) has debit lines \(DR\) and credit lines \(CR\) |
| \(P\) | Periods (month, quarter, year, …) used for slicing and comparison |

Optional but useful for richer demos later: contacts \(Q\), processes \(J\), control documents \(D\). The first demo does not need them.

### 3.2 Hard constraints (always true)

These are not ML assumptions; they are double-entry axioms the demo must respect:

1. Every transaction has ≥1 debit and ≥1 credit line.
2. Every line posts to exactly one account with a positive weight (amount).
3. Within a transaction, \(\sum w(DR) = \sum w(CR)\).
4. Direction (debit/credit) is stored as direction; account type \(B\) turns that into balance increase/decrease.
5. The balance-sheet identity holds over closed books: assets = liabilities + equity (with temporary P&L accounts rolling into equity).

Any pipeline that invents unbalanced edges or negative line weights is invalid.

### 3.3 Why a bipartite rewrite

A single journal can touch many accounts. For characteristic analysis we care about **pairwise value flow**: which account funded which account (and how often / how much).

**Exact-cover averaging (default rewrite).** For transaction \(T_i\) with total weight \(W = \sum w(DR) = \sum w(CR)\), every debit–credit pair becomes an edge:

\[
Y_i = DR \times CR,\qquad
w(DR_j, CR_k) = \frac{w(DR_j)\,w(CR_k)}{W}
\]

Two-line transactions collapse to one edge with weight \(W\). Multi-line journals distribute weight proportionally so edge weights still sum to \(W\).

**Minimal rewrite (optional upgrade).** When a journal clearly packs unrelated events (common in cleanup JEs), prefer splitting into balanced subsets before averaging—e.g. matching unique amounts across sides, or exact covers of line subsets. Until that exists, averaging is sufficient and matches the spreadsheet prototype.

**Pairing confidence.** The product only has to *guess* when both sides carry several lines. A journal with one line on either side pins its pairings exactly—an \((n,1)\) journal apportions \(w(dr_j, cr_1) = w(dr_j)\), which is not an average at all. So every edge carries an **ambiguous share**: the fraction of its weight sourced from many-to-many journals. This is the paper's "proportion of reduced hyperedges," and it is the honest answer to the false-edge problem: a 100%-ambiguous edge is a pairing the rewrite invented, and should be read as weak evidence rather than silently ranked beside observed flows.

### 3.3.1 Self-loop edges

When one account is debited *and* credited in the same journal, \(DR \times CR\) emits an \((a, a)\) edge. No account funded another, so it is not a value movement—it is an artifact of the rewrite.

They are not rare. On the reference entity they carry **18% of total weight** and occupy three of the top five spectrum slots.

Policy:

- **Retain them.** Dropping them would break \(\sum_{j,k} w(dr_j, cr_k) = W\), and the prototype includes them, so removal would also break parity.
- **Label them.** Every edge exposes `is_self_loop`; `build` reports their weight share.
- **Never read them as postings.** In particular, they must be decided *before* any account-type reasoning: a self-loop's type pair is by definition identical on both sides, which the type table would misread—`(Bank, Bank)` means a transfer between two *different* bank accounts, and same-type-both-sides otherwise reads as reclassification.

A posting whose *whole* content is one account against itself is a different thing: it moves no value and is almost certainly an error, whatever the account type. Verification fails it outright (§5.1).

### 3.4 Aggregation → characteristic map

After rewriting all \(T\) in a window of periods:

1. **Collapse identical edges** \((a_{dr}, a_{cr})\) across transactions.
2. Store per edge at least:
   - **Edge sum** — total rewritten weight
   - **Depth** — how many source transactions contributed
   - **Pair instances** — how many DR×CR emissions; above depth means multi-line journals fed it
   - **Ambiguous share** — fraction of weight from many-to-many journals (§3.3)
   - **Self-loop flag** — whether both endpoints are the same account (§3.3.1)
   - Optional: mean amount, recurrence over periods, standard deviation, contact if available
3. Materialize square (or sparse) matrices over accounts:
   - \(W[a_{dr}, a_{cr}]\) — weight
   - \(C[a_{dr}, a_{cr}]\) — count / depth
4. **Normalize** so large and small businesses are comparable. One workable score (as in the spreadsheet prototype) blends three quantities, *each expressed as a share of its own global total* so that all three sit on the same scale and each sums to 1 across edges:

   | Term | Edge value | Global denominator |
   |------|------------|--------------------|
   | weight share | edge weight \(w\) | \(\sum_e w_e\) |
   | depth share | edge depth \(c\) | \(\sum_e c_e\) |
   | mean-size share | mean weight per instance \(w/c\) | \(\sum_e (w_e/c_e)\) |

   \[
   \mathrm{norm}(e) = \tfrac{1}{3}\left(\frac{w_e}{\sum w} + \frac{c_e}{\sum c} + \frac{w_e/c_e}{\sum (w/c)}\right)
   \]

   Rank accounts / edges by that score to get the **characteristic spectrum**.

   The third denominator is the **sum of per-edge means**, not the global mean \(\sum w / \sum c\). They differ by orders of magnitude (≈542× on the reference entity), and substituting the latter turns that term from a share into an unbounded ratio that dominates the average — the blend degenerates into "mean transaction size" and one-off large journals outrank recurring core activity.

That spectrum *is* the Accounting Logic Map for the chosen window: a low-dimensional projection of high-dimensional journal activity that preserves “who moves value with whom.”

---

## 4. What the map is *not*

- Not a replacement general ledger.
- Not full accrual-flow tracing (invoice → payment chains) by itself—though edges and account types \(B\) are the substrate for that later.
- Not a claim that every averaged multi-line JE edge is ontologically “true”; noise exists, but dominant edges dominate the ranking.
- Not dependent on a specific product (QBO, Xero, etc.); predefined transaction types only help labeling, not the graph math.

---

## 5. Three uses being proven

### 5.1 Verification of posted transactions

**Question:** Given a newly posted (or candidate) transaction, does it fit this entity’s established map?

**Method:**

1. Rewrite the candidate into edges \(Y^*\).
2. For each edge, look up historical \(W\), \(C\), and account-type expectations from \(B\) / characteristic transaction tables (e.g. Expense usually debited against Bank/Card credit).
3. Score:
   - **Known strong edge** — high historical weight/depth → supports posting.
   - **Known weak / rare edge** — exists but low rank → allow with lower confidence or review flag.
   - **Unseen edge** — never (or almost never) observed → anomaly unless account types still form a valid characteristic pair (e.g. first rent payment to a new landlord GL still Expense←Bank).
   - **Type-illegal or reclass-suspicious** — same non-cash type on both sides often signals reclassification; cash↔cash is transfer-like; red combinations from the type matrix can hard-fail or hard-warn.
   - **Self-loop** — decided before type logic (§3.3.1). If the whole posting is one account against itself, **fail**: it moves no value. If the loop is only an artifact of rewriting a larger journal, it is noted and gets no vote either way.

   Line weights must be positive before any of this runs. A negative line can still balance, so the balance check alone will pass it through to the rewrite and produce a negative edge weight — which §3.2 declares invalid.

**Output useful in a demo:** per-transaction pass/warn/fail with the concrete edges and their historical percentiles—not a single opaque number.

Verification answers: “Is this posting consistent with how *this* business has moved value?”

### 5.2 Prediction of future / incomplete transactions

**Question:** Given a partial observation (one side of an exchange, a bank amount, an account, a contact), what counterparts are most likely?

**Method:**

1. Condition on the known node (account and/or side).
2. Read the row/column of \(W\) and \(C\) (or the normed matrix): counterpart accounts ranked by probability mass.
3. Optionally refine with:
   - account type \(B\) (bank feed out → Expense / AP / Card / Loan payoff priors),
   - **period seasonality** — condition the counterpart distribution on the same slot in prior years rather than on the whole window,
   - feed-side priors (which side of the edge is usually “pre-fed” from bank/card imports).

**Seasonality.** Averaging a counterpart distribution over the whole window buries any
edge that only occurs in part of the year. Conditioning on the same month (or quarter)
in prior years reads the mass from comparable periods only, so seasonal counterparts
surface and out-of-season ones drop out entirely. This needs per-period edge mass
retained during aggregation, not just an edge total. The target period is excluded from
its own conditioning set — predicting *for* a period using that period's activity would
be circular.

**Demo shape:** input `account=<operating bank>, side=credit, amount≈X` → ranked debit accounts with historical share of that node’s activity and typical amount bands; add a season to rank against comparable periods instead.

Prediction answers: “What is the *characteristic* other side of this movement?”

### 5.3 Anomaly and trend insight (any relative size)

**Question:** Has the *structure* of activity changed in a way that should change decisions—even if P&L totals look familiar?

**Method:**

1. Build maps for windows: e.g. trailing 12 closed months vs current open month; or YoY same months.
2. Compare distributions of edges (and/or account participation ranks):
   - edges that **appeared** or **vanished**,
   - large **rank shifts** in normed score,
   - concentration changes (few edges dominate more/less),
   - growth in **Uncategorized** / clearing / discrepancy accounts,
   - new edges that violate type expectations at rising volume.
3. Because the representation is relative (shares, ranks, probabilities), the same machinery applies to a 50-transaction sole prop and a multi-entity group—scale differences show up as depth and absolute weight, not as a different algorithm.

**Demo shape:** table of top Δ-ranked edges and new edges in \(P_{open}\) vs baseline \(P_{-n}\), with account-type tags.

Anomaly insight answers: “What about *how* value moves is changing?”

---

## 6. Account types as a second axis

The graph alone names accounts. The type map \(B\) supplies meaning:

- **Natural balance** — whether a debit increases the account.
- **Role in flows** — cash, accrual holding (A/R, A/P), temporary P&L, equity, etc.
- **Characteristic pairs** — e.g. Invoice ≈ DR A/R + CR Revenue; Bill payment ≈ DR A/P + CR Cash/Card.

Use \(B\) to:

- color and group matrix output,
- separate “surprising account pair” from “surprising *type* pair,”
- bootstrap priors when historical depth is thin (new entity or new account).

Base groups: Assets, Liabilities, Equity, Income, Expense (with contra and clearing treated explicitly when present).

---

## 7. Periods, windows, and present bias

Prefer recent closed periods for the baseline (often 12–18 months), then compare the open period to that baseline. A simple forward expectation for variance analysis:

\[
\hat{E}(P_1) \;=\; \frac{1}{n}\sum_{-n}^{-1} E(P)
\]

i.e. project average period activity forward and measure open-period deviation in graph space—not only in trial-balance totals. (The sum matters: the projection is the mean *over* the trailing closed periods, not a single period divided by \(n\).)

Every line already carries a date, so periods need no extra input contract—`period_key` derives month, quarter, or year labels that sort chronologically as strings.

Two things follow from this, and both are part of the demo:

1. **Windowed builds.** A baseline is a date-bounded slice of one ledger, not a separately curated file. Bounds are inclusive and applied to *lines*, so a window that cuts a journal in half produces an unbalanced transaction and fails validation—which is correct: such a window does not describe a real set of books.
2. **Honest holdout.** Splitting by period is what makes a prediction holdout meaningful: build from closed periods, evaluate on transactions from a period the map never saw. Note that edge-type overlap between the two is *not* leakage—a stable business repeats its edges every month. What matters is that the transactions were excluded.

Period length matters for the projection: a handful of periods gives a mean too noisy to read a variance against, which is why the default trailing window is 12.

Materiality can weight which deviations matter; the first demo can rank by structural size (weight/depth) and leave dollar materiality as a later knob.

---

## 8. Reference prototype (Excel) — behavioral contract

The test workbook encodes the aggregation half of this idea on a real chart of accounts:

| Artifact | Role in the concept |
|----------|---------------------|
| Distinct DR\|CR edges with sum & depth | Aggregated rewrite output |
| Weight / count matrices | Dense view of \(W\), \(C\) |
| Normed blend vs global totals | Ranking / spectrum |
| Filtered multisort of hot accounts | Characteristic accounts for inspection |
| Chart-of-accounts type list | \(B\) labels |

A coding demo “proves the idea” when it can reproduce this pipeline from journal lines (or from an edge list), emit the same classes of artifacts (logs + TSV), and then apply those artifacts to the three uses in §5 on held-out or synthetic cases.

---

## 9. Suggested demo scope (definition of done)

**In scope for a first Python CLI**

1. Ingest balanced transaction lines (sample TSV and/or edge list exported from books).
2. Rewrite → aggregate → write TSVs: edges, weight matrix (sparse long form), count matrix, ranked spectrum.
3. Log clearly: counts of transactions/edges, top characteristic edges, simple open-vs-baseline deltas if two windows are provided.
4. Small verification and prediction commands that consume the built map.

**Explicitly later**

- Full minimal exact-cover splitter for messy JEs  
- Contact-level graphs and control-map estimation  
- Accrual chain / flow object reconstruction  
- Cross-entity comparison  

---

## 10. Success criteria for the idea (not the UI)

The concept is supported if, on real or realistic books:

1. **Verification** — held-out normal postings score as in-distribution on their edges; deliberately wrong type pairs and random account pairs score worse in an explainable way.
2. **Prediction** — given one side of frequent historical edges, the true counterpart ranks near the top of the conditional distribution more often than chance / type-only baselines.
3. **Anomalies** — injected regime changes (new financing edge, surge in clearing, disappearance of a core sales edge) appear as top structural deltas between windows without requiring the user to read every journal.

Scale-invariance is shown when the same code path, with share/rank metrics, produces useful rankings for both a small sample entity and a larger edge set without parameter retuning beyond window choice.

---

## 11. Glossary

| Term | Meaning |
|------|---------|
| Edge | Ordered pair (debit account, credit account) with weight |
| Depth | How often that edge was produced by the rewrite |
| Characteristic map / spectrum | Ranked distribution of aggregated edges (and accounts) |
| Rewrite | Expanding a multi-line journal into DR×CR edges |
| Baseline window | Historical periods used as “normal” |
| Open window | Current or candidate period under scrutiny |

---

## 12. Bottom line

Books already encode a graph of control over value. The Accounting Logic Map makes that graph explicit, aggregates it into a stable signature, and uses the signature three ways: **check** postings against history and type logic, **guess** missing counterparts from conditional edge mass, and **watch** whether the business’s movement pattern is drifting. That is the idea a coding demo should implement and measure.
