# Author: Pradeep Sahoo
"""Command line for both use cases.

Use case 1 (incident investigation): investigate | replay | shadow run | shadow feedback | shadow report
Use case 2 (knowledge & runbooks):   knowledge run | knowledge evaluate | knowledge feedback | knowledge report
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from .audit import AuditLog
from .investigator import investigate
from .models import CAUSE_CATEGORIES
from .providers import ProviderError, get_provider
from .render import investigation_md

HOME = Path(__file__).resolve().parents[2]          # incident-investigator/
DATA = HOME / "data" / "synthetic"
RUNS = HOME / "runs"


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def cmd_investigate(a) -> int:
    inv = investigate(Path(a.incident), get_provider(a.provider), "replay", AuditLog(RUNS / "adhoc-audit.jsonl"),
                      Path(a.runbooks))
    print(json.dumps(inv.to_dict(), indent=2) if a.json else investigation_md(inv))
    return 0


def cmd_replay(a) -> int:
    from .replay import run
    out = Path(a.out) if a.out else RUNS / "replay" / f"{a.provider}-{_stamp()}"
    gates = json.loads(Path(a.gates).read_text(encoding="utf-8"))["incident_investigation"]
    result = run(Path(a.incidents), Path(a.labels), Path(a.runbooks), get_provider(a.provider), out, gates)
    print((out / "report.md").read_text(encoding="utf-8"))
    print(f"Full results: {out}")
    return 0 if result["passed"] else 1


def _shadow(a):
    from .shadow import ShadowRunner
    return ShadowRunner(Path(a.inbox), Path(a.workdir), Path(a.runbooks))


def cmd_shadow_run(a) -> int:
    runner = _shadow(a)
    done = runner.process_new(get_provider(a.provider))
    print(f"Investigated {len(done)} new incident(s): {', '.join(done) or 'none'}")
    print(f"Review queue: {runner.outbox}  (on-call was not notified)")
    return 0


def cmd_shadow_feedback(a) -> int:
    entry = _shadow(a).record_feedback(a.incident, a.useful == "yes", a.confirmed_cause, a.by, a.minutes, a.note or "")
    print(json.dumps(entry, indent=2))
    return 0


def cmd_shadow_report(a) -> int:
    print(json.dumps(_shadow(a).report(), indent=2))
    return 0


def _kb(a):
    from .knowledge import KnowledgeBase
    return KnowledgeBase.load(Path(a.runbooks), Path(a.knowledge_dir))


def cmd_knowledge_run(a) -> int:
    from .knowledge import get_drafter
    from .knowledge.review import run
    result = run(_kb(a), get_drafter(a.provider), Path(a.workdir))
    print(f"As of {result['as_of']}: {len(result['findings'])} findings, {len(result['repeats'])} repeat cluster(s), "
          f"{len(result['overdue'])} overdue action(s), {len(result['edits'])} drafted edit(s), "
          f"{len(result['rejected_edits'])} rejected by validation.")
    print(f"Review queue: {Path(a.workdir) / 'review-queue'}  (nothing was changed in the runbook wiki)")
    return 0


def cmd_knowledge_evaluate(a) -> int:
    from .knowledge import get_drafter
    from .knowledge.review import evaluate, run
    out = Path(a.workdir)
    result = run(_kb(a), get_drafter(a.provider), out)
    labels = json.loads((Path(a.knowledge_dir) / "labels.json").read_text(encoding="utf-8"))
    gates = json.loads(Path(a.gates).read_text(encoding="utf-8"))["knowledge"]
    ev = evaluate(result, labels, gates)
    (out / "evaluation.md").write_text(ev["report_md"], encoding="utf-8")
    print(ev["report_md"])
    print(f"Full results: {out}")
    return 0 if ev["passed"] else 1


def cmd_knowledge_feedback(a) -> int:
    from .knowledge.review import record_feedback
    print(json.dumps(record_feedback(Path(a.workdir), a.edit, a.accept == "yes", a.by, a.note or ""), indent=2))
    return 0


def cmd_knowledge_report(a) -> int:
    from .knowledge.review import report
    print(json.dumps(report(Path(a.workdir)), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="investigator", description="Evidence-backed incident investigation (read-only).")
    p.add_argument("--runbooks", default=str(DATA / "runbooks.json"))
    sub = p.add_subparsers(dest="cmd", required=True)

    i = sub.add_parser("investigate", help="Investigate one incident file")
    i.add_argument("incident")
    i.add_argument("--provider", default="mock", choices=["mock", "claude"])
    i.add_argument("--json", action="store_true")
    i.set_defaults(fn=cmd_investigate)

    r = sub.add_parser("replay", help="Score the investigator on past incidents with known causes")
    r.add_argument("--provider", default="mock", choices=["mock", "claude"])
    r.add_argument("--incidents", default=str(DATA / "incidents"))
    r.add_argument("--labels", default=str(DATA / "labels.json"))
    r.add_argument("--gates", default=str(HOME / "config" / "pilot_gates.json"))
    r.add_argument("--out")
    r.set_defaults(fn=cmd_replay)

    s = sub.add_parser("shadow", help="Shadow mode on live incidents")
    s.add_argument("--inbox", default=str(DATA / "live"))
    s.add_argument("--workdir", default=str(RUNS / "shadow"))
    ssub = s.add_subparsers(dest="shadow_cmd", required=True)
    sr = ssub.add_parser("run", help="Investigate new incidents in the inbox")
    sr.add_argument("--provider", default="mock", choices=["mock", "claude"])
    sr.set_defaults(fn=cmd_shadow_run)
    sf = ssub.add_parser("feedback", help="Record an engineer's verdict on one investigation")
    sf.add_argument("incident")
    sf.add_argument("--useful", required=True, choices=["yes", "no"])
    sf.add_argument("--confirmed-cause", choices=list(CAUSE_CATEGORIES))
    sf.add_argument("--minutes", type=int, help="Engineer's own time to first correct hypothesis")
    sf.add_argument("--by", required=True)
    sf.add_argument("--note")
    sf.set_defaults(fn=cmd_shadow_feedback)
    sp = ssub.add_parser("report", help="Usefulness and agreement so far")
    sp.set_defaults(fn=cmd_shadow_report)

    k = sub.add_parser("knowledge", help="Use case 2: runbook health, repeat incidents, drafted edits")
    k.add_argument("--knowledge-dir", default=str(DATA / "knowledge"))
    k.add_argument("--workdir", default=str(RUNS / "knowledge"))
    ksub = k.add_subparsers(dest="knowledge_cmd", required=True)
    kr = ksub.add_parser("run", help="Check runbooks, draft edits, write the review queue")
    kr.add_argument("--provider", default="mock", choices=["mock", "claude"])
    kr.set_defaults(fn=cmd_knowledge_run)
    ke = ksub.add_parser("evaluate", help="Run, then score findings against labels and pilot gates")
    ke.add_argument("--provider", default="mock", choices=["mock", "claude"])
    ke.add_argument("--gates", default=str(HOME / "config" / "pilot_gates.json"))
    ke.set_defaults(fn=cmd_knowledge_evaluate)
    kf = ksub.add_parser("feedback", help="A runbook owner accepts or rejects a drafted edit")
    kf.add_argument("edit")
    kf.add_argument("--accept", required=True, choices=["yes", "no"])
    kf.add_argument("--by", required=True)
    kf.add_argument("--note")
    kf.set_defaults(fn=cmd_knowledge_feedback)
    kp = ksub.add_parser("report", help="Findings and edit acceptance so far")
    kp.set_defaults(fn=cmd_knowledge_report)
    return p


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):      # Windows consoles default to cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except ProviderError as exc:
        print(f"Provider error: {exc}", file=sys.stderr)
        return 2
    except (FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
