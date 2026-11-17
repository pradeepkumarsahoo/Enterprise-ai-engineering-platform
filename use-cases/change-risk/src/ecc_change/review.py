# Author: Pradeep Sahoo
"""Use case 4 runs: assess changes, backtest on past changes, gate status.

assess   -> factors and score (code), conditions (model, validated), Markdown + HTML report per
            change, results.json (keyed by change, so earlier assessments and approvals are kept)
backtest -> every past change scored as of its start, compared with what followed it
status   -> gate state of every assessed change
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from ecc_core.audit import AuditLog, new_correlation_id

from .drafting import validate_conditions
from .factors import RULES_VERSION, Rules, assess, is_upcoming
from .gate import RELEASE_ROLES, required_approvers, status
from .html import report_html
from .sources import ChangeInputs

AGENT = "agent:change-risk-assessor"
FAILED_CLOSE_CODES = ("Unsuccessful", "Backed out", "Unsuccessful - backed out")


def _results(workdir: Path) -> dict:
    path = Path(workdir) / "results.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"assessments": {}}


def assessed(workdir: Path, number: str) -> dict:
    a = _results(workdir)["assessments"].get(number)
    if a is None:
        raise ValueError(f"{number} has not been assessed; run `ecc change assess {number}` first")
    return a


def assess_changes(inp: ChangeInputs, numbers: list[str], r: Rules, drafter, workdir: Path) -> dict:
    workdir = Path(workdir)
    (workdir / "reports").mkdir(parents=True, exist_ok=True)
    audit = AuditLog(workdir / "audit.jsonl")
    cid = new_correlation_id()
    audit.record(AGENT, "change.assess.started", ",".join(numbers), cid, provider=drafter.name)
    for tool in ("servicenow.change_request.read", "servicenow.incident.read", "changesets.read", "catalogue.read",
                 "calendar.read", "runbooks.read"):
        audit.record(AGENT, "tool.call", tool, cid)
    results = _results(workdir)
    out = {}
    for number in numbers:
        if number not in inp.changes:
            raise ValueError(f"{number} is not a change request in ServiceNow")
        a = assess(inp, number, r)
        raw = drafter.draft_conditions(a)
        summary, conditions, rejected = validate_conditions(raw, a)
        for x in rejected:
            audit.record("policy-engine", "change.condition.rejected", f"{number}/{x['item']}", cid, outcome="rejected",
                         reason=x["reason"])
        d = {**asdict(a), "summary": summary, "conditions": [asdict(c) for c in conditions],
             "rejected_conditions": rejected, "required_approvers": required_approvers(a.band),
             "provider": drafter.name}
        results["assessments"][number] = d
        out[number] = d
        audit.record(AGENT, "change.assessed", number, cid, score=a.score, band=a.band, assessment_id=a.assessment_id,
                     factors=[f.key for f in a.factors], approved=False)
    results.update({"as_of": r.as_of, "rules_version": next(iter(out.values()))["rules_version"] if out else None})
    (workdir / "results.json").write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    for number in out:
        render_reports(workdir, number)
    return out


def render_reports(workdir: Path, number: str) -> None:
    """(Re)write a change's Markdown and HTML report with its current gate state."""
    d = assessed(workdir, number)
    gate = status(d, workdir)
    (Path(workdir) / "reports").mkdir(parents=True, exist_ok=True)
    (Path(workdir) / "reports" / f"{number}.md").write_text(report_md(d, gate), encoding="utf-8")
    (Path(workdir) / "reports" / f"{number}.html").write_text(report_html(d, gate), encoding="utf-8")


def upcoming(inp: ChangeInputs, r: Rules) -> list[str]:
    return sorted(n for n in inp.changesets if is_upcoming(inp, n, r))


# ------------------------------------------------------------------ Markdown report

def report_md(d: dict, gate: dict) -> str:
    ev = {e["id"]: e["summary"] for e in d["evidence"]}
    L = [f"# Change risk · {d['change']} · {d['service']}", "",
         f"> Pre-deploy assessment. The score comes from rules in code; the model only explains it and drafts "
         f"release conditions. Approve or reject with `ecc change approve {d['change']}`.", "",
         f"**{d['title']}** · planned {d['planned_start']} UTC · requested by {d['requested_by']}", "",
         f"## Score: {d['score']} / 10 · {d['band']}", "",
         f"Release gate: **{gate['state']}** · needs {gate['required_approvers']} approver(s) from "
         f"{', '.join(RELEASE_ROLES)}; the requester cannot approve. Assessment `{d['assessment_id']}`.", "",
         "| Factor | Signal | Weight | Evidence |", "|---|---|---|---|"]
    L += [f"| {f['title']} | {f['signal']} | +{f['weight']:g} | {', '.join(f['evidence'])} |" for f in d["factors"]] \
        or ["| — | no factor fired | 0 | |"]
    L += ["", f"Score = sum of weights, capped at 10 · {d['rules_version']} · weights set in the product configuration.", ""]
    if d["summary"]:
        L += ["## Summary", "", d["summary"], ""]
    L += ["## Similar past changes", ""]
    L += [f"- **{s['change']}** on {s['ci']} → **{s['incident']}** (same {', '.join(s['matched_on'])})"
          for s in d["similar"]] or ["- none"]
    L += ["", "## Suggested release conditions", ""]
    L += [f"- {c['text']} ({c['factor']}; {', '.join(c['evidence'])})" for c in d["conditions"]] or ["- none"]
    if d["rejected_conditions"]:
        L += ["", "Conditions rejected by validation:", ""] + [f"- {x['item']}: {x['reason']}" for x in d["rejected_conditions"]]
    L += ["", "## Could not establish", ""] + ([f"- {u}" for u in d["could_not_establish"]] or ["- nothing"])
    cited = sorted(ev, key=lambda x: int(x[1:]))
    L += ["", "## Evidence", ""] + [f"- **{i}** {ev[i]}" for i in cited]
    L += ["", "_Generated by Engineering Command Centre · use case 4 · Author: Pradeep Sahoo_", ""]
    return "\n".join(L)


# ------------------------------------------------------------------ backtest

def backtest(inp: ChangeInputs, r: Rules, gates: dict, labels: dict | None = None) -> dict:
    """Score every past change as of its start; compare the band with what followed it."""
    cases = []
    for number in sorted(inp.changesets, key=inp.start):
        if is_upcoming(inp, number, r):
            continue
        a = assess(inp, number, r)                                   # as of the change's start
        inc = inp.linked_incident(number, r.outcome_window_hours)    # the outcome: scoring only
        failed = inp.changes[number].get("close_code") in FAILED_CLOSE_CODES
        caused = bool(inc) or failed
        cases.append({"change": number, "service": a.service, "start": a.planned_start, "score": a.score,
                      "band": a.band, "flagged": a.band != "low", "caused_incident": caused,
                      "incident": inc["number"] if inc else None, "close_code": inp.changes[number].get("close_code"),
                      "factors": [f.key for f in a.factors]})
    caused = [c for c in cases if c["caused_incident"]]
    flagged = [c for c in cases if c["flagged"]]
    recall = sum(c["flagged"] for c in caused) / len(caused) if caused else 1.0
    false_alarm = sum(not c["caused_incident"] for c in flagged) / len(flagged) if flagged else 0.0
    m = {"changes": len(cases), "caused_incident": len(caused), "flagged": len(flagged), "recall": round(recall, 3),
         "false_alarm_rate": round(false_alarm, 3),
         "missed": [c["change"] for c in caused if not c["flagged"]],
         "false_alarms": [c["change"] for c in flagged if not c["caused_incident"]]}
    if labels:
        want = labels.get("bands", {})
        m["band_match"] = all(want.get(c["change"]) == c["band"] for c in cases)
        m["outcome_match"] = {c["change"]: c["incident"] for c in cases if c["incident"]} == labels.get("caused_incident")
    checks = {"recall": m["recall"] >= gates["recall_min"], "false_alarm_rate": m["false_alarm_rate"] <= gates["false_alarm_max"]}
    ok = all(checks.values())
    tick = lambda b: "✅" if b else "❌"
    md = [f"# Change risk backtest · {RULES_VERSION}", "",
          f"{m['changes']} past changes scored as of their start, compared with what followed. "
          f"**{len(caused) - len(m['missed'])} of {len(caused)}** changes that were followed by an incident (or closed "
          f"unsuccessful) were scored medium or high. Gates: **{'PASS' if ok else 'FAIL'}**.", "",
          "| Measure | Result | Gate | |", "|---|---|---|---|",
          f"| Incident-causing changes scored medium or high | {m['recall']:.0%} | ≥ {gates['recall_min']:.0%} | {tick(checks['recall'])} |",
          f"| Medium or high scores with no incident after them | {m['false_alarm_rate']:.0%} | ≤ {gates['false_alarm_max']:.0%} | {tick(checks['false_alarm_rate'])} |",
          "", "| Change | Service | Start (UTC) | Score | Band | What followed | Factors |", "|---|---|---|---|---|---|---|"]
    for c in cases:
        followed = c["incident"] or (f"closed {c['close_code'].lower()}" if c["caused_incident"] else "nothing")
        mark = ("✅" if c["flagged"] else "❌ missed") if c["caused_incident"] else ("⚠️ false alarm" if c["flagged"] else "✅")
        md.append(f"| {c['change']} | {c['service']} | {c['start']} | {c['score']} | {c['band']} | {followed} {mark} | "
                  f"{', '.join(c['factors']) or '—'} |")
    if m["missed"]:
        md += ["", f"Missed: {', '.join(m['missed'])}. Nothing in the change's metadata (diff kinds, settings, migrations, "
                   "contracts, coverage, window, history) signalled the risk; a memory leak, for example, needs a load "
                   "test result or runtime data, which no source here provides."]
    if m["false_alarms"]:
        md += ["", f"False alarms: {', '.join(m['false_alarms'])}. Scored medium or high, and nothing followed."]
    md += ["", f"_Gate note: {gates.get('note', '')}_", "",
           "_Synthetic history: the changes and incidents were written alongside the rules, so this proves the "
           "backtest works, not that the weights are right. Re-run on real ServiceNow history before relying on it._",
           "", "_Generated by Engineering Command Centre · use case 4 · Author: Pradeep Sahoo_", ""]
    return {"metrics": m, "cases": cases, "gate_results": checks, "passed": ok, "report_md": "\n".join(md)}
