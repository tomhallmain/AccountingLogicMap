# Accounting Logic Map — Concept Definition

**Purpose of this document.** Define the idea in enough detail to implement and evaluate it, without requiring the original paper, its spreadsheet prototype, or a source ledger. It covers what the map is, how it is built, and how it supports verification of posted activity, prediction of near-term postings, and anomaly and trend insight at any business scale.

---

## 1. One-sentence claim

Double-entry books are a directed bipartite graph of value movement between debits and credits. Rewriting posted transactions into that graph and aggregating it over time produces a **characteristic edge distribution**: a compact, explainable signature of the business, usable to check new postings, forecast likely counterparts, and surface structural anomalies.

---

## 2. What problem this solves

Accounting systems store transactions as multi-line journals, and most tools reason about them one document at a time. That is adequate for posting, but a weak basis for:

- asking whether a new posting fits the entity's established pattern,
- identifying the missing side of a half-known event, such as a bank feed line with no category,
- noticing that the shape of activity has drifted while period totals remain unremarkable.

The Accounting Logic Map treats the ledger as a graph and reduces it so that these questions become measurable comparisons against a learned baseline. The result is not an opaque score but a ranked set of debit–credit relationships carrying amounts, frequencies, and account-type context.

---

## 3. Core model

### 3.1 Base entity image

An accounting entity $E$ is the informational representation of a business: the element sets a system holds before any analysis begins.

| Symbol | Element | Contents |
|--------|---------|----------|
| $A$ | Accounts | The chart of accounts, including parent–child subset relationships |
| $B$ | Account types | The parent class binding each $a \in A$ to a natural balance direction and a role in flows |
| $T$ | Transactions | Discrete-time elements $T_i$, each holding debit and credit line subsets $DR, CR \subseteq T_i$. Every line binds one side to a single account $a \in A$ for some weight measure $w(r)$ |
| $Q$ | Contacts | External entity records, with subsets for owners $Q_O$, customers $Q_C$, vendors $Q_V$, and employees $Q_E$ |
| $P$ | Periods | Years, quarters, months, weeks, and finer divisions, admitting comparison over time |
| $J$ | Processes | Recorded procedure sets: posting, reconciliation, close |
| $D$ | Control documents | Entity metadata, audit trails, draft and deleted records, receipts, quotes, purchase orders, reconciliations, workpapers |

A present-biased, backwards-looking state of $E$ is the hypergraph

$$
E := \int_{-n \times P}^{0} ⟗\,(A, B, T, Q, J, D)
$$

where $n$ is the number of periods from the inception of $E$ to the end of the most recent closed period. $T$, $J$, and $D$ form hyperedges, and $DR$ and $CR$ form the two sides of an equal-weighted bigraph embedded in $T$. More complex entities carry further elements, among them inventory items and classes.

Read left to right, the expression says three things. The operator ⟗ is the full outer join, so the element sets combine without discarding a record that has no counterpart in the others: an account with no transactions, a contact with no invoices, and a control document with no posting all survive the join, and their absence of counterparts is itself information about the books. The bounds $-n \times P$ to $0$ run the join across every period from inception to the present. Integrating over that range collapses the result into a single accumulated state rather than a sequence of period snapshots.

The entity is therefore one object: every account, type, transaction, contact, process, and document, joined and accumulated across the entity's whole life.

Two properties of this image govern everything downstream.

**It is present-biased by design.** Weighting recent records more heavily forfeits a complete picture of the entity's history, which is an acceptable trade. Analysis over the most recent 12 to 18 months is the efficient way to draw relevant information out of so high-dimensional a state, and §7 develops the windowing and forward projection that follow from it.

**The characteristic map is a projection of it, not a replacement for it.** The map projects the $T$ hyperedges onto pairwise flow and reads the result against $B$, over a window of $P$. Those four elements are what the map consumes. $Q$, $J$, and $D$ are part of the entity and bind information the projection does not carry — counterparty, procedure, and evidence — which is what makes the image worth stating in full even where a given analysis uses part of it.

### 3.2 Invariant constraints

These are not modelling assumptions; they are double-entry axioms any implementation respects:

1. Every transaction has at least one debit and one credit line.
2. Every line posts to exactly one account with a positive weight.
3. Within a transaction, $\sum w(DR) = \sum w(CR)$.
4. Direction is stored as direction; account type $B$ converts it into a balance increase or decrease.
5. The balance-sheet identity holds over closed books: assets equal liabilities plus equity, with temporary P&L accounts rolling into equity.

Any pipeline that produces unbalanced edges or negative line weights is invalid.

Constraints 1 through 4 are enforced on ingest. Constraint 5 is enforced upstream by any correctly configured accounting system, so the map does not re-derive it. What the map does take from the same logic is the natural-balance signal in §6.1, which concerns position rather than the graph.

### 3.3 Why a bipartite rewrite

A single journal can touch many accounts. Characteristic analysis depends on **pairwise value flow**: which account funded which account, how often, and for how much.

**Exact-cover averaging** is the default rewrite. For transaction $T_i$ with total weight $W = \sum w(DR) = \sum w(CR)$, every debit–credit pair becomes an edge:

$$
Y_i = DR \times CR, \qquad w(DR_j, CR_k) = \frac{w(DR_j)\,w(CR_k)}{W}
$$

Two-line transactions collapse to a single edge with weight $W$. Multi-line journals distribute weight proportionally, so edge weights still sum to $W$. Averaging conserves weight and makes no assumption about which lines belong together.

**Minimal rewrite** splits a journal into balanced subsets before averaging, so that only lines belonging to the same event are paired. The subsets are recovered by taking exact covers of the lines: a subset is an event when its debits and credits balance on their own, and the finest such partition is the journal's real content. Because line weights are positive, any subset summing to zero necessarily holds both a debit and a credit, so balance alone identifies a candidate event.

**Wide journals need this most.** A journal's width is evidence about its nature. A large entry is characteristically a catch-up posting, where a period's activity has been brought onto the books in one document for convenience rather than posted event by event. Such an entry is a bundle of unrelated events by construction, so averaging across it produces a dense block of edges that were never posted, and the number of false edges grows with the square of the width. The wider the journal, the more the minimal rewrite recovers.

**A split is taken only when it is forced.** Where several balanced subsets of the same size compete for the same lines, the journal does not record which pairing occurred, and choosing one would substitute an unmeasured guess for a measured estimate. Consider a journal debiting two accounts 100 each and crediting two others 100 each: two partitions are equally consistent with it, and neither is the posting. Those lines stay together and averaging handles them, which is the honest treatment because averaging reports its own uncertainty through the ambiguous share below.

**Forcing is a property of a subset, not of a journal.** An ambiguous cluster says nothing about the clean events beside it, so it suppresses only its own lines. A catch-up entry carrying two hundred settled events and one unresolvable cluster yields two hundred events and one residue, not a refusal. Splitting therefore removes ambiguity wherever the journal resolves it, and introduces none where it does not.

The two rewrites agree on every journal that carries one line on either side, and on every journal that admits no forced split. They differ on packed journals, where the minimal rewrite is the more faithful reading and averaging is the conservative one.

**Pairing confidence** distinguishes the two cases the product creates. The product is an estimate only when both sides carry several lines. A journal with a single line on either side pins its pairings exactly: an $(n,1)$ journal apportions $w(dr_j, cr_1) = w(dr_j)$, which is not an average. Every edge therefore carries an **ambiguous share**, the fraction of its weight sourced from many-to-many journals. This is the paper's proportion of reduced hyperedges, and it is the measure that addresses the false-edge problem. An edge with a 100% ambiguous share exists only because the rewrite paired lines that may never have been related, and it is weak evidence rather than a peer of observed flows.

### 3.3.1 Self-loop edges

When one account is debited *and* credited in the same journal, $DR \times CR$ emits an $(a, a)$ edge. No account funded another, so it records no value movement; it is an artifact of the rewrite.

Such edges are not rare. On the reference entity, 5 of 190 edges are self-loops, and they carry **18.4% of total weight** and occupy two of the top five spectrum slots.

Policy:

- **Retain them.** Dropping them would break $\sum_{j,k} w(dr_j, cr_k) = W$, and the prototype includes them, so removal would also break parity.
- **Label them.** Every edge exposes a self-loop flag, and its share of total weight is reported.
- **Never read them as postings.** They are decided *before* any account-type reasoning, because a self-loop's type pair is identical on both sides by construction and the type table would misread it. A Bank-against-Bank pair normally indicates a transfer between two different bank accounts, and matching types on both sides otherwise suggests reclassification.

A posting whose entire content is one account against itself is a separate case. It moves no value and is almost certainly an error, whatever the account type, so verification fails it outright (§5.1).

### 3.4 Aggregation into the characteristic map

After rewriting all $T$ in a window of periods:

1. **Collapse identical edges** $(a_{dr}, a_{cr})$ across transactions.
2. Store per edge at least:
   - **Edge sum** — total rewritten weight
   - **Depth** — how many source transactions contributed
   - **Pair instances** — how many DR×CR emissions; a count above depth means multi-line journals fed the edge
   - **Ambiguous share** — fraction of weight from many-to-many journals, per §3.3
   - **Self-loop flag** — whether both endpoints are the same account, per §3.3.1
   - Optionally the mean amount, recurrence over periods, standard deviation, and contact
3. Materialize square or sparse matrices over accounts:
   - $W[a_{dr}, a_{cr}]$ — weight
   - $C[a_{dr}, a_{cr}]$ — count, or depth

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
- Not full accrual-flow tracing from invoice through payment on its own; edges and account types $B$ are the substrate for that.
- Not a claim that every averaged multi-line edge represents a real relationship. Noise exists, but dominant edges dominate the ranking.
- Not dependent on any particular accounting product. The transaction types such products predefine assist labeling, not the graph math.

---

## 5. Three uses being proven

### 5.1 Verification of posted transactions

**Question:** Given a newly posted or candidate transaction, does it fit this entity's established map?

**Method:**

1. Rewrite the candidate into edges $Y^*$.
2. For each edge, look up historical $W$, $C$, and account-type expectations from $B$ or from characteristic transaction tables. An expense, for example, is usually debited against a bank or card credit.
3. Score:
   - **Known strong edge** — high historical weight and depth, supporting the posting.
   - **Known weak or rare edge** — present but low-ranked; allow with lower confidence or flag for review.
   - **Unseen edge** — never, or almost never, observed. Treat as an anomaly unless the account types still form a valid characteristic pair, as a first rent payment to a new landlord GL remains Expense against Bank.
   - **Type-illegal or reclass-suspicious** — the same non-cash type on both sides often indicates reclassification; cash against cash is transfer-like; combinations the type matrix marks as invalid can hard-fail or hard-warn.
   - **Self-loop** — decided before type logic, per §3.3.1. If the whole posting is one account against itself it **fails**, because it moves no value. If the loop is an artifact of rewriting a larger journal, it is noted and casts no vote.

   Line weights are confirmed positive before any of this runs. A negative line can still balance, so the balance check alone would pass it through to the rewrite and produce a negative edge weight, which §3.2 declares invalid.

**Output useful in a demonstration:** per-transaction pass, warn, or fail with the contributing edges and their historical percentiles, rather than a single opaque number.

Verification answers whether a posting is consistent with how this business has moved value.

### 5.2 Prediction of future or incomplete transactions

**Question:** Given a partial observation — one side of an exchange, a bank amount, an account, a contact — which counterparts are most likely?

**Method:**

1. Condition on the known node, meaning the account, the side, or both.
2. Read the row or column of $W$ and $C$, or of the normed matrix, to rank counterpart accounts by probability mass.
3. Refine with:
   - account type $B$, so that a bank feed outflow carries Expense, A/P, Card, and loan payoff priors,
   - **period seasonality**, conditioning the counterpart distribution on the same slot in prior years rather than on the whole window,
   - **feed-side priors**, indicating which side of the edge is usually pre-populated from a bank or card import and which side is therefore the one worth ranking.

**Seasonality.** Averaging a counterpart distribution over the whole window buries any edge that occurs in only part of the year. Conditioning on the same month or quarter in prior years reads mass from comparable periods only, so seasonal counterparts surface and out-of-season ones drop out entirely. This requires per-period edge mass to be retained during aggregation, not just an edge total. The target period is excluded from its own conditioning set, since predicting for a period using that period's activity would be circular.

**Demonstration shape:** given an operating bank account, the credit side, and an approximate amount, return ranked debit accounts with each counterpart's historical share of that node's activity and typical amount bands. Adding a season ranks against comparable periods instead.

Prediction answers which counterpart is characteristic for a given movement.

### 5.3 Scale-independent anomaly and trend insight

**Question:** Has the structure of activity changed in a way that should change decisions, even where P&L totals look familiar?

**Method:**

1. Build maps for two windows: trailing 12 closed months against the current open month, or the same months year over year.
2. Compare distributions of edges and account participation ranks:
   - edges that **appeared** or **vanished**,
   - large **rank shifts** in normed score,
   - concentration changes, where few edges dominate more or less than before,
   - growth in Uncategorized, clearing, or discrepancy accounts,
   - new edges that violate type expectations at rising volume.
3. Because the representation is relative — shares, ranks, probabilities — the same machinery applies to a 50-transaction sole proprietorship and to a multi-entity group. Scale differences appear as depth and absolute weight, not as a different algorithm. The same relativity is what lets the comparison cross entities rather than windows (§6.2).

**Demonstration shape:** a table of top Δ-ranked edges and new edges in $P_{open}$ against baseline $P_{-n}$, with account-type tags.

Anomaly insight answers how the pattern of value movement is changing.

---

## 6. Account types as a second axis

The graph alone names accounts. The type map $B$ supplies meaning:

- **Natural balance** — whether a debit increases the account.
- **Role in flows** — cash, accrual holding such as A/R and A/P, temporary P&L, equity, and so on.
- **Characteristic pairs** — an invoice is approximately DR A/R and CR Revenue; a bill payment is approximately DR A/P and CR Cash or Card.

Use $B$ to:

- color and group matrix output,
- separate a surprising account pair from a surprising *type* pair,
- bootstrap priors where historical depth is thin, as with a new entity or a new account,
- compare one entity against another, since types are the only axis two charts of accounts share (§6.2).

Base groups: Assets, Liabilities, Equity, Income, Expense, with contra and clearing accounts treated explicitly where present.

### 6.2 Cross-entity comparison

Account identifiers are entity-specific. One entity's `1000 Bank` and another's `10100 Operating` are the same thing under different names, and no key matches them, so two entities' edge distributions cannot be compared directly. The type map is the bridge: projecting each entity's edges onto pairs of account types puts every entity on one axis, and because the map is already expressed in shares, the projections compare across entities of any size.

**Granularity is a trade.** Base groups — Asset, Liability, Equity, Income, Expense — compare across any chart of accounts, because every type vocabulary maps onto them. Raw types are finer but only comparable where two entities happen to label types the same way, and products differ on exactly that: `Expense` against `Expenses` is a labelling difference, not an accounting one. Base groups are therefore the robust default and raw types the sharper instrument for entities known to share a vocabulary.

**Self-loops are excluded before projection.** A self-loop's type pair is identical on both sides by construction (§3.3.1), so retaining them would load the diagonal of the type matrix with rewrite artifacts and read as reclassification the entity never posted. The excluded share is reported rather than silently dropped, since it is itself a fact about the books.

**Distance between two entities** is the total variation between their type spectra: half the summed absolute difference in share across every type pair either entity uses. It runs from 0, meaning the two move value across the same type pairs in the same proportions, to 1, meaning they share none. It reads directly as a quantity — a distance of 0.4 says two fifths of one entity's flow would have to move to a different type pair to match the other.

**Benchmarking** positions one entity against a group of peers rather than against a single counterpart. Each peer contributes its share of every type pair equally, so the group describes the peers rather than its largest member, and a peer that never uses a pair counts as a zero rather than being omitted — omitting it would compare the subject only against peers that behave as it does. The result is per type pair, not a single score: which pairs the entity over-weights, which it under-weights, which its peers use and it does not, and which it uses alone.

That distinction is the point. A score says an entity is unusual; a ranked set of type pairs says an entity funds its operating costs on a credit card where its peers use a bank account, which is a statement someone can act on.

### 6.1 Natural balance as a quality signal

Each type implies a characteristic balance direction — the paper's $\tilde{B} = \{+1 \text{ if } DR,\ -1 \text{ if } CR\}$, keyed to the type's initialization side. Asset and expense types run debit; liability, equity, and income types run credit. This sign is carried by the *account type*, not by a per-line convention: the $DR - CR$ subtraction inside the balance definition already accounts for line direction.

The cheapest available check follows from it. Does an account's closing balance sit where its type says it should? A bank account with a credit balance is overdrawn. That is possible, but remaining so for a whole period or more indicates a lag in accuracy or completeness rather than a real position.

**Contra accounts are the complication.** Accumulated Depreciation is a fixed asset that always carries a credit balance, because it exists to reduce a sibling asset on the same side of the sheet. Allowances, sales discounts, and treasury stock behave the same way. Reporting them every period would bury the real signal, and nothing in a chart of accounts marks them explicitly.

Contra status is therefore **inferred** from three pieces of evidence, weighted so that no single weak signal decides:

| Evidence | Weight | Rationale |
|----------|--------|-----------|
| Sits opposite a same-type parent resolved from `Parent:Child` chart hierarchy | +2 | A contra is characteristically a child of the balance it reduces |
| Has been on the non-natural side in every period it carried a balance, over at least 3 periods **and** covering at least 60% of its life | +2 | A contra is off-side by construction, from inception |
| Name matches a known contra form | +1 | Corroboration only; a label is not evidence about the books |

Two rules matter more than the weights:

- **Peer comparison is not scored.** An account sitting opposite its same-type peers is equally consistent with a contra and with an error, so it cannot discriminate between them.
- **Coverage is required alongside consistency.** An account that is flat most months and dips the wrong way occasionally has never held a natural-side balance either, yet it presents a timing problem rather than a contra. Requiring the off-side condition to span most of the account's life separates the two.

An account is reported when its balance sits opposite its *effective* natural side, flipped where contra status was inferred, with the run length attached. One period may be a timing difference; several consecutive periods constitute the signal.

---

## 7. Periods, windows, and present bias

The baseline is drawn from recent closed periods, typically 12 to 18 months, and the open period is compared against it. A simple forward expectation for variance analysis:

$$
\hat{E}(P_1) = \frac{1}{n}\sum_{-n}^{-1} E(P)
$$

This projects average period activity forward and measures open-period deviation in graph space, not only in trial-balance totals. The projection is the mean *over* the trailing closed periods, not a single period divided by $n$.

Every line carries a date, so periods require no additional input contract: a period key derives month, quarter, or year labels that sort chronologically as strings.

Two consequences follow:

1. **Windowed builds.** A baseline is a date-bounded slice of one ledger, not a separately curated file. Bounds are inclusive and applied to lines, so a window that cuts a journal in half produces an unbalanced transaction and fails validation. That is the correct outcome: such a window does not describe a real set of books.
2. **Honest holdout.** Splitting by period is what makes a prediction holdout meaningful — build from closed periods, then evaluate on transactions from a period the map never saw. Edge-type overlap between the two is not leakage, since a stable business repeats its edges every month. What matters is that the transactions themselves were excluded.

Period count matters for the projection: a handful of periods gives a mean too noisy to read a variance against, which is why the trailing window defaults to 12.

Deviations can be ranked two ways. Structural size, meaning weight and depth, is scale-free and needs no entity-level input. Dollar materiality weights the same deltas by the amounts at stake, and requires a threshold that is a judgement about the entity rather than a derivable quantity.

---

## 8. Reference prototype — behavioral contract

The aggregation half of this idea was first prototyped as a spreadsheet over a live chart of accounts. Its artifacts define what an implementation reproduces:

| Artifact | Role in the concept |
|----------|---------------------|
| Distinct DR\|CR edges with sum and depth | Aggregated rewrite output |
| Weight and count matrices | Dense view of $W$ and $C$ |
| Normed blend against global totals | Ranking, or spectrum |
| Filtered multisort of high-activity accounts | Characteristic accounts for inspection |
| Chart-of-accounts type list | $B$ labels |

Reduced to a portable form, that is an aggregated edge list — one row per distinct debit–credit pair, carrying the two endpoints, the summed weight, and the contributing transaction depth — alongside an account-to-type lookup. Everything else in the table above derives from those two tables. An entity published in that form, carrying the expected norm and conditional probability for each edge, makes the contract testable without the original spreadsheet.

**Coverage of the prototype edge list.** It carries 10 columns, of which 6 carry information the map uses:

| Columns | Status |
|---------|--------|
| Debit node, credit node, edge sum, edge transaction depth | The aggregated edge list itself |
| Two conditional-probability columns | Reproduced exactly by prediction: edge weight ÷ total weight at that node on that side, matching on all 190 edges |
| Feed-side annotation | Absent on 70 of 190 rows, so the annotation is too incomplete at source to support the feed-side priors of §5.2 |
| Per-account probability | Constant `1.0` on all 190 rows; carries no information |

An implementation proves the idea when it reproduces this pipeline from journal lines or from an edge list, emits the same classes of artifacts as logs and tabular output, and applies those artifacts to the three uses in §5 on held-out or synthetic cases.

---

## 9. Scope of a demonstration

A demonstration of this concept covers:

1. Ingest of balanced transaction lines, from journal-line files or from an aggregated edge list.
2. Rewrite, aggregation, and output of edges, the weight and count matrices in sparse long form, and the ranked spectrum.
3. Logging of transaction and edge counts, top characteristic edges, and open-against-baseline deltas where two windows are given.
4. Verification and prediction against the built map.
5. Period windowing, per-period edge mass, forward expectation, and seasonal conditioning inside prediction, per §5.2 and §7.
6. Natural-balance reporting with contra inference, per §6.1.
7. Cross-entity comparison and benchmarking against a peer group, per §6.2.
8. Measurement of the success criteria in §10.

Terminal logs and tabular artifacts are sufficient. A user interface proves nothing about the concept.

---

## 10. Success criteria for the concept

The concept is supported if, on real or realistic books:

1. **Verification** — held-out normal postings score as in-distribution on their edges, while deliberately wrong type pairs and random account pairs score worse in an explainable way.
2. **Prediction** — given one side of a frequent historical edge, the true counterpart ranks near the top of the conditional distribution more often than chance or a type-only baseline.
3. **Anomalies** — injected regime changes, such as a new financing edge, a surge in clearing activity, or the disappearance of a core sales edge, appear as top structural deltas between windows without requiring the user to read every journal.

Scale-invariance is demonstrated when the same code path, using share and rank metrics, produces useful rankings for both a small sample entity and a larger edge set without parameter retuning beyond the choice of window.

---

## 11. Glossary

| Term | Meaning |
|------|---------|
| Edge | Ordered pair of debit account and credit account, with weight |
| Depth | How often that edge was produced by the rewrite |
| Characteristic map, or spectrum | Ranked distribution of aggregated edges and accounts |
| Rewrite | Expansion of a multi-line journal into DR×CR edges |
| Baseline window | Historical periods used as the reference for normal activity |
| Open window | Current or candidate period under scrutiny |

---

## 12. Summary

Books already encode a graph of control over value. The Accounting Logic Map makes that graph explicit, aggregates it into a stable signature, and applies the signature three ways: checking postings against history and type logic, inferring missing counterparts from conditional edge mass, and monitoring whether the entity's pattern of movement is drifting.
