# Author: Pradeep Sahoo
"""Commands for use case 3, registered under `ecc architecture`.

    ecc architecture ingest <document.md>
    ecc architecture run | evaluate [--requirement-doc <document.md>]
    ecc architecture feedback <ADR-ID|STORY-ID> --accept yes|no --by NAME
    ecc architecture report

Data locations, assessment margins and pilot gates come from
[use_cases.architecture] in the product configuration.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecc_core.plugin import Context

PROVIDERS = ["mock", "claude"]
DOC_HELP = "start from a requirement document (.md/.txt) instead of requirement.json"


def register(p: argparse.ArgumentParser, ctx: Context) -> None:
    from .assess import Rules
    p.add_argument("--workdir", help="default: <runs>/architecture")
    sub = p.add_subparsers(dest="architecture_cmd", required=True)

    def workdir(a) -> Path:
        return Path(a.workdir) if a.workdir else ctx.runs

    def rules() -> Rules:
        s = ctx.settings
        return Rules(s["availability_margin"], s["latency_margin"], s["throughput_margin"])

    def extractor(a):
        from . import get_extractor
        return get_extractor(ctx.provider_name(a.provider), ctx.claude)

    def drafter(a):
        from . import get_drafter
        return get_drafter(ctx.provider_name(a.provider), ctx.claude)

    def inputs(a):
        """Inputs plus the extraction, when the requirement comes from a document (--requirement-doc)."""
        from .intake import extract, save
        from .sources import ArchitectureInputs
        inp = ArchitectureInputs.load(ctx.path("arch_dir"))
        if not a.requirement_doc:
            return inp, None
        ex = extract(Path(a.requirement_doc), extractor(a))
        save(ex, workdir(a) / "requirement.extracted.json")
        inp.requirement = ex.requirement
        return inp, ex

    def run_pipeline(a):
        from .review import run
        inp, ex = inputs(a)
        return run(inp, drafter(a), workdir(a), ex, rules(), ctx.settings["mermaid_url"])

    def cmd_ingest(a) -> int:
        from .intake import extract, save
        ex = extract(Path(a.document), extractor(a))
        out = workdir(a) / "requirement.extracted.json"
        save(ex, out)
        r = ex.requirement
        print(f"{r['id']} \u201c{r['title']}\u201d: {len(r['capabilities'])} capabilities, {len(r['nfrs'])} NFRs "
              f"({sum(n['target'] is None for n in r['nfrs'])} without an agreed target), {len(r['open_decisions'])} "
              f"open decision(s), {len(ex.rejected)} item(s) rejected by validation. Flags: {', '.join(ex.flags) or 'none'}.")
        for x in ex.rejected:
            print(f"  rejected: {x}")
        print(f"Extracted requirement: {out}  (status: {r['source']['status']})")
        return 0

    def cmd_run(a) -> int:
        r = run_pipeline(a)
        proposal = workdir(a) / "proposal"
        traced = sum(t["status"] == "traced" for t in r["traceability"])
        print(f"{r['requirement_id']}: preferred option {r['preferred'] or 'none'}, "
              f"{'ADR ' + r['adr']['id'] + ' drafted' if r['adr'] else 'no ADR drafted'}, {len(r['stories'])} stories, "
              f"{traced} of {len(r['traceability'])} NFRs traced, {len(r['open_questions'])} open question(s), "
              f"{len(r['rejected_drafts'])} draft(s) rejected by validation.")
        if r["diagram"]:
            print(f"Container diagram: {proposal / (r['requirement_id'] + '-container.mmd')}")
        print(f"Proposal page (open in a browser): {proposal / (r['requirement_id'] + '.html')}")
        print(f"Proposal: {proposal / (r['requirement_id'] + '.md')}  "
              "(nothing was written to the ADR repository or the backlog)")
        return 0

    def cmd_evaluate(a) -> int:
        from .review import evaluate
        result = run_pipeline(a)
        labels = json.loads((ctx.path("arch_dir") / "labels.json").read_text(encoding="utf-8"))
        ev = evaluate(result, labels, ctx.gates)
        (workdir(a) / "evaluation.md").write_text(ev["report_md"], encoding="utf-8")
        print(ev["report_md"])
        print(f"Full results: {workdir(a)}")
        return 0 if ev["passed"] else 1

    def cmd_feedback(a) -> int:
        from .review import record_feedback
        print(json.dumps(record_feedback(workdir(a), a.item, a.accept == "yes", a.by, a.note or ""), indent=2))
        return 0

    def cmd_report(a) -> int:
        from .review import report
        print(json.dumps(report(workdir(a)), indent=2))
        return 0

    i = sub.add_parser("ingest", help="Extract a structured requirement from a requirement document (.md/.txt)")
    i.add_argument("document")
    i.add_argument("--provider", choices=PROVIDERS)
    i.set_defaults(fn=cmd_ingest)
    for name, fn, help_ in (("run", cmd_run, "Assess options, draft the ADR and stories, draw the diagram, write the proposal"),
                            ("evaluate", cmd_evaluate, "Run, then score against labels and pilot gates")):
        c = sub.add_parser(name, help=help_)
        c.add_argument("--provider", choices=PROVIDERS)
        c.add_argument("--requirement-doc", help=DOC_HELP)
        c.set_defaults(fn=fn)
    f = sub.add_parser("feedback", help="Review board approves or rejects the ADR; product owner a story")
    f.add_argument("item", help="ADR id (e.g. ADR-007) or story id (e.g. STORY-02)")
    f.add_argument("--accept", required=True, choices=["yes", "no"])
    f.add_argument("--by", required=True)
    f.add_argument("--note")
    f.set_defaults(fn=cmd_feedback)
    rp = sub.add_parser("report", help="Approvals so far")
    rp.set_defaults(fn=cmd_report)
