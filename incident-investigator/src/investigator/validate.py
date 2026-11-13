# Author: Pradeep Sahoo
"""Check the provider's output against the evidence and the policy.

Anything the model claims that cannot be tied to a real evidence record is
removed and counted as an unsupported claim. Risk and approval on next steps
are always set by policy, never by the model.
"""
from __future__ import annotations

from .models import ACTION_TYPES, CAUSE_CATEGORIES, Evidence, Hypothesis, NextStep
from .policy import MAX_CONFIDENCE, classify


def _known(ids, known: set[str], where: str, problems: list[str]) -> list[str]:
    good = []
    for i in ids or []:
        if i in known:
            if i not in good:
                good.append(i)
        else:
            problems.append(f"{where} cited unknown evidence '{i}'")
    return good


def validate(raw: dict, evidence: list[Evidence]) -> tuple[list[Hypothesis], list[NextStep], list[str], list[str], str]:
    """Returns (hypotheses, next_steps, could_not_establish, unsupported_claims, summary)."""
    known = {e.id for e in evidence}
    injected = {e.id for e in evidence if "possible_prompt_injection" in e.flags}
    problems: list[str] = []

    hyps: list[Hypothesis] = []
    for n, h in enumerate(raw.get("hypotheses", []), start=1):
        where = f"Hypothesis {n} ({h.get('title', '?')})"
        support = _known(h.get("supporting_evidence"), known, where, problems)
        contra = _known(h.get("contradicting_evidence"), known, where, problems)
        if support and set(support) <= injected:
            problems.append(f"{where} rested only on instruction-like text; removed")
            continue
        if not support:
            problems.append(f"{where} had no valid supporting evidence; removed")
            continue
        cat = h.get("cause_category")
        if cat not in CAUSE_CATEGORIES:
            problems.append(f"{where} used unknown category '{cat}'; set to 'unknown'")
            cat = "unknown"
        try:
            conf = float(h.get("confidence", 0))
        except (TypeError, ValueError):
            conf = 0.0
        hyps.append(Hypothesis(h.get("title", "").strip() or cat, cat, round(min(max(conf, 0.0), MAX_CONFIDENCE), 2),
                               support, contra, h.get("explanation", "")))
    hyps.sort(key=lambda h: -h.confidence)

    steps: list[NextStep] = []
    for n, s in enumerate(raw.get("next_steps", []), start=1):
        action = s.get("action_type")
        if action not in ACTION_TYPES:
            problems.append(f"Next step {n} used unknown action type '{action}'; treated as high risk")
        ev = _known(s.get("evidence"), known, f"Next step {n}", problems)
        risk, approval = classify(action)
        steps.append(NextStep(s.get("description", ""), action if action in ACTION_TYPES else "escalate",
                              ev, risk, approval))
    # read-only diagnostics first, then by risk
    order = {"low": 0, "medium": 1, "high": 2}
    steps.sort(key=lambda s: (s.requires_approval, order[s.risk]))

    could_not = [c for c in raw.get("could_not_establish", []) if isinstance(c, str) and c.strip()]
    return hyps, steps, could_not, problems, str(raw.get("summary", "")).strip()
