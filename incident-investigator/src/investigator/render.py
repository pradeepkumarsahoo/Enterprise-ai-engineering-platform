"""Markdown rendering of one investigation (used by `investigate` and the shadow review queue)."""
from __future__ import annotations

from .models import Investigation
from .policy import LEAD_CONFIDENCE_MIN


def investigation_md(inv: Investigation, banner: str = "") -> str:
    lines = [f"# {inv.incident_id} · {inv.service}", ""]
    if banner:
        lines += [f"> {banner}", ""]
    lines += [f"**Summary:** {inv.summary or '—'}", "",
              f"Mode `{inv.mode}` · provider `{inv.provider}` · {inv.duration_s:.2f} s · correlation `{inv.correlation_id}`", ""]
    lines += ["## Hypotheses", ""]
    if not inv.hypotheses:
        lines.append("_No hypothesis is supported by the evidence._")
    for i, h in enumerate(inv.hypotheses, start=1):
        tag = " (lead)" if i == 1 and h.confidence >= LEAD_CONFIDENCE_MIN else ""
        lines.append(f"{i}. **{h.title}**{tag} · `{h.cause_category}` · confidence {h.confidence:.2f}")
        lines.append(f"   - Supports: {', '.join(h.supporting_evidence)}"
                     + (f" · Contradicts: {', '.join(h.contradicting_evidence)}" if h.contradicting_evidence else ""))
        if h.explanation:
            lines.append(f"   - {h.explanation}")
    lines += ["", "## Could not establish", ""]
    lines += [f"- {c}" for c in inv.could_not_establish] or ["- —"]
    lines += ["", "## Recommended next steps", "", "| Step | Type | Risk | Needs approval | Evidence |", "|---|---|---|---|---|"]
    for s in inv.next_steps:
        lines.append(f"| {s.description} | {s.action_type} | {s.risk} | {'yes' if s.requires_approval else 'no'} | {', '.join(s.evidence) or '—'} |")
    lines += ["", "_Recommendations only. This system cannot execute any of them._", "", "## Evidence", ""]
    for e in inv.evidence:
        flag = f" ⚠ {', '.join(e.flags)}" if e.flags else ""
        lines.append(f"- **{e.id}** · {e.kind} · {e.source}: {e.summary}{flag}")
    if inv.unsupported_claims:
        lines += ["", "## Removed by validation", ""] + [f"- {u}" for u in inv.unsupported_claims]
    return "\n".join(lines) + "\n"
