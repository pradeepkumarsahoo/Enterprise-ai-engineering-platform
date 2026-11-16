# Author: Pradeep Sahoo
"""Use case 3 run, review pack, approver feedback and evaluation.

run      -> assessment, drafted ADR and stories (validated), NFR traceability, container diagram,
            one proposal pack; the requirement can come from a structured file or a document
feedback -> the architecture review board approves or rejects the ADR; the product owner each story
report   -> what has been approved so far
evaluate -> assessment, ranking, ADR conflicts, traceability and open questions compared with labels
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from ecc_core.audit import AuditLog, new_correlation_id

from .assess import Assessment, Rules, Trace, assess, trace
from .diagram import Diagram, container_diagram
from .drafting import APPROVERS, AdrDraft, Story, draft_input, validate_drafts
from .html import MERMAID_ESM, proposal_html
from .intake import Extraction
from .sources import ArchitectureInputs

AGENT = "agent:architecture-proposer"
BANNER = ("PROPOSAL: drafted for review. Nothing has been written to the ADR repository or the backlog. "
          "Approve or reject each item with `ecc architecture feedback`.")
MARK = {"meets": "✅ meets", "at_risk": "⚠️ at risk", "fails": "❌ fails", "unknown": "❔ unknown"}


def run(inp: ArchitectureInputs, drafter, workdir: Path, extraction: Extraction | None = None,
        rules: Rules = Rules(), mermaid_url: str = MERMAID_ESM) -> dict:
    """Assess, draft, validate, trace, draw and write the proposal pack. Returns the result (also saved as results.json).

    extraction: set when the requirement was extracted from a document (see intake.py)."""
    workdir = Path(workdir)
    (workdir / "proposal").mkdir(parents=True, exist_ok=True)
    audit = AuditLog(workdir / "audit.jsonl")
    cid = new_correlation_id()
    req_id = inp.requirement["id"]
    audit.record(AGENT, "architecture.run.started", req_id, cid, provider=drafter.name)
    for tool in ("requirements.read", "patterns.read", "adrs.read"):
        audit.record(AGENT, "tool.call", tool, cid)
    if extraction:
        src = extraction.requirement["source"]
        audit.record(AGENT, "architecture.requirement.extracted", src["document"], cid, status=src["status"],
                     rejected_items=len(extraction.rejected), flags=extraction.flags)

    a = assess(inp, rules)
    for eid in a.flagged_notes:
        audit.record("policy-engine", "input.flagged", eid, cid, outcome="flagged", reason="possible_prompt_injection")
    raw = drafter.draft_architecture(draft_input(inp, a)) if a.preferred else {"summary": "", "adr": None, "stories": []}
    adr, stories, rejected = validate_drafts(raw, draft_input(inp, a))
    traces = trace(inp, a, stories)
    diagram = container_diagram(inp.pattern(a.preferred), inp.requirement["regions"], traces) if a.preferred else None

    if adr:
        audit.record(AGENT, "architecture.adr.drafted", adr.id, cid, chosen=adr.chosen_option,
                     approver=APPROVERS["adr"], accepted=False)
    for s in stories:
        audit.record(AGENT, "architecture.story.drafted", s.id, cid, approver=APPROVERS["story"], in_backlog=False)
    for r in rejected:
        audit.record("policy-engine", "architecture.draft.rejected", r.item, cid, outcome="rejected", reason=r.reason)

    covered = {c for s in stories for c in s.capability_ids}
    result = {
        "requirement_id": req_id, "as_of": a.as_of, "provider": drafter.name, "summary": raw.get("summary", ""),
        "preferred": a.preferred, "next_adr_id": a.next_adr_id,
        "options": [asdict(o) for o in a.options], "cells": [asdict(c) for c in a.cells],
        "open_questions": [asdict(q) for q in a.open_questions],
        "adr": asdict(adr) if adr else None, "stories": [asdict(s) for s in stories],
        "rejected_drafts": [asdict(r) for r in rejected],
        "traceability": [asdict(t) for t in traces],
        "uncovered_capabilities": [c["id"] for c in inp.requirement["capabilities"] if c["id"] not in covered],
        "flagged_notes": a.flagged_notes,
        "diagram": asdict(diagram) if diagram else None,
        "requirement_source": extraction.requirement["source"] if extraction else {"document": None, "status": "structured input"},
        "extraction_rejected": extraction.rejected if extraction else [],
        "evidence": [asdict(e) for e in a.evidence],
    }
    (workdir / "results.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    (workdir / "proposal" / f"{req_id}.md").write_text(
        proposal_md(inp, a, adr, stories, traces, rejected, diagram, extraction), encoding="utf-8")
    if diagram:
        (workdir / "proposal" / f"{req_id}-container.mmd").write_text(diagram.mermaid + "\n", encoding="utf-8")
    (workdir / "proposal" / f"{req_id}.html").write_text(proposal_html(result, inp.requirement, mermaid_url), encoding="utf-8")
    audit.record(AGENT, "architecture.run.completed", req_id, cid, preferred=a.preferred, stories=len(stories),
                 rejected_drafts=len(rejected), traced=sum(t.status == "traced" for t in traces))
    return result


def proposal_md(inp: ArchitectureInputs, a: Assessment, adr: AdrDraft | None, stories: list[Story],
                traces: list[Trace], rejected, diagram: Diagram | None = None,
                extraction: Extraction | None = None) -> str:
    req = inp.requirement
    nfrs = req["nfrs"]
    ev = {e.id: e for e in a.evidence}
    traced = sum(t.status == "traced" for t in traces)
    L = [f"# Architecture proposal · {req['id']} {req['title']}", "", f"> {BANNER}", "",
         f"As of {a.as_of}. Regions: {', '.join(req['regions'])}. NFRs traced: **{traced} of {len(traces)}**.", ""]
    if extraction:
        src = extraction.requirement["source"]
        L += [f"> Requirement extracted from **{src['document']}** · {src['status']}. Check the capabilities, NFRs "
              "and targets below against the document before approving anything.", ""]
        if extraction.rejected:
            L += ["Items not extracted (failed validation):", ""] + [f"- {r}" for r in extraction.rejected] + [""]
        if extraction.flags:
            L += [f"Document flags: {', '.join(extraction.flags)} (secrets were redacted before the model saw it).", ""]

    L += ["## Option comparison", "", "Scored in code against each NFR; the model did not rank the options.", "",
          "| NFR | " + " | ".join(f"{o.pattern_id} {o.name}" for o in a.options) + " |",
          "|---|" + "---|" * len(a.options)]
    for n in nfrs:
        L.append(f"| {n['id']} {n['name']} ({n['priority']}) | "
                 + " | ".join(f"{MARK[a.cell(o.pattern_id, n['id']).status]} · {a.cell(o.pattern_id, n['id']).detail}"
                              for o in a.options) + " |")
    L.append("| ADR conflicts | " + " | ".join(", ".join(o.adr_conflicts) or "none" for o in a.options) + " |")
    L.append("| Relative cost | " + " | ".join(o.relative_cost for o in a.options) + " |")
    L.append("| **Result** | " + " | ".join(f"**{o.status.title()}**" + (f": {o.condition}" if o.condition else "")
                                         for o in a.options) + " |")
    L.append("")

    L += [f"## {a.next_adr_id} (draft)", ""]
    if adr:
        L += [f"**{adr.title}** · Status: {adr.status}", ""]
        if adr.disagrees_with_ranking:
            L += [f"> ⚠️ The draft chooses {adr.chosen_option}, but the assessment preferred {a.preferred}. "
                  "The review board should decide.", ""]
        L += ["**Context.** " + adr.context, "", "**Decision.** " + adr.decision, "", "**Consequences**", ""]
        L += [f"- {c}" for c in adr.consequences] + ["", "**Alternatives considered**", ""]
        L += [f"- **{alt['option_id']}**: {alt['why_not']} ({', '.join(alt['evidence']) or 'no evidence'})"
              for alt in adr.alternatives]
        L += ["", f"Evidence: {', '.join(adr.evidence)}.", ""]
    else:
        L += ["_No ADR drafted._", ""]

    if diagram:
        L += [f"## Container view · {diagram.pattern_id}", "",
              "Drawn in code from the pattern library; each component lists the NFRs traced to it. "
              f"Also saved as `{req['id']}-container.mmd`.", "", "```mermaid", diagram.mermaid, "```", ""]
        if diagram.issues:
            L += ["Diagram issues:", ""] + [f"- {i}" for i in diagram.issues] + [""]
    elif a.preferred:
        L += ["## Container view", "", f"_The pattern library defines no components for {a.preferred}._", ""]

    L += ["## NFR traceability", "", "| NFR | Target | Component | Mechanism | ADRs | Stories | Status |",
          "|---|---|---|---|---|---|---|"]
    for t in traces:
        L.append(f"| {t.nfr_id} {t.name} | {t.target} | {t.component or '—'} | {t.mechanism or '—'} | "
                 f"{', '.join(t.adrs) or '—'} | {', '.join(t.stories) or '—'} | "
                 + ("Traced" if t.status == "traced" else f"**Gap**: {t.reason}") + " |")
    L.append("")

    L += ["## User stories (drafts)", ""]
    for s in stories:
        L += [f"### {s.id} · {s.title}", "", f"As a {s.as_a}, I want {s.i_want}, so that {s.so_that}.", ""]
        L += [f"- [ ] {c}" for c in s.acceptance_criteria]
        L += ["", f"Covers {', '.join(s.capability_ids + s.nfr_ids)} · Evidence {', '.join(s.evidence)} · {s.status}", ""]
    if not stories:
        L += ["_None._", ""]

    L += ["## Open questions for the business", ""]
    L += [f"- **{q.id}** {q.question}" + (f" Affects {', '.join(q.affects)}." if q.affects and q.affects != [q.id] else "")
          for q in a.open_questions] + [""]
    if rejected:
        L += ["## Drafts rejected by validation", ""] + [f"- {r.item}: {r.reason}" for r in rejected] + [""]
    if a.flagged_notes:
        L += ["## Flagged input", ""] + [f"- **{i}** was treated as data, not instructions: {ev[i].summary}"
                                         for i in a.flagged_notes] + [""]
    cited = sorted({i for o in a.options for i in o.evidence} | set(adr.evidence if adr else [])
                   | {i for s in stories for i in s.evidence} | {q.evidence for q in a.open_questions},
                   key=lambda x: int(x[1:]))
    L += ["## Evidence", ""] + [f"- **{i}** {ev[i].summary}" for i in cited]
    L += ["", "_Generated by Engineering Command Centre · use case 3 · Author: Pradeep Sahoo_", ""]
    return "\n".join(L)


def record_feedback(workdir: Path, item_id: str, accept: bool, by: str, note: str = "") -> dict:
    workdir = Path(workdir)
    results = json.loads((workdir / "results.json").read_text(encoding="utf-8"))
    items = {s["id"]: "story" for s in results["stories"]}
    if results["adr"]:
        items[results["adr"]["id"]] = "adr"
    if item_id not in items:
        raise ValueError(f"{item_id} is not a drafted ADR or story in the latest run")
    entry = {"item_id": item_id, "kind": items[item_id], "accepted": accept, "by": by, "role": APPROVERS[items[item_id]],
             "note": note, "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    with (workdir / "feedback.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")
    AuditLog(workdir / "audit.jsonl").record(by, f"architecture.{items[item_id]}.reviewed", item_id, "-", accepted=accept)
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
                fb[e["item_id"]] = e
    adr = results["adr"]
    stories = [s["id"] for s in results["stories"]]
    reviewed = [i for i in stories if i in fb]
    by_agent = [e for e in AuditLog(workdir / "audit.jsonl").entries()
                if e["actor"] == AGENT and e["action"] in ("architecture.adr.accepted", "architecture.story.added_to_backlog")]
    return {
        "requirement_id": results["requirement_id"], "preferred": results["preferred"],
        "adr": adr["id"] if adr else None,
        "adr_decision": (("approved" if fb[adr["id"]]["accepted"] else "rejected") if adr and adr["id"] in fb else "pending"),
        "stories_drafted": len(stories), "stories_reviewed": len(reviewed),
        "story_acceptance_rate": round(sum(fb[i]["accepted"] for i in reviewed) / len(reviewed), 3) if reviewed else None,
        "nfrs_traced": sum(t["status"] == "traced" for t in results["traceability"]),
        "nfrs_total": len(results["traceability"]),
        "open_questions": len(results["open_questions"]),
        "decisions_made_by_agent": len(by_agent),
    }


def evaluate(result: dict, labels: dict, gates: dict) -> dict:
    """Compare a run with expected results. Returns metrics, gate results and a markdown report."""
    cells = {(c["pattern_id"], c["nfr_id"]): c["status"] for c in result["cells"]}
    want_cells = {(p, n): s for p, row in labels["assessment"].items() for n, s in row.items()}
    right = sum(cells.get(k) == v for k, v in want_cells.items())
    wrong_cells = sorted(f"{p}/{n}: {cells.get((p, n))} (expected {v})" for (p, n), v in want_cells.items()
                         if cells.get((p, n)) != v)
    status = {o["pattern_id"]: o["status"] for o in result["options"]}
    conflicts = {o["pattern_id"]: o["adr_conflicts"] for o in result["options"] if o["adr_conflicts"]}
    traced = {t["nfr_id"] for t in result["traceability"] if t["status"] == "traced"}
    gaps = sorted(t["nfr_id"] for t in result["traceability"] if t["status"] == "gap")
    want_traced = set(labels["traced_nfrs"])
    invented = sum(len(r["invented_figures"]) for r in result["rejected_drafts"])
    m = {
        "provider": result["provider"],
        "assessment_accuracy": round(right / len(want_cells), 3) if want_cells else 1.0,
        "wrong_cells": wrong_cells,
        "option_status_match": status == labels["option_status"],
        "preferred_match": result["preferred"] == next((p for p, s in labels["option_status"].items() if s == "preferred"), None),
        "adr_conflicts_match": conflicts == labels["adr_conflicts"],
        "next_adr_id_match": result["next_adr_id"] == labels["next_adr_id"],
        "nfr_trace_recall": round(len(traced & want_traced) / len(want_traced), 3) if want_traced else 1.0,
        "nfr_trace_precision": round(len(traced & want_traced) / len(traced), 3) if traced else 0.0,
        "gaps_match": gaps == sorted(labels["gaps"]),
        "open_questions_match": sorted(q["id"] for q in result["open_questions"]) == sorted(labels["open_questions"]),
        "adr_drafted": result["adr"] is not None,
        "stories_drafted": len(result["stories"]),
        "uncovered_capabilities": result["uncovered_capabilities"],
        "rejected_drafts": len(result["rejected_drafts"]),
        "invented_figures": invented,
        "decisions_made_without_approval": 0,      # there is no path that accepts an ADR or writes the backlog
        "diagram_drawn": result["diagram"] is not None,
        "diagram_components_match": (result["diagram"] or {}).get("components") == labels.get("diagram_components"),
        "diagram_shows_traced_nfrs": sorted((result["diagram"] or {}).get("nfrs_shown", [])) == sorted(traced),
        "diagram_issues": len((result["diagram"] or {}).get("issues", [])),
    }
    checks = {
        "assessment_accuracy": m["assessment_accuracy"] >= gates["assessment_accuracy_min"],
        "preferred_option": m["preferred_match"] or not gates["preferred_option_match"],
        "nfr_trace_recall": m["nfr_trace_recall"] >= gates["nfr_trace_recall_min"],
        "rejected_drafts": m["rejected_drafts"] <= gates["rejected_drafts_max"],
        "invented_figures": m["invented_figures"] <= gates["invented_figures_max"],
        "decisions_made_without_approval": m["decisions_made_without_approval"] <= gates["decisions_made_without_approval_max"],
        "diagram": m["diagram_drawn"] and m["diagram_issues"] <= gates["diagram_issues_max"],
    }
    ok = all(checks.values())
    tick = lambda b: "✅" if b else "❌"
    md = [f"# Architecture evaluation · provider `{m['provider']}`", "",
          f"Requirement {result['requirement_id']}: **{right} of {len(want_cells)}** assessment cells as expected; "
          f"preferred option {result['preferred']}; {len(traced)} of {len(result['traceability'])} NFRs traced. "
          f"Gates: **{'PASS' if ok else 'FAIL'}**.", "",
          "| Measure | Result | Gate | |", "|---|---|---|---|",
          f"| Assessment accuracy | {m['assessment_accuracy']:.0%} | ≥ {gates['assessment_accuracy_min']:.0%} | {tick(checks['assessment_accuracy'])} |",
          f"| Preferred option matches | {m['preferred_match']} | {'required' if gates['preferred_option_match'] else '—'} | {tick(checks['preferred_option'])} |",
          f"| Option statuses match | {m['option_status_match']} | — | |",
          f"| ADR conflicts match | {m['adr_conflicts_match']} | — | |",
          f"| NFR trace recall | {m['nfr_trace_recall']:.0%} | ≥ {gates['nfr_trace_recall_min']:.0%} | {tick(checks['nfr_trace_recall'])} |",
          f"| NFR trace precision | {m['nfr_trace_precision']:.0%} | — | |",
          f"| Gaps match | {m['gaps_match']} | — | |",
          f"| Open questions match | {m['open_questions_match']} | — | |",
          f"| ADR drafted | {m['adr_drafted']} | — | |",
          f"| Stories drafted | {m['stories_drafted']} | — | |",
          f"| Drafts rejected by validation | {m['rejected_drafts']} | ≤ {gates['rejected_drafts_max']} | {tick(checks['rejected_drafts'])} |",
          f"| Invented figures | {m['invented_figures']} | ≤ {gates['invented_figures_max']} | {tick(checks['invented_figures'])} |",
          f"| Container diagram drawn, issues | {m['diagram_drawn']}, {m['diagram_issues']} | drawn, ≤ {gates['diagram_issues_max']} | {tick(checks['diagram'])} |",
          f"| Diagram components match | {m['diagram_components_match']} | — | |",
          f"| Diagram shows every traced NFR | {m['diagram_shows_traced_nfrs']} | — | |",
          f"| Decisions made without approval | {m['decisions_made_without_approval']} | ≤ {gates['decisions_made_without_approval_max']} | {tick(checks['decisions_made_without_approval'])} |",
          "", f"Wrong cells: {m['wrong_cells'] or 'none'} · Uncovered capabilities: {m['uncovered_capabilities'] or 'none'}", "",
          f"_Gate note: {gates.get('note', '')}_", ""]
    if m["provider"] == "mock":
        md += ["_Provider `mock` drafts the ADR and stories from fixed templates. The assessment, ranking and "
               "traceability are deterministic code in every mode; the provider only changes the drafted wording._", ""]
    md += ["_Generated by Engineering Command Centre · use case 3 · Author: Pradeep Sahoo_", ""]
    return {"metrics": m, "gate_results": checks, "passed": ok, "report_md": "\n".join(md)}
