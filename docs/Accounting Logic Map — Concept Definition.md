# Accounting Logic Map — Concept Definition

**Purpose of this document.** Define the idea being proven in enough detail to implement and evaluate a coding demo, without requiring the original paper, its spreadsheet prototype, or a source ledger. It covers what the map is, how it is built, and how it supports verification of posted activity, prediction of near-term postings, and anomaly and trend insight at any business scale.

---

## 1. One-sentence claim

Double-entry books are a directed bipartite graph of value movement (debit ↔ credit). Rewriting posted transactions into that graph and aggregating it over time produces a **characteristic edge distribution**: a compact, explainable signature of the business, usable to check new postings, forecast likely counterparts, and surface structural anomalies.

---

## 2. What problem this solves

Accounting systems store transactions as multi-line journals, and most tools reason about them one document at a time. That is adequate for posting, but a weak basis for:

- asking whether a new posting fits the entity's established pattern,
- identifying the missing side of a half-known event, such as a bank feed line with no category,
- noticing that the shape of activity has drifted while period totals remain unremarkable.

The Accounting Logic Map treats the ledger as a graph and reduces it so that these questions become measurable comparisons against a learned baseline. The result is not an opaque score but a ranked set of debit–credit relationships carrying amounts, frequencies, and account-type context.

---

## 3. Core model

### 3.1 Entity image (minimal)

An accounting entity $E$ is represented by at least:

| Symbol | Meaning |
|--------|---------|
| $A$ | Chart of accounts |
| $B$ | Account-type map (Bank, A/R, Expense, …) binding each $a \in A$ to natural balance and role |
| $T$ | Posted transactions; each $T_i$ has debit lines $DR$ and credit lines $CR$ |
| $P$ | Periods (month, quarter, year, …) used for slicing and comparison |

Contacts $Q$, processes $J$, and control documents $D$ support richer analysis later. The first demo does not require them.

### 3.2 Hard constraints (always true)

These are not modelling assumptions; they are double-entry axioms the demo must respect:

1. Every transaction has at least one debit and one credit line.
2. Every line posts to exactly one account with a positive weight (amount).
3. Within a transaction, $\sum w(DR) = \sum w(CR)$.
4. Direction (debit/credit) is stored as direction; account type $B$ converts it into a balance increase or decrease.
5. The balance-sheet identity holds over closed books: assets = liabilities + equity, with temporary P&L accounts rolling into equity.

Any pipeline that produces unbalanced edges or negative line weights is invalid.

Constraints 1–4 are enforced on ingest. Constraint 5 is enforced upstream by any correctly configured accounting system, so the map does not re-derive it. What the map does take from the same logic is the natural-balance signal in §6.1, which concerns position rather than the graph.

### 3.3 Why a bipartite rewrite

A single journal can touch many accounts. Characteristic analysis depends on **pairwise value flow**: which account funded which account, how often, and for how much.

**Exact-cover averaging (default rewrite).** For transaction $T_i$ with total weight $W = \sum w(DR) = \sum w(CR)$, every debit–credit pair becomes an edge:

$$
Y_i = DR \times CR, \qquad w(DR_j, CR_k) = \frac{w(DR_j)\,w(CR_k)}{W}
$$

Two-line transactions collapse to a single edge with weight $W$. Multi-line journals distribute weight proportionally, so edge weights still sum to $W$.

**Minimal rewrite (deferred upgrade).** Where a journal packs unrelated events together, as cleanup entries often do, splitting it into balanced subsets before averaging would be preferable — for example by matching unique amounts across sides, or by taking exact covers of line subsets. Until that exists, averaging is sufficient and matches the spreadsheet prototype.

**Pairing confidence.** The product is only an estimate when both sides carry several lines. A journal with a single line on either side pins its pairings exactly: an $(n,1)$ journal apportions $w(dr_j, cr_1) = w(dr_j)$, which is not an average. Every edge therefore carries an **ambiguous share** — the fraction of its weight sourced from many-to-many journals. This is the paper's "proportion of reduced hyperedges", and it is the measure that addresses the false-edge problem. An edge with a 100% ambiguous share exists only because the rewrite paired lines that may never have been related, and it should be read as weak evidence rather than ranked alongside observed flows.

### 3.3.1 Self-loop edges

When one account is debited *and* credited in the same journal, $DR \times CR$ emits an $(a, a)$ edge. No account funded another, so it records no value movement; it is an artifact of the rewrite.

Such edges are not rare. On the reference entity, 5 of 190 edges are self-loops, and they carry **18.4% of total weight** and occupy two of the top five spectrum slots.

Policy:

- **Retain them.** Dropping them would break $\sum_{j,k} w(dr_j, cr_k) = W$, and the prototype includes them, so removal would also break parity.
- **Label them.** Every edge exposes `is_self_loop`, and `build` reports their share of total weight.
- **Never read them as postings.** They must be decided *before* any account-type reasoning, because a self-loop's type pair is identical on both sides by construction and the type table would misread it: `(Bank, Bank)` normally indicates a transfer between two different bank accounts, and matching types on both sides otherwise suggests reclassification.

A posting whose entire content is one account against itself is a separate case. It moves no value and is almost certainly an error, whatever the account type, so verification fails it outright (§5.1).

### 3.4 Aggregation → characteristic map

After rewriting all $T$ in a window of periods:

1. **Collapse identical edges** $(a_{dr}, a_{cr})$ across transactions.
2. Store per edge at least:
   - **Edge sum** — total rewritten weight
   - **Depth** — how many source transactions contributed
   - **Pair instances** — how many DR×CR emissions; a count above depth means multi-line journals fed the edge
   - **Ambiguous share** — fraction of weight from many-to-many journals (§3.3)
   - **Self-loop flag** — whether both endpoints are the same account (§3.3.1)
   - Optional: mean amount, recurrence over periods, standard deviation, contact where available
3. Materialize square (or sparse) matrices over accounts:
   - $W[a_{dr}, a_{cr}]$ — weight
   - $C[a_{dr}, a_{cr}]$ — count / depth

**Normalization.** Scores must be comparable across large and small businesses. The blend used by the spreadsheet prototype combines three quantities, each expressed as a share of its own global total, so that all three sit on the same scale and each sums to 1 across edges:

| Term | Edge value | Global denominator |
|------|------------|--------------------|
| weight share | edge weight $w$ | $\sum_e w_e$ |
| depth share | edge depth $c$ | $\sum_e c_e$ |
| mean-size share | mean weight per instance $w/c$ | $\sum_e (w_e/c_e)$ |

$$
\mathrm{norm}(e) = \tfrac{1}{3}\left(\frac{w_e}{\sum w} + \frac{c_e}{\sum c} + \frac{w_e/c_e}{\sum (w/c)}\right)
$$

Ranking accounts and edges by that score gives the **characteristic spectrum**.

The third denominator is the sum of per-edge means, not the global mean $\sum w / \sum c$. The two differ by orders of magnitude — a factor of roughly 542 on the reference entity — and substituting the latter turns that term from a share into an unbounded ratio that dominates the average. The blend then degenerates into a measure of mean transaction size, and one-off large journals outrank recurring core activity.

That spectrum is the Accounting Logic Map for the chosen window: a low-dimensional projection of high-dimensional journal activity that preserves which accounts move value with which.

---

## 4. What the map is *not*

- Not a replacement general ledger.
- Not full accrual-flow tracing (invoice → payment chains) on its own, though edges and account types $B$ are the substrate for it.
- Not a claim that every averaged multi-line edge represents a real relationship. Noise exists, but dominant edges dominate the ranking.
- Not dependent on a specific product such as QBO or Xero. Predefined transaction types assist labeling, not the graph math.

---

## 5. Three uses being proven

### 5.1 Verification of posted transactions

**Question:** Given a newly posted or candidate transaction, does it fit this entity's established map?

**Method:**

1. Rewrite the candidate into edges $Y^*$.
2. For each edge, look up historical $W$, $C$, and account-type expectations from $B$ or from characteristic transaction tables — for example, an expense is usually debited against a bank or card credit.
3. Score:
   - **Known strong edge** — high historical weight and depth, supporting the posting.
   - **Known weak or rare edge** — present but low-ranked; allow with lower confidence or flag for review.
   - **Unseen edge** — never, or almost never, observed. Treat as an anomaly unless the account types still form a valid characteristic pair, such as a first rent payment to a new landlord GL that remains Expense ← Bank.
   - **Type-illegal or reclass-suspicious** — the same non-cash type on both sides often indicates reclassification; cash against cash is transfer-like; combinations the type matrix marks as invalid can hard-fail or hard-warn.
   - **Self-loop** — decided before type logic (§3.3.1). If the whole posting is one account against itself it **fails**, because it moves no value. If the loop is an artifact of rewriting a larger journal, it is noted and casts no vote.

   Line weights must be confirmed positive before any of this runs. A negative line can still balance, so the balance check alone would pass it through to the rewrite and produce a negative edge weight, which §3.2 declares invalid.

**Output useful in a demo:** per-transaction pass/warn/fail with the contributing edges and their historical percentiles, rather than a single opaque number.

Verification answers whether a posting is consistent with how this business has moved value.

### 5.2 Prediction of future or incomplete transactions

**Question:** Given a partial observation — one side of an exchange, a bank amount, an account, a contact — which counterparts are most likely?

**Method:**

1. Condition on the known node (account and/or side).
2. Read the row or column of $W$ and $C$, or of the normed matrix, to rank counterpart accounts by probability mass.
3. Optionally refine with:
   - account type $B$, for example bank feed outflow → Expense / A/P / Card / loan payoff priors,
   - **period seasonality**, conditioning the counterpart distribution on the same slot in prior years rather than on the whole window,
   - feed-side priors, indicating which side of the edge is usually pre-populated from a bank or card import. The prototype's aggregated edges carry such an annotation, but it is absent on 70 of 190 rows (§8), so the available data does not yet support the prior.

**Seasonality.** Averaging a counterpart distribution over the whole window buries any edge that occurs in only part of the year. Conditioning on the same month or quarter in prior years reads mass from comparable periods only, so seasonal counterparts surface and out-of-season ones drop out entirely. This requires per-period edge mass to be retained during aggregation, not just an edge total. The target period is excluded from its own conditioning set, since predicting for a period using that period's activity would be circular.

**Demo shape:** given `account=<operating bank>, side=credit, amount≈X`, return ranked debit accounts with each counterpart's historical share of that node's activity and typical amount bands. Adding a season ranks against comparable periods instead.

Prediction answers which counterpart is characteristic for a given movement.

### 5.3 Anomaly and trend insight (any relative size)

**Question:** Has the structure of activity changed in a way that should change decisions, even where P&L totals look familiar?

**Method:**

1. Build maps for two windows: for example trailing 12 closed months against the current open month, or the same months year over year.
2. Compare distributions of edges and account participation ranks:
   - edges that **appeared** or **vanished**,
   - large **rank shifts** in normed score,
   - concentration changes, where few edges dominate more or less than before,
   - growth in Uncategorized, clearing, or discrepancy accounts,
   - new edges that violate type expectations at rising volume.
3. Because the representation is relative — shares, ranks, probabilities — the same machinery applies to a 50-transaction sole proprietorship and to a multi-entity group. Scale differences appear as depth and absolute weight, not as a different algorithm.

**Demo shape:** a table of top Δ-ranked edges and new edges in $P_{open}$ against baseline $P_{-n}$, with account-type tags.

Anomaly insight answers how the pattern of value movement is changing.

---

## 6. Account types as a second axis

The graph alone names accounts. The type map $B$ supplies meaning:

- **Natural balance** — whether a debit increases the account.
- **Role in flows** — cash, accrual holding (A/R, A/P), temporary P&L, equity, and so on.
- **Characteristic pairs** — an invoice is approximately DR A/R + CR Revenue; a bill payment is approximately DR A/P + CR Cash/Card.

Use $B$ to:

- color and group matrix output,
- separate a surprising account pair from a surprising *type* pair,
- bootstrap priors where historical depth is thin, as with a new entity or a new account.

Base groups: Assets, Liabilities, Equity, Income, Expense, with contra and clearing accounts treated explicitly where present.

### 6.1 Natural balance as a quality signal

Each type implies a characteristic balance direction — the paper's $\tilde{B} = \{+1 \text{ if } DR,\ -1 \text{ if } CR\}$, keyed to the type's initialization side. Asset and expense types run debit; liability, equity, and income types run credit. This sign is carried by the *account type*, not by a per-line convention: the $DR - CR$ subtraction inside the balance definition already accounts for line direction.

The cheapest available check follows from it: does an account's closing balance sit where its type says it should? A bank account with a credit balance is overdrawn. That is possible, but remaining so for a whole period or more indicates a lag in accuracy or completeness rather than a real position.

**Contra accounts are the complication.** Accumulated Depreciation is a fixed asset that always carries a credit balance, because it exists to reduce a sibling asset on the same side of the sheet. Allowances, sales discounts, and treasury stock behave the same way. Reporting them every period would bury the real signal, and nothing in a chart of accounts marks them explicitly.

Contra status is therefore **inferred** from three pieces of evidence, weighted so that no single weak signal decides:

| Evidence | Weight | Rationale |
|----------|--------|-----------|
| Sits opposite a same-type parent resolved from `Parent:Child` chart hierarchy | +2 | A contra is characteristically a child of the balance it reduces |
| Has been on the non-natural side in every period it carried a balance, over ≥3 periods **and** covering ≥60% of its life | +2 | A contra is off-side by construction, from inception |
| Name matches a known contra form | +1 | Corroboration only; a label is not evidence about the books |

Two rules matter more than the weights:

- **Peer comparison is not scored.** An account sitting opposite its same-type peers is equally consistent with a contra and with an error, so it cannot discriminate between them.
- **Coverage is required alongside consistency.** An account that is flat most months and dips the wrong way occasionally has never held a natural-side balance either, yet it presents a timing problem rather than a contra. Requiring the off-side condition to span most of the account's life separates the two.

An account is reported when its balance sits opposite its *effective* natural side — flipped where contra status was inferred — with the run length attached, since one period may be a timing difference and several consecutive periods constitute the signal.

---

## 7. Periods, windows, and present bias

Prefer recent closed periods for the baseline, typically 12–18 months, then compare the open period against that baseline. A simple forward expectation for variance analysis:

$$
\hat{E}(P_1) = \frac{1}{n}\sum_{-n}^{-1} E(P)
$$

This projects average period activity forward and measures open-period deviation in graph space, not only in trial-balance totals. The projection is the mean *over* the trailing closed periods, not a single period divided by $n$.

Every line already carries a date, so periods require no additional input contract: `period_key` derives month, quarter, or year labels that sort chronologically as strings.

Two consequences follow, and both are part of the demo:

1. **Windowed builds.** A baseline is a date-bounded slice of one ledger, not a separately curated file. Bounds are inclusive and applied to *lines*, so a window that cuts a journal in half produces an unbalanced transaction and fails validation. That is the correct outcome: such a window does not describe a real set of books.
2. **Honest holdout.** Splitting by period is what makes a prediction holdout meaningful — build from closed periods, then evaluate on transactions from a period the map never saw. Edge-type overlap between the two is not leakage, since a stable business repeats its edges every month. What matters is that the transactions themselves were excluded.

Period count matters for the projection: a handful of periods gives a mean too noisy to read a variance against, which is why the default trailing window is 12.

Materiality can weight which deviations matter. The first demo ranks by structural size (weight and depth) and leaves dollar materiality as a later refinement.

---

## 8. Reference prototype — behavioral contract

The aggregation half of this idea was first prototyped as a spreadsheet over a live chart of accounts. Its artifacts define what an implementation has to reproduce:

| Artifact | Role in the concept |
|----------|---------------------|
| Distinct DR\|CR edges with sum and depth | Aggregated rewrite output |
| Weight / count matrices | Dense view of $W$, $C$ |
| Normed blend against global totals | Ranking / spectrum |
| Filtered multisort of high-activity accounts | Characteristic accounts for inspection |
| Chart-of-accounts type list | $B$ labels |

Reduced to a portable form, that is an aggregated edge list — one row per distinct debit–credit pair, carrying the two endpoints, the summed weight, and the contributing transaction depth — alongside an account-to-type lookup. Everything else in the table above is derivable from those two tables. `data/reference/` ships an entity in exactly that form, with the expected norm and conditional probabilities per edge, so the contract is testable without the original spreadsheet.

**Coverage of the prototype edge list.** It carries 10 columns, of which this concept and the proof spec account for 6:

| Columns | Status |
|---------|--------|
| Debit node, credit node, edge sum, edge transaction depth | Mapped directly (proof spec §5.3) |
| Two conditional-probability columns | Reproduced exactly by prediction: edge weight ÷ total weight at that node on that side, matching on all 190 edges |
| Feed-side annotation | Absent on 70 of 190 rows; the annotation is incomplete at source, which is why the feed-side priors in §5.2 remain unsupported |
| Per-account probability | Constant `1.0` on all 190 rows; carries no information |

A coding demo proves the idea when it can reproduce this pipeline from journal lines or from an edge list, emit the same classes of artifacts as logs and TSV, and apply those artifacts to the three uses in §5 on held-out or synthetic cases.

---

## 9. Demo scope (definition of done)

**Delivered**

1. Ingest of balanced transaction lines, from sample TSV or from an edge list exported from books.
2. Rewrite → aggregate → TSV output: edges, weight matrix in sparse long form, count matrix, ranked spectrum.
3. Logging of transaction and edge counts, top characteristic edges, and open-against-baseline deltas where two windows are provided.
4. Verification and prediction commands that consume the built map.
5. Period windowing, per-period edge mass, forward expectation, and seasonal conditioning inside prediction (§5.2, §7).
6. Natural-balance reporting with contra inference (§6.1).
7. An evaluation harness measuring the success criteria in §10.

**Deferred**

- Full minimal exact-cover splitter for multi-event journal entries
- Contact-level graphs and control-map estimation
- Accrual chain and flow object reconstruction
- Cross-entity comparison

---

## 10. Success criteria for the idea (not the UI)

The concept is supported if, on real or realistic books:

1. **Verification** — held-out normal postings score as in-distribution on their edges, while deliberately wrong type pairs and random account pairs score worse in an explainable way.
2. **Prediction** — given one side of a frequent historical edge, the true counterpart ranks near the top of the conditional distribution more often than chance or a type-only baseline.
3. **Anomalies** — injected regime changes, such as a new financing edge, a surge in clearing activity, or the disappearance of a core sales edge, appear as top structural deltas between windows without requiring the user to read every journal.

Scale-invariance is demonstrated when the same code path, using share and rank metrics, produces useful rankings for both a small sample entity and a larger edge set without parameter retuning beyond the choice of window.

---

## 11. Glossary

| Term | Meaning |
|------|---------|
| Edge | Ordered pair (debit account, credit account) with weight |
| Depth | How often that edge was produced by the rewrite |
| Characteristic map / spectrum | Ranked distribution of aggregated edges and accounts |
| Rewrite | Expansion of a multi-line journal into DR×CR edges |
| Baseline window | Historical periods used as the reference for normal activity |
| Open window | Current or candidate period under scrutiny |

---

## 12. Summary

Books already encode a graph of control over value. The Accounting Logic Map makes that graph explicit, aggregates it into a stable signature, and applies the signature three ways: checking postings against history and type logic, inferring missing counterparts from conditional edge mass, and monitoring whether the entity's pattern of movement is drifting. That is the idea the coding demo implements and measures.
