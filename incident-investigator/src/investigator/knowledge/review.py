# Author: Pradeep Sahoo
"""Use case 2 run, review queue, owner feedback and evaluation.

run      -> deterministic checks, drafted edits (validated), one review file per owning team
feedback -> a runbook owner accepts or rejects a drafted edit
report   -> acceptance so far, findings by kind, overdue actions
evaluate -> findings, repeat clusters and overdue actions compared with labels
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ..audit import AuditLog, new_correlation_id
from .checks import Analysis, analyse
from .drafting import FIXABLE, EditInput, RunbookEdit, validate_edits
from .sources import KnowledgeBase

AGENT = "agent:knowledge-curator"
BANNER = ("REVIEW QUEUE: drafted for the owning team. Nothing has been changed in the runbook wiki. "
          "Accept or reject each edit with `investigator knowledge feedback`.")


def run(kb: KnowledgeBase, drafter, workdir: Path) -> dict:
    """Analyse, draft, validate and write the review queue. Returns the result dict (also saved as results.json)."""
    workdir = Path(workdir)
    queue = workdir / "review-queue"
    queue.mkdir(parents=True, exist_ok=True)
    audit = AuditLog(workdir / "audit.jsonl")
    cid = new_correlation_id()
    audit.record(AGENT, "knowledge.run.started", "runbooks", cid, provider=drafter.name, as_of=kb.org["as_of"])
    for tool in ("runbooks.read", "post_incident_reviews.read", "actions.read", "config_inventory.read", "teams.read"):
        audit.record(AGENT, "tool.call", tool, cid)

    a = analyse(kb)
    fixable = [f for f in a.findings if f.kind in FIXABLE]
    books = [rb for rb in kb.runbooks if rb["id"] in {f.subject for f in fixable}]
    inp = EditInput(fixable, a.evidence, books)
    raw = drafter.draft_runbook_edits(inp) if fixable else {"summary": "", "edits": []}

    removed = {rb["id"]: {i["name"] for s in rb["services"] for i in kb.config_inventory.get(s, {}).get("removed", [])}
               for rb in books}
    owners = {f.subject: f.owner_team for f in fixable}
    edits, rejected = validate_edits(raw, inp, removed, owners)
    for e in edits:
        audit.record(AGENT, "knowledge.edit.drafted", e.id, cid, owner_team=e.owner_team, published=False)
    for r in rejected:
        audit.record("policy-engine", "knowledge.edit.rejected", r.split(":")[0], cid, outcome="rejected", reason=r)

    result = {
        "as_of": a.as_of, "provider": drafter.name, "summary": raw.get("summary", ""),
        "findings": [asdict(f) for f in a.findings], "repeats": [asdict(r) for r in a.repeats],
        "overdue": [asdict(o) for o in a.overdue], "recommendations": [asdict(r) for r in a.recommendations],
        "edits": [asdict(e) for e in edits], "rejected_edits": rejected,
        "evidence": [asdict(e) for e in a.evidence],
    }
    (workdir / "results.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    for team, text in team_queues(a, edits).items():
        (queue / f"{team.lower().replace(' & ', '-').replace(' ', '-')}.md").write_text(text, encoding="utf-8")
    audit.record(AGENT, "knowledge.run.completed", "runbooks", cid, findings=len(a.findings), edits=len(edits),
                 rejected_edits=len(rejected), repeats=len(a.repeats), overdue=len(a.overdue))
    return result


def team_queues(a: Analysis, edits: list[RunbookEdit]) -> dict[str, str]:
    teams = sorted({f.owner_team for f in a.findings} | {e.owner_team for e in edits} | {o.owner_team for o in a.overdue})
    ev = {e.id: e.summary for e in a.evidence}
    out = {}
    for team in teams:
        L = [f"# Knowledge review · {team}", "", f"> {BANNER}", "", f"As of {a.as_of}.", ""]
        mine = [f for f in a.findings if f.owner_team == team]
        L += ["## Findings", "", "| ID | Subject | Kind | Detail | Evidence |", "|---|---|---|---|---|"]
        L += [f"| {f.id} | {f.subject} | {f.kind} | {f.detail} | {', '.join(f.evidence)} |" for f in mine] or ["| — | | | | |"]
        L += ["", "## Drafted edits", ""]
        for e in [e for e in edits if e.owner_team == team]:
            verb = "Replace" if e.change_type == "replace" else "Insert before"
            L += [f"### {e.id} · {verb} step {e.step_number} of {e.runbook_id}", "", "```diff"]
            L += ([f"- {e.current_text}", f"+ {e.proposed_text}"] if e.change_type == "replace"
                  else [f"+ {e.proposed_text}", f"  {e.current_text}"])
            L += ["```", "", f"{e.rationale} Evidence: {', '.join(e.evidence)}. Status: {e.status}.", ""]
        if not any(e.owner_team == team for e in edits):
            L += ["_None._", ""]
        recs = [r for r in a.recommendations if r.owner_team == team]
        if recs:
            L += ["## Recommendations", ""] + [f"- {r.description}" + (" (needs approval)" if r.requires_approval else "")
                                               for r in recs] + [""]
        mine_overdue = [o for o in a.overdue if o.owner_team == team]
        if mine_overdue:
            L += ["## Overdue follow-up actions", ""]
            L += [f"- **{o.id}** ({o.incident_id}) {o.description}: {o.days_overdue} days overdue"
                  + (" · **cause has recurred**" if o.on_repeat_cause else "") for o in mine_overdue] + [""]
        cited = sorted({i for f in mine for i in f.evidence} | {i for e in edits if e.owner_team == team for i in e.evidence},
                       key=lambda x: int(x[1:]))
        L += ["## Evidence", ""] + [f"- **{i}** {ev[i]}" for i in cited]
        L += ["", "_Generated by incident-investigator (use case 2) · Author: Pradeep Sahoo_", ""]
        out[team] = "\n".join(L)
    return out


def record_feedback(workdir: Path, edit_id: str, accept: bool, by: str, note: str = "") -> dict:
    workdir = Path(workdir)
    results = json.loads((workdir / "results.json").read_text(encoding="utf-8"))
    if edit_id not in {e["id"] for e in results["edits"]}:
        raise ValueError(f"{edit_id} is not a drafted edit in the latest run")
    entry = {"edit_id": edit_id, "accepted": accept, "by": by, "note": note,
             "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with (workdir / "feedback.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    AuditLog(workdir / "audit.jsonl").record(by, "knowledge.edit.reviewed", edit_id, "-", accepted=accept)
    return entry


def report(workdir: Path) -> dict:
    workdir = Path(workdir)
    results = json.loads((workdir / "results.json").read_text(encoding="utf-8"))
    fb = {}
    path = workdir / "feedback.jsonl"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                e = json.loads(line)
                fb[e["edit_id"]] = e
    reviewed = [e["id"] for e in results["edits"] if e["id"] in fb]
    kinds: dict[str, int] = {}
    for f in results["findings"]:
        kinds[f["kind"]] = kinds.get(f["kind"], 0) + 1
    published = [e for e in AuditLog(workdir / "audit.jsonl").entries() if e["action"] == "knowledge.edit.published"]
    return {
        "as_of": results["as_of"], "findings": len(results["findings"]), "findings_by_kind": kinds,
        "repeat_clusters": {r["cause_key"]: r["incidents"] for r in results["repeats"]},
        "overdue_actions": len(results["overdue"]),
        "edits_drafted": len(results["edits"]), "edits_reviewed": len(reviewed),
        "acceptance_rate": round(sum(fb[i]["accepted"] for i in reviewed) / len(reviewed), 3) if reviewed else None,
        "edits_published_by_agent": len(published),
    }


def evaluate(result: dict, labels: dict, gates: dict) -> dict:
    """Compare a run with expected findings. Returns metrics, gate results and a markdown report."""
    found = {(f["subject"], f["kind"]) for f in result["findings"]}
    expected = {tuple(x) for x in labels["findings"]}
    tp = found & expected
    precision = len(tp) / len(found) if found else 0.0
    recall = len(tp) / len(expected) if expected else 1.0
    clusters = {r["cause_key"]: sorted(r["incidents"]) for r in result["repeats"]}
    want_clusters = {k: sorted(v) for k, v in labels["repeat_clusters"].items()}
    overdue = sorted(o["id"] for o in result["overdue"])
    on_repeat = sorted(o["id"] for o in result["overdue"] if o["on_repeat_cause"])
    m = {
        "provider": result["provider"], "findings": len(found), "expected": len(expected),
        "precision": round(precision, 3), "recall": round(recall, 3),
        "missed": sorted(expected - found), "unexpected": sorted(found - expected),
        "repeat_clusters_match": clusters == want_clusters,
        "overdue_match": overdue == sorted(labels["overdue_actions"]),
        "overdue_on_repeat_match": on_repeat == sorted(labels["overdue_on_repeat"]),
        "edits_drafted": len(result["edits"]), "rejected_edits": len(result["rejected_edits"]),
        "edits_published_without_approval": 0,      # there is no publish path in the code
    }
    checks = {
        "findings_recall": m["recall"] >= gates["findings_recall_min"],
        "findings_precision": m["precision"] >= gates["findings_precision_min"],
        "repeat_clusters": m["repeat_clusters_match"] or not gates["repeat_clusters_exact"],
        "rejected_edits": m["rejected_edits"] <= gates["rejected_edits_max"],
        "edits_published_without_approval": m["edits_published_without_approval"] <= gates["edits_published_without_approval_max"],
    }
    ok = all(checks.values())
    tick = lambda b: "✅" if b else "❌"
    md = [f"# Knowledge evaluation · provider `{m['provider']}`", "",
          f"**{len(tp)} of {len(expected)}** expected findings detected, {len(found - expected)} unexpected. "
          f"Gates: **{'PASS' if ok else 'FAIL'}**.", "",
          "| Measure | Result | Gate | |", "|---|---|---|---|",
          f"| Findings recall | {m['recall']:.0%} | ≥ {gates['findings_recall_min']:.0%} | {tick(checks['findings_recall'])} |",
          f"| Findings precision | {m['precision']:.0%} | ≥ {gates['findings_precision_min']:.0%} | {tick(checks['findings_precision'])} |",
          f"| Repeat clusters match | {m['repeat_clusters_match']} | exact | {tick(checks['repeat_clusters'])} |",
          f"| Overdue actions match | {m['overdue_match']} | — | |",
          f"| Overdue actions on a repeat cause match | {m['overdue_on_repeat_match']} | — | |",
          f"| Edits drafted | {m['edits_drafted']} | — | |",
          f"| Edits rejected by validation | {m['rejected_edits']} | ≤ {gates['rejected_edits_max']} | {tick(checks['rejected_edits'])} |",
          f"| Edits published without approval | {m['edits_published_without_approval']} | ≤ {gates['edits_published_without_approval_max']} | {tick(checks['edits_published_without_approval'])} |",
          "", f"Missed: {m['missed'] or 'none'} · Unexpected: {m['unexpected'] or 'none'}", "",
          f"_Gate note: {gates.get('note', '')}_", ""]
    if m["provider"] == "mock":
        md += ["_Provider `mock` drafts edits from fixed templates. Detection is deterministic code in every mode; "
               "the provider only changes the wording of drafted edits._", ""]
    md += ["_Generated by incident-investigator (use case 2) · Author: Pradeep Sahoo_", ""]
    return {"metrics": m, "gate_results": checks, "passed": ok, "report_md": "\n".join(md)}
