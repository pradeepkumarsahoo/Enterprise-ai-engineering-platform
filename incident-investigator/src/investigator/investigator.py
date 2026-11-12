"""Orchestrates one investigation: read -> evidence -> detectors -> model -> validate -> audit."""
from __future__ import annotations

import time
from pathlib import Path

from . import detectors, evidence
from .adapters import FixtureRunbooks, FixtureSource
from .audit import AuditLog, new_correlation_id
from .models import Investigation
from .policy import MODES
from .providers import Provider, ProviderError, ProviderInput
from .validate import validate

AGENT = "agent:incident-investigator"


def investigate(incident_path: Path, provider: Provider, mode: str, audit: AuditLog,
                runbooks_path: Path | None = None) -> Investigation:
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode}")
    cid = new_correlation_id()
    started = time.perf_counter()
    source = FixtureSource(incident_path, on_call=lambda tool: audit.record(AGENT, "tool.call", tool, cid, mode=mode))
    inc_id = source._data["incident"]["id"]
    audit.record(AGENT, "investigation.started", inc_id, cid, mode=mode, provider=provider.name)

    runbooks = FixtureRunbooks(runbooks_path) if runbooks_path else None
    inc, ev, facts = evidence.build(source, runbooks)
    for e in ev:
        if "possible_prompt_injection" in e.flags:
            audit.record("policy-engine", "untrusted_input.flagged", f"{inc_id}/{e.id}", cid,
                         outcome="treated_as_data")
        if "secret_redacted" in e.flags:
            audit.record("policy-engine", "secret.redacted", f"{inc_id}/{e.id}", cid)
    candidates = detectors.run_all(facts)

    try:
        raw = provider.investigate(ProviderInput(inc, ev, candidates, facts.missing_sources))
    except ProviderError as exc:
        audit.record(AGENT, "investigation.failed", inc_id, cid, outcome="error", error=str(exc))
        raise
    hyps, steps, could_not, unsupported, summary = validate(raw, ev)
    duration = round(time.perf_counter() - started, 3)

    result = Investigation(inc_id, inc["service"], mode, provider.name, summary, hyps, could_not, steps,
                           ev, candidates, unsupported, duration, cid)
    audit.record(AGENT, "investigation.completed", inc_id, cid, mode=mode, provider=provider.name,
                 hypotheses=len(hyps), unsupported_claims=len(unsupported),
                 approval_required_steps=sum(s.requires_approval for s in steps), duration_s=duration)
    return result
