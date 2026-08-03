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

## 3. Extending the scope

### 3.1 Cross-entity comparison

Because the representation is relative — shares, ranks, and probabilities — the
characteristic spectra of two entities are directly comparable, and the same
machinery that compares two windows of one entity would compare two entities over one
window. Applications include benchmarking an entity against sector peers, and
detecting a group of entities whose books have drifted apart.

**Depends on** a mapping between charts of accounts, since the account identifiers
that key the edges are entity-specific. Account types $B$ supply a coarse mapping
already, which makes type-level comparison reachable before account-level comparison
is.

**Changes** what the signature is for: from a description of one business over time to
a position among comparable businesses.
