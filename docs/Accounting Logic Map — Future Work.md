# Accounting Logic Map — Future Work

**Companion to:** [`Accounting Logic Map — Concept Definition.md`](./Accounting%20Logic%20Map%20%E2%80%94%20Concept%20Definition.md)

**Purpose.** Hold the capabilities the Accounting Logic Map is designed to admit but
does not yet implement, so that the Concept Definition can describe the model as it
stands without qualifying every section with what is missing. Each entry states what
the capability is, what it depends on, and what it would change about the map's
output.

Nothing here is required for the three uses the concept proves. Everything here is
reachable from the model as defined, which is the point of recording it.

---

## 1. Extending the projection

The base entity image in concept §3.1 holds seven element sets. The characteristic map
projects four of them — accounts $A$, account types $B$, transactions $T$, and periods
$P$. The remaining three are defined in the image and unused by the projection.

### 1.1 Contact-conditioned edges

**Element:** contacts $Q$, with subsets for owners, customers, vendors, and employees.

Edges are currently keyed on the account pair alone. Keying them on
`(debit account, credit account, contact)` would separate flows that share a pair but
belong to unrelated counterparties: two vendors billed through the same expense and
payable accounts are one edge today and would be two.

**Depends on** a contact identifier reaching the line-level input contract, which v1
does not carry. Most accounting systems hold one; exporting it is the work.

**Changes** prediction most: conditioning on a known contact narrows the counterpart
distribution far more sharply than conditioning on the account alone, which is the
common case when a bank feed line arrives with a payee but no category.

### 1.2 Process and control-document structure

**Elements:** recorded processes $J$ and control documents $D$.

Posting, reconciliation, and close are recorded procedures, and the image treats them
as hyperedges alongside transactions. Estimating a control map from them would let the
graph carry not just how value moved but under what procedure and with what
supporting evidence — the difference between a posting that was reconciled and one
that was not.

**Depends on** access to audit-trail and reconciliation records, which sit outside the
journal export most systems make easy.

**Changes** verification: a posting consistent with the edge distribution but produced
outside the normal process is currently indistinguishable from one produced inside it.

### 1.3 Accrual chain reconstruction

Invoice to payment, bill to bill payment, and the other settlement pairs described by
account types are chains of transactions, not single edges. Reconstructing them would
recover flow objects — the whole life of a receivable — rather than the pairwise
movements the map records.

**Depends on** contact conditioning and on the type-pair matrix below, both of which
supply the evidence for linking an initialization to its settlement.

**Changes** the unit of analysis. The map would gain a second layer above the edge
distribution, at which questions about timing and aging become answerable.

---

## 2. Refining the scores

### 2.1 Full type-pair prior matrix

The concept's account-type tables describe characteristic pairs for every transaction
form — invoice as DR A/R against CR Revenue, bill payment as DR A/P against CR
Cash or Card, and so on through the settlement types. Verification currently consults
a heuristic subset of those pairs rather than the full matrix.

**Depends on** transcribing the tables from the concept's source material into a
lookup the type reasoning can consult.

**Changes** verification of unseen edges. A pair the entity has never posted is
currently judged by a short list of common combinations; the full matrix would place
it against every documented transaction form, and would distinguish a genuinely
unusual pair from one that is merely new to this entity.

### 2.2 Feed-side priors

Each edge has a side that is typically pre-populated from a bank or card import, and
the other side supplied by categorization. Knowing which is which sharpens prediction,
because the unknown side is the one worth ranking.

**Depends on** a complete feed-side annotation at source. The prototype's aggregated
edges carry the field, but it is absent on 70 of 190 rows, so the prior cannot yet be
estimated from it. This is a data gap, not a modelling one.

**Changes** prediction, by removing counterparts that would never be the missing side
of a query.

### 2.3 Dollar materiality weighting

Structural deltas between windows are currently ranked by structural size — edge
weight and depth. Materiality would weight them by the amounts at stake instead, so
that a small structural change on a large flow ranks above a large structural change
on an immaterial one.

**Depends on** a materiality threshold, which is an entity-level judgement rather than
a derivable quantity.

**Changes** the anomaly ranking only. Both orderings are defensible and serve
different readers, so this is a configurable alternative rather than a replacement.

### 2.4 Direction-merged account pairs

Edges are ordered: `(a, b)` and `(b, a)` are separate entries, and each is scored
against the whole map on its own. Where value moves both ways across the same pair —
transfers between two bank accounts, a charge and its refund, an accrual and its
reversal — the relationship is split across two edges, and each ranks lower than the
relationship as a whole.

A merged view would key on the unordered pair and carry both directions on it: total
weight through the pair, net weight in the dominant direction, and the share flowing
against it.

**Depends on** nothing outside the current map. It is a second projection of the
same edges, and the ordered map remains the primary one, because direction is itself
information.

**Changes** ranking and anomaly reading. A pair with heavy two-way flow and little
net movement is churn, and one that turns from one-way to two-way between windows is a
structural change that neither ordered edge shows on its own.

### 2.5 Edge recurrence and dispersion

Concept §3.4 lists recurrence over periods and standard deviation as optional edge
statistics. The map already records per-period mass for every edge where the source
carries dates, so both are derivable: the number of periods in which an edge is
active, the regularity of its gaps, and the dispersion of its per-period weight.

**Depends on** nothing outside the current input contract.

**Changes** all three uses. Two edges with the same weight and depth can be a steady
monthly flow or a single burst, and the normed score cannot tell them apart.
Verification could treat a posting on a steady edge as expected and one on a sporadic
edge as weaker evidence; prediction could prefer recurring counterparts; and anomaly
detection gains a measured expectation for whether an edge should appear in the open
window at all.

### 2.6 Account-level comparison through a standard chart

Cross-entity comparison (concept §6.2) goes through account types, because they are
the only axis two charts of accounts share. In practice most charts are variations
on a standard set of accounts, differing mainly in labels and granularity. Mapping
each entity's accounts onto one standard chart would give a shared axis finer than
types: operating bank, payroll liabilities, and software subscriptions compare
directly, where the type projection merges them with everything else of the same type.

**Depends on** a mapping from each entity's accounts to the standard chart. The
mapping can be supplied, or inferred from name, type, parent account, and position in
the entity's own map; an inferred mapping would need to report its confidence, since
a wrong mapping produces a confident-looking wrong comparison.

**Changes** benchmarking resolution, and gives a new or thinly populated entity a
source of priors: the standard chart populated from comparable entities, which is
also a basis for proposing a starting chart of accounts for a new entity by industry.

---

## 3. Extending the time axis

The map places every line in a period and then keeps only the period label. Where
within `2025-03` a line fell is discarded, although every line already carries a full
date. That discarded coordinate does not describe how value moved; it describes how
the record was made, which is a different characteristic of an entity and a distinctly
useful one.

### 3.1 Intra-period posting cadence

**What it measures.** Restoring within-period position gives each period a shape: the
distribution of transaction count and weight across the period's span, expressed as a
position in [0, 1] so that periods of unequal length compare. The shape is a
characteristic of the bookkeeping rather than of the business.

| Shape | Reading |
|-------|---------|
| Spread across the period | Postings made as events occur |
| Concentrated at the close | Catch-up: a period brought onto the books in one sitting |
| Concentrated at the open | Prior-period work landing late, or cleanup by a reviewer |
| Repeating peaks | A cadence — payroll runs, billing cycles, card statement dates |

**Measures.** Three fall out of machinery the implementation already has:

- **Centroid** — the weight-weighted mean position, one number per period. Near 0.5 is
  balanced; drift toward 1 over successive periods is drift toward catch-up posting.
- **Concentration** — the share of a period's weight landing in its final days, or the
  entropy of the day distribution. Either reads as how much of the period was recorded
  in how little of it.
- **Stability** — one period's shape against the entity's own average, using the total
  variation distance of concept §6.2, which needs only two distributions rather than
  two type spectra. This is the distinction that matters: a consistent month-end spike
  is a process, while an erratic shape is the absence of one, and a single number for
  concentration cannot tell them apart.

A first-order signal is already reachable without new measurement. The minimal rewrite
identifies wide journals, and a wide journal is characteristically a catch-up entry
(concept §3.3), so a per-period count of journals wide enough to decompose is a proxy
for cadence that needs no additional data.

**Depends on** nothing outside the current input contract. Reading the result as
*timeliness* rather than as event timing depends on §3.2.

**Changes** four things:

- It adds a control-quality axis orthogonal to the edge distribution. The map says how
  value moves; cadence says how faithfully and how promptly it was recorded. Concept
  §3.1 places processes $J$ and control documents $D$ in the entity image for exactly
  this class of question, and cadence is the part of it reachable from the journal
  alone.
- Anomaly detection gains a signal that does not depend on edges at all. A period whose
  posting shape breaks from the entity's own norm is worth attention even where every
  edge in it is ordinary, and the reverse holds too: a structural change posted on the
  entity's usual cadence is more likely to be a real change in the business than a
  recording artifact.
- Cross-entity benchmarking extends to it. An entity's cadence compares against peers
  the same way its type spectrum does, so whether a set of books is tidier or messier
  than comparable ones becomes a measured quantity rather than an impression.
- It is useful where nothing is wrong. Even with every posting legitimate and timely,
  the distribution says when the work falls. That is a staffing question for the
  recorder, and for a reviewer inheriting an unfamiliar set of books it answers where
  the crunch sits and what is due to land when — which is otherwise learned only by
  living through a close.

### 3.2 Posting lag against the entry record

**What it measures.** The gap between when an event occurred and when it was recorded.
Position within a period is a proxy for this, and it confounds two different things: a
genuine month-end event recorded promptly and a mid-month event recorded at the close
land in the same place.

**Depends on** an entry timestamp distinct from the transaction date. Accounting
systems generally record creation and modification times per transaction; the
line-level input contract carries only the posted date, so this is an export question
rather than a modelling one. Attributing lag to a particular recorder depends further
on the process element $J$ of §1.2.

**Changes** the readings in §3.1 from inference to measurement, and separates the two
populations that matter for control: events recorded late, and events that genuinely
occur at period boundaries. Only the first is a finding about the books.

### 3.3 Edge-level forward expectation

The forward expectation of concept §7 is computed on period totals: expected weight
and transaction count for the open period against the mean of the trailing closed
periods. Anomaly detection compares whole maps by share and rank. Neither says, in
amounts, which account pairs carry the open period's variance.

An edge-level expectation projects each edge's per-period mass forward over the
trailing window — six or twelve closed periods, or the same period in prior years
where the entity is seasonal — and distils the open period's variance into a ranked
list of account pairs. Two forms answer different questions:

- **Absolute variance** compares the magnitude of flow through a pair, and reads as a
  change in volume.
- **Net variance** lets flows in opposite directions offset (§2.4), and reads as a
  change in the balance moved. A pair whose absolute variance is large and whose net
  variance is small has churned without moving value.

Projecting the normed score rather than raw weight gives the same expectation in
scale-free form, so it compares across entities and across periods of different
activity. Set against the structural comparison, this separates the two kinds of
change a period can carry: a change in *which* pairs move value, which the anomaly
comparison measures, and a change in *how much* moves through pairs that were already
active, which this measures.

**Depends on** nothing outside the current input contract; per-period edge mass is
already recorded.

**Changes** variance analysis from "the period is 12% heavier than expected" to "these
five account pairs account for the difference", which is the form a reviewer acts on.

### 3.4 Periodic structure and decay

Seasonal conditioning compares a period with the same period in prior years. That
captures an annual cycle and nothing else: quarterly filings, biannual insurance, and
billing cycles that do not align with months are treated as noise.

Treating each edge's per-period mass as a time series admits standard signal methods.
A frequency decomposition identifies the cycles an edge actually follows, and can
reconstruct an expected series from sparse observations. Exponential decay weighting
in place of a flat trailing window expresses the present bias of concept §3.1
directly, rather than as a hard cutoff. Differencing along the time axis measures how
fast an edge's share is changing, not only whether it has changed.

**Depends on** enough history to observe a cycle more than once, which for annual
effects means at least two years of periods.

**Changes** prediction and forward expectation, by replacing a single seasonal
comparison with the cycles each edge exhibits.

### 3.5 Measurement error and estimate error

Two sources of error sit in any comparison of the books with an expectation.
**Measurement error** comes from the data: an accounting file that has not synced, a
feed that lags, a period not yet fully posted. **Estimate error** is the variance
between a correct measurement and the predicted value. The map currently treats every
difference as the second kind.

A recursive estimator such as a Kalman filter keeps the two apart: it carries an
expectation and its uncertainty forward period by period, and weighs each new
observation by how reliable the measurement is known to be. Account type and account
detail supply the structure of the expectation; data staleness supplies the
measurement uncertainty.

**Depends on** knowing how current the source data is — a sync or extraction
timestamp alongside the export, related to the entry-time question in §3.2.

**Changes** anomaly and variance reporting, by discounting differences that are
explained by stale data rather than reporting them as changes in the entity.

---

## 4. Refining the rewrite

### 4.1 Rewriting by transaction form

Both rewrites work from line amounts alone. Averaging pairs every debit with every
credit; the minimal rewrite separates only the events the amounts force apart. Many
multi-line journals, though, are instances of a known form whose internal pairing is
not in doubt: an invoice with shipping, sales tax, and a discount credits revenue,
shipping income, and tax payable against one receivable, and applies the discount
against revenue. The form says which lines belong together even where the amounts
would admit several partitions.

A form-aware rewrite would recognise the form and apply its pairing, falling back to
the minimal rewrite and then to averaging where no form matches.

**Depends on** a transaction type or form reaching the input contract — most systems
record one — and on the characteristic pairs of §2.1 to define each form's pairing.

**Changes** the ambiguous share. Journals the minimal rewrite must leave whole
because competing partitions exist can be resolved by evidence other than amounts,
without guessing.

### 4.2 Pre-aggregated postings

Depth counts source transactions. Where repeated similar transactions within a period
have been posted as one — a daily sales summary, a monthly batch of card fees — one
transaction stands for many, and the edge's depth understates its recurrence while
its mean-size share overstates the size of each event.

Detecting such postings needs a signal that a transaction is an aggregate: a memo or
form that says so, a regular posting date with amounts that vary as a sum would, or
an edge whose depth is lower than comparable entities show for the same type pair.

**Depends on** those signals being present. An aggregate that leaves no mark cannot
be distinguished from a single large event, and the map records it as one.

**Changes** the depth and mean-size terms of the normed score for the affected
edges. Whether aggregation is a defect depends on the reader: an aggregated posting is
correct bookkeeping, and the map needs only to know how many events it represents.

### 4.3 Edge co-occurrence

The rewrite projects each transaction hyperedge onto pairwise edges and then treats
the edges independently. Which edges were produced by the same journal is discarded.
Keeping it gives a second graph whose nodes are edges and whose links are
co-occurrence within a journal: an edge adjacency matrix over the map.

That graph recovers the forms of §4.1 from the data itself, since a form is a set of
edges that recur together. With the period axis added, the edge-to-period and
edge-to-edge relations form a tensor over accounts and time, which is the natural
setting for predicting the next period's state rather than only its totals.

**Depends on** retaining transaction identity through aggregation, which the map
currently collapses.

**Changes** verification of multi-line postings. A journal whose individual edges are
each familiar, but which combines them in a way the entity has never posted, is
currently judged edge by edge and passes.

---

## 5. Cash-basis views

### 5.1 Cash-basis projection

The map describes the books as posted, which for most entities is the accrual basis.
A cash-basis view can be derived from the same edges rather than from a second set of
books: flows from assets to expenses and from liabilities to revenue that record
accrual rather than payment are excluded, and the settling cash movements are
reclassified to the income and expense accounts the accruals named.

Excluding flows is straightforward; the reclassification is the work. A single
payment can settle several accruals across several accounts, so the settled amounts
have to be apportioned back to the accounts they originally named, and flows that
carry information cash basis would otherwise lose — a prepaid expense amortised across
several accounts over a period — need to be kept rather than excluded.

**Depends on** the accrual chains of §1.3, which link each settlement to the accruals
it clears.

**Changes** reporting. Dual-basis reporting comes from one map, and the difference
between the two views is itself a measure of how much of the entity's activity is
timing.

### 5.2 Receipt and spend bifurcation

Cash accounts sit on both sides of the map: debited when value is received and
credited when it is spent. Splitting the map at cash into a receipt graph and a spend
graph gives two distributions that each read directly as a categorised cash rollup —
where cash comes from and where it goes — and that can each be compared across
windows and entities on their own.

**Depends on** identifying cash accounts, which the account-type map already does.

**Changes** anomaly reading, by keeping a shift in spending from being diluted by
unrelated receipts in the same map, and provides the cash-flow view that the
account-pair spectrum does not show directly.

---

## 6. Assisted posting

Prediction ranks counterparts. Posting a transaction requires a decision, including
the decision not to post.

### 6.1 Match first, then rank, then abstain

An incoming feed line is first checked against open items — an unpaid invoice or bill
of matching amount — since a match settles an existing record and is a fast, exact
decision. Matching becomes a search when several feed lines may settle one item or
one line several items.

Where nothing matches, the counterpart is ranked by successively broader evidence:
prior postings with the same bank description, then the same amount on the same side,
then position within the period, with year-to-date history weighted more heavily once
several months have closed. A line whose evidence does not narrow the counterparts to
a small set is posted to an uncategorised account rather than guessed.

**Depends on** feed-side priors (§2.2), the bank description reaching the input
contract, and access to open items.

**Changes** prediction from a ranking into a decision with a stated confidence and an
explicit abstain, which is what automated categorisation needs.

### 6.2 Reconciliation as exact cover

Reconciling a bank or card statement against the books is an exact-cover problem:
partition the statement lines and the recorded transactions into groups that settle
against each other. Where several sources feed the same accounts — a bank feed, a
payment processor, a payroll provider — a recurring event appears in each and the
covers have to be joined across sources.

The minimal rewrite (concept §3.3) solves a related problem and refuses to choose
between competing partitions, because a journal records no further evidence. A
reconciliation has to choose, so it can use evidence the rewrite cannot: the map's
own edge probabilities, dates, and the recurrence of §2.5 rank the candidate covers,
and the ranking's confidence is reported with the match.

**Depends on** statement data alongside the journal export.

**Changes** the scope of the map, from describing posted activity to reconciling it.

---

## 7. Evaluation

### 7.1 Adversarial postings

Verification is evaluated against hand-built candidates and injected anomalies. A
generator trained to produce postings the verifier accepts but that do not fit the
entity would probe it systematically: each accepted posting is a gap in the verifier,
and the generator's success rate measures how much room the gap leaves.

**Depends on** a label for what does not fit, which in practice means a reviewer or
a held-out set of known errors.

**Changes** the success criteria of concept §10, from fixed cases to a measured
resistance.
