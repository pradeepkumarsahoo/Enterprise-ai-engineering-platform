# Author: Pradeep Sahoo
"""Commands for use case 2, registered under `ecc knowledge`.

    ecc knowledge run | evaluate | feedback <EDIT-ID> --accept yes|no --by NAME | report

Data locations, thresholds and pilot gates come from [use_cases.knowledge] in
the product configuration; runbooks come from [sources].
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecc_core.plugin import Context

PROVIDERS = ["mock", "claude"]


def register(p: argparse.ArgumentParser, ctx: Context) -> None:
    from .checks import Thresholds
    p.add_argument("--workdir", help="default: <runs>/knowledge")
    sub = p.add_subparsers(dest="knowledge_cmd", required=True)

    def workdir(a) -> Path:
        return Path(a.workdir) if a.workdir else ctx.runs

    def thresholds() -> Thresholds:
        return Thresholds(**ctx.settings)

    def kb():
        from .sources import KnowledgeBase
        return KnowledgeBase.load(ctx.source("runbooks"), ctx.path("knowledge_dir"))

    def drafter(a):
        from . import get_drafter
        return get_drafter(ctx.provider_name(a.provider), ctx.claude)

    def cmd_run(a) -> int:
        from .review import run
        result = run(kb(), drafter(a), workdir(a), thresholds())
        print(f"As of {result['as_of']}: {len(result['findings'])} findings, {len(result['repeats'])} repeat cluster(s), "
              f"{len(result['overdue'])} overdue action(s), {len(result['edits'])} drafted edit(s), "
              f"{len(result['rejected_edits'])} rejected by validation.")
        print(f"Review queue: {workdir(a) / 'review-queue'}  (nothing was changed in the runbook wiki)")
        return 0

    def cmd_evaluate(a) -> int:
        from .review import evaluate, run
        out = workdir(a)
        result = run(kb(), drafter(a), out, thresholds())
        labels = json.loads((ctx.path("knowledge_dir") / "labels.json").read_text(encoding="utf-8"))
        ev = evaluate(result, labels, ctx.gates)
        (out / "evaluation.md").write_text(ev["report_md"], encoding="utf-8")
        print(ev["report_md"])
        print(f"Full results: {out}")
        return 0 if ev["passed"] else 1

    def cmd_feedback(a) -> int:
        from .review import record_feedback
        print(json.dumps(record_feedback(workdir(a), a.edit, a.accept == "yes", a.by, a.note or ""), indent=2))
        return 0

    def cmd_report(a) -> int:
        from .review import report
        print(json.dumps(report(workdir(a)), indent=2))
        return 0

    r = sub.add_parser("run", help="Check runbooks, draft edits, write the review queue")
    r.add_argument("--provider", choices=PROVIDERS)
    r.set_defaults(fn=cmd_run)
    e = sub.add_parser("evaluate", help="Run, then score findings against labels and pilot gates")
    e.add_argument("--provider", choices=PROVIDERS)
    e.set_defaults(fn=cmd_evaluate)
    f = sub.add_parser("feedback", help="A runbook owner accepts or rejects a drafted edit")
    f.add_argument("edit")
    f.add_argument("--accept", required=True, choices=["yes", "no"])
    f.add_argument("--by", required=True)
    f.add_argument("--note")
    f.set_defaults(fn=cmd_feedback)
    rp = sub.add_parser("report", help="Findings and edit acceptance so far")
    rp.set_defaults(fn=cmd_report)
