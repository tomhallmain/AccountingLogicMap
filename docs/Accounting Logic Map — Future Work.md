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
