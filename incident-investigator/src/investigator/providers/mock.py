# Author: Pradeep Sahoo
"""Deterministic mock provider.

Turns the detector candidates into the provider output format with fixed
templates. It needs no API key, costs nothing and gives the same answer every
run, so the rest of the pipeline (evidence, validation, policy, audit, replay
scoring, shadow mode) can be built and tested without a model.

It does not measure model quality. Replay results with this provider measure
the detectors and the pipeline; run replay with the Claude provider to
measure the model.
"""
from __future__ import annotations

from ..policy import LEAD_CONFIDENCE_MIN
from .base import ProviderInput

STEPS = {
    "config_change": [("read_only_diagnostic", "Compare the rendered configuration of the previous and current release"),
                      ("config_change", "Restore the changed setting through a reviewed config change"),
                      ("rollback", "Roll back to the previous release")],
    "slow_query": [("read_only_diagnostic", "Get the query plan for the slow statement and check for a missing index"),
                   ("rollback", "Roll back the release that introduced the query")],
    "traffic_spike": [("read_only_diagnostic", "Confirm the traffic source from access logs"),
                      ("scale", "Raise the autoscaler maximum within quota")],
    "dependency_failure": [("read_only_diagnostic", "Confirm the dependency's status and error rate by region"),
                           ("escalate", "Escalate to the dependency owner or provider")],
    "resource_leak": [("read_only_diagnostic", "Capture a heap profile from one affected pod"),
                      ("restart", "Rolling restart as a short-term mitigation")],
    "certificate_expiry": [("read_only_diagnostic", "Confirm which certificate expired and which services use it"),
                           ("config_change", "Rotate the certificate through the certificate pipeline")],
    "bad_feature_flag": [("read_only_diagnostic", "Confirm the errors are limited to the flagged code path"),
                         ("feature_flag_change", "Turn the flag off for the affected cohort")],
    "code_change": [("read_only_diagnostic", "Review the diff of the release deployed before onset"),
                    ("rollback", "Roll back to the previous release")],
}


class MockProvider:
    name = "mock"

    def investigate(self, inp: ProviderInput) -> dict:
        cands = [c for c in inp.candidates if c.supporting]
        ruled_down = [c for c in inp.candidates if not c.supporting]
        hypotheses = [{
            "title": c.title,
            "cause_category": c.cause_category,
            "confidence": round(c.score, 2),
            "supporting_evidence": c.supporting,
            "contradicting_evidence": c.contradicting,
            "explanation": f"{c.title}. Supported by {', '.join(c.supporting)}"
                           + (f"; contradicted by {', '.join(c.contradicting)}." if c.contradicting else "."),
        } for c in cands]

        could_not = []
        lead = cands[0] if cands and cands[0].score >= LEAD_CONFIDENCE_MIN else None
        if lead:
            could_not += lead.gaps
        else:
            could_not.append("No signal in the available evidence explains the change; the cause is not established")
        for c in ruled_down:
            could_not.append(f"Ruled down: {c.title.lower()} (contradicted by {', '.join(c.contradicting)})")
        could_not += inp.missing_sources

        steps = []
        runbook = [e.id for e in inp.evidence if e.kind == "runbook"][:1]
        if lead:
            for action, text in STEPS.get(lead.cause_category, []):
                steps.append({"description": text, "action_type": action, "evidence": lead.supporting[:3] + runbook})
        else:
            steps.append({"description": "Enable request tracing for this service so the next occurrence can be explained",
                          "action_type": "read_only_diagnostic", "evidence": []})
            steps.append({"description": "Ask the owning team whether anything changed outside the deploy pipeline",
                          "action_type": "escalate", "evidence": []})

        summary = (f"Lead hypothesis: {lead.title} (confidence {lead.score:.2f})." if lead
                   else "Cause not established from the available evidence.")
        flagged = [e.id for e in inp.evidence if "possible_prompt_injection" in e.flags]
        if flagged:
            summary += f" Instruction-like text in {', '.join(flagged)} was treated as data."
        return {"summary": summary, "hypotheses": hypotheses, "could_not_establish": could_not, "next_steps": steps}
