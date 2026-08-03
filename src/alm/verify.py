from __future__ import annotations

from .models import (
    BALANCE_TOLERANCE,
    RARE_EDGE_RANK_FRAC,
    EdgeFinding,
    LogicMap,
    Transaction,
    VerifyResult,
)
from .rewrite import rewrite_transaction

# Type pairs that are common even for first-time account combinations.
COMMON_TYPE_PAIRS = {
    ("Expense", "Bank"),
    ("Expense", "Credit Card"),
    ("Cost of Goods Sold", "Bank"),
    ("Cost of Goods Sold", "Credit Card"),
    ("Cost of Goods Sold", "Accounts payable (A/P)"),
    ("Accounts receivable (A/R)", "Income"),
    ("Bank", "Income"),
    ("Bank", "Accounts receivable (A/R)"),
    ("Accounts payable (A/P)", "Bank"),
    ("Accounts payable (A/P)", "Credit Card"),
    ("Expense", "Accounts payable (A/P)"),
    ("Credit Card", "Bank"),
    ("Bank", "Bank"),
    ("Other Current Liabilities", "Bank"),
    ("Long Term Liabilities", "Bank"),
    ("Bank", "Equity"),
    ("Equity", "Bank"),
}

# Same non-cash type on both sides often signals reclassification.
RECLASS_TYPES = {
    "Expense",
    "Income",
    "Cost of Goods Sold",
    "Other Current Assets",
    "Fixed Assets",
    "Other Assets",
    "Other Current Liabilities",
    "Long Term Liabilities",
    "Equity",
}


def _normalize_type(t: str) -> str:
    return t.strip()


def _is_common_type_pair(debit_type: str, credit_type: str) -> bool:
    dt, ct = _normalize_type(debit_type), _normalize_type(credit_type)
    if (dt, ct) in COMMON_TYPE_PAIRS:
        return True
    # Broader families
    if dt in {"Expense", "Cost of Goods Sold", "Other Expense"} and ct in {
        "Bank",
        "Credit Card",
        "Accounts payable (A/P)",
    }:
        return True
    if dt in {"Bank", "Other Current Assets", "Accounts receivable (A/R)"} and ct in {
        "Income",
        "Other Income",
    }:
        return True
    return False


def _is_reclass_suspicious(debit_type: str, credit_type: str) -> bool:
    dt, ct = _normalize_type(debit_type), _normalize_type(credit_type)
    if dt == ct and dt in RECLASS_TYPES:
        return True
    return False


def verify_transaction(logic_map: LogicMap, txn: Transaction) -> VerifyResult:
    reasons: list[str] = []
    findings: list[EdgeFinding] = []

    # Axiom: line weights are stored positive; direction lives in `side`, never
    # in the sign. A negative line can still balance, and would otherwise reach
    # the rewrite and produce a negative edge weight.
    nonpositive = [ln for ln in txn.lines if ln.amount <= 0]
    if nonpositive:
        return VerifyResult(
            txn_id=txn.txn_id,
            verdict="fail",
            reasons=[
                "non-positive line weight: "
                + ", ".join(f"{ln.account_id} {ln.side} {ln.amount}" for ln in nonpositive)
            ],
            findings=[],
        )

    if abs(txn.debit_total() - txn.credit_total()) > BALANCE_TOLERANCE:
        return VerifyResult(
            txn_id=txn.txn_id,
            verdict="fail",
            reasons=[
                f"unbalanced: debits={txn.debit_total():.2f} credits={txn.credit_total():.2f}"
            ],
            findings=[],
        )

    try:
        pairs = rewrite_transaction(txn)
    except ValueError as exc:
        return VerifyResult(
            txn_id=txn.txn_id,
            verdict="fail",
            reasons=[str(exc)],
            findings=[],
        )

    rank_index = logic_map.edge_rank_index()
    n_edges = max(len(logic_map.scored), 1)
    rare_rank_cutoff = max(1, int(n_edges * RARE_EDGE_RANK_FRAC))

    supports = 0
    warns = 0
    fails = 0

    single_pair = len(txn.debit_lines()) == 1 and len(txn.credit_lines()) == 1

    for key, weight in pairs:
        scored = rank_index.get(key)
        debit_type = logic_map.account_type(key.debit_account_id)
        credit_type = logic_map.account_type(key.credit_account_id)
        seen = scored is not None
        note = ""

        if key.is_self_loop:
            # Decided before the type-pair table, which cannot reason about this:
            # ("Bank","Bank") is listed as a common pair meaning a transfer
            # between two *different* bank accounts.
            if single_pair:
                # The whole posting is one account against itself — it moves
                # nothing, whatever the account type.
                note = "self-transfer: same account on both sides"
                fails += 1
                reasons.append(
                    f"posting moves no value: {key.debit_account_id} debited and "
                    f"credited against itself"
                )
            else:
                # An artifact of rewriting a journal that touches this account on
                # both sides. Not a posting the recorder made, so it gets no vote.
                note = "self-loop rewrite artifact (not a posting)"
            findings.append(
                EdgeFinding(
                    key=key,
                    weight=weight,
                    seen=seen,
                    rank=scored.rank if scored else None,
                    norm=scored.norm if scored else None,
                    share_w=scored.share_w if scored else None,
                    debit_type=debit_type,
                    credit_type=credit_type,
                    note=note,
                )
            )
            continue

        if seen and scored is not None:
            if scored.rank <= max(1, n_edges // 4):
                note = "known strong edge"
                supports += 1
            elif scored.rank >= rare_rank_cutoff:
                note = "known rare edge"
                warns += 1
                reasons.append(
                    f"rare historical edge {key.label()} (rank {scored.rank}/{n_edges})"
                )
            else:
                note = "known edge"
                supports += 1
        else:
            if _is_reclass_suspicious(debit_type, credit_type):
                note = "unseen reclass-suspicious type pair"
                fails += 1
                reasons.append(
                    f"unseen reclass-like pair {key.label()} ({debit_type}→{credit_type})"
                )
            elif _is_common_type_pair(debit_type, credit_type):
                note = "unseen but common type pair"
                warns += 1
                reasons.append(
                    f"unseen edge {key.label()} but common types ({debit_type}→{credit_type})"
                )
            else:
                note = "unseen uncommon type pair"
                fails += 1
                reasons.append(
                    f"unseen uncommon edge {key.label()} ({debit_type}→{credit_type})"
                )

        findings.append(
            EdgeFinding(
                key=key,
                weight=weight,
                seen=seen,
                rank=scored.rank if scored else None,
                norm=scored.norm if scored else None,
                share_w=scored.share_w if scored else None,
                debit_type=debit_type,
                credit_type=credit_type,
                note=note,
            )
        )

    if fails:
        verdict = "fail"
    elif warns:
        verdict = "warn"
    else:
        verdict = "pass"
        if not reasons:
            reasons.append("all edges supported by map or strong history")

    return VerifyResult(
        txn_id=txn.txn_id,
        verdict=verdict,
        reasons=reasons,
        findings=findings,
    )


def verify_transactions(
    logic_map: LogicMap,
    txns: list[Transaction],
    *,
    expected: dict[str, str] | None = None,
) -> list[VerifyResult]:
    results = [verify_transaction(logic_map, txn) for txn in txns]
    if expected:
        for r in results:
            r.expected_verdict = expected.get(r.txn_id)
    return results
