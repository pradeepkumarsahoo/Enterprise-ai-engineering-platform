"""Replay: run the investigator on past incidents and score it against known root causes.

Labels live in a separate file the investigator never reads. Scoring compares
the investigation's lead hypothesis with the label and checks the pilot gates.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import median

from .audit import AuditLog
from .investigator import investigate
from .policy import LEAD_CONFIDENCE_MIN
from .providers import Provider
from .render import investigation_md


@dataclass
class CaseResult:
    incident_id: str
    expected: str
    predicted: str
    lead_confidence: float
    correct: bool
    false_confident_lead: bool
    lead_evidence: int
    unsupported_claims: int
    injection_lines_flagged: int
    secrets_redacted: int
    agent_seconds: float
    human_minutes: int | None


def predicted_cause(inv) -> tuple[str, float]:
    lead = inv.lead()
    if lead and lead.confidence >= LEAD_CONFIDENCE_MIN:
        return lead.cause_category, lead.confidence
    return "unknown", (lead.confidence if lead else 0.0)


def run(incidents_dir: Path, labels_path: Path, runbooks_path: Path, provider: Provider,
        out_dir: Path, gates: dict) -> dict:
    labels = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "incidents").mkdir(exist_ok=True)
    audit = AuditLog(out_dir / "audit.jsonl")

    cases: list[CaseResult] = []
    for path in sorted(Path(incidents_dir).glob("*.json")):
        inv = investigate(path, provider, "replay", audit, runbooks_path)
        label = labels.get(inv.incident_id)
        if label is None:
            continue
        pred, conf = predicted_cause(inv)
        expected = label["cause_category"]
        lead = inv.lead()
        cases.append(CaseResult(
            inv.incident_id, expected, pred, round(conf, 2), pred == expected,
            pred != "unknown" and pred != expected,
            len(lead.supporting_evidence) if lead and pred != "unknown" else 0,
            len(inv.unsupported_claims),
            sum("possible_prompt_injection" in e.flags for e in inv.evidence),
            sum("secret_redacted" in e.flags for e in inv.evidence),
            inv.duration_s, label.get("human_first_hypothesis_min"),
        ))
        (out_dir / "incidents" / f"{inv.incident_id}.md").write_text(
            investigation_md(inv, f"Replay of a past incident. Known cause: `{expected}` — {label['summary']}"),
            encoding="utf-8")

    executed = [e for e in audit.entries() if e["action"].startswith("action.execute")]
    n = len(cases)
    human = [c.human_minutes for c in cases if c.human_minutes is not None]
    metrics = {
        "provider": provider.name,
        "incidents": n,
        "lead_accuracy": round(sum(c.correct for c in cases) / n, 3) if n else 0.0,
        "correct": sum(c.correct for c in cases),
        "false_confident_leads": sum(c.false_confident_lead for c in cases),
        "unsupported_claims": sum(c.unsupported_claims for c in cases),
        "injection_lines_flagged": sum(c.injection_lines_flagged for c in cases),
        "secrets_redacted": sum(c.secrets_redacted for c in cases),
        "actions_executed": len(executed),
        "median_agent_seconds": round(median(c.agent_seconds for c in cases), 3) if n else None,
        "median_human_minutes_to_first_hypothesis": median(human) if human else None,
    }
    checks = {
        "lead_accuracy": metrics["lead_accuracy"] >= gates["lead_accuracy_min"],
        "false_confident_leads": metrics["false_confident_leads"] <= gates["false_confident_leads_max"],
        "unsupported_claims": metrics["unsupported_claims"] <= gates["unsupported_claims_max"],
        "actions_executed": metrics["actions_executed"] <= gates["actions_executed_max"],
    }
    result = {"metrics": metrics, "gates": gates, "gate_results": checks, "passed": all(checks.values()),
              "cases": [asdict(c) for c in cases]}
    (out_dir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    (out_dir / "report.md").write_text(report_md(result), encoding="utf-8")
    return result


def report_md(result: dict) -> str:
    m, g, ok = result["metrics"], result["gates"], result["gate_results"]
    lines = [f"# Replay report · provider `{m['provider']}`", "",
             f"**{m['correct']} of {m['incidents']}** past incidents had the correct lead hypothesis "
             f"(or correctly reported “not established”). Gates: **{'PASS' if result['passed'] else 'FAIL'}**.", "",
             "| Measure | Result | Gate | |", "|---|---|---|---|",
             f"| Lead hypothesis accuracy | {m['lead_accuracy']:.0%} | ≥ {g['lead_accuracy_min']:.0%} | {'✅' if ok['lead_accuracy'] else '❌'} |",
             f"| Confident but wrong leads | {m['false_confident_leads']} | ≤ {g['false_confident_leads_max']} | {'✅' if ok['false_confident_leads'] else '❌'} |",
             f"| Unsupported claims removed by validation | {m['unsupported_claims']} | ≤ {g['unsupported_claims_max']} | {'✅' if ok['unsupported_claims'] else '❌'} |",
             f"| Actions executed | {m['actions_executed']} | ≤ {g['actions_executed_max']} | {'✅' if ok['actions_executed'] else '❌'} |",
             f"| Instruction-like log lines flagged | {m['injection_lines_flagged']} | — | |",
             f"| Secrets redacted before the model call | {m['secrets_redacted']} | — | |",
             f"| Median agent time | {m['median_agent_seconds']} s | — | |",
             f"| Median human time to first correct hypothesis | {m['median_human_minutes_to_first_hypothesis']} min | baseline | |",
             "", "| Incident | Known cause | Predicted | Confidence | Evidence cited | Human baseline |",
             "|---|---|---|---|---|---|"]
    for c in result["cases"]:
        mark = "✅" if c["correct"] else "❌"
        human = f"{c['human_minutes']} min" if c["human_minutes"] is not None else "not found"
        lines.append(f"| {c['incident_id']} | {c['expected']} | {mark} {c['predicted']} | {c['lead_confidence']:.2f} | "
                     f"{c['lead_evidence']} | {human} |")
    lines += ["", f"_Gate note: {g.get('note', '')}_", ""]
    if m["provider"] == "mock":
        lines += ["_Provider `mock` turns the rule-based detectors into answers with fixed templates. "
                  "This run measures the evidence pipeline and detectors, not a language model._", ""]
    return "\n".join(lines)
