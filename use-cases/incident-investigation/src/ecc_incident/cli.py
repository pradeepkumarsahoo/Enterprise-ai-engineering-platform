# Author: Pradeep Sahoo
"""Commands for use case 1, registered under `ecc incident`.

    ecc incident investigate <incident.json> [--json]
    ecc incident replay [--out DIR]
    ecc incident shadow run | feedback <ID> ... | report

Data locations, confidence limits and pilot gates come from
[use_cases.incident] in the product configuration.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path

from ecc_core.audit import AuditLog
from ecc_core.plugin import Context

from .models import CAUSE_CATEGORIES
from .policy import Limits

PROVIDERS = ["mock", "claude"]


def limits(ctx: Context) -> Limits:
    return Limits(ctx.settings["lead_confidence_min"], ctx.settings["max_confidence"])


def provider(ctx: Context, name: str | None):
    from .providers import get_provider
    return get_provider(ctx.provider_name(name), ctx.claude, limits(ctx))


def register(p: argparse.ArgumentParser, ctx: Context) -> None:
    sub = p.add_subparsers(dest="incident_cmd", required=True)

    def cmd_investigate(a) -> int:
        from .investigator import investigate
        from .render import investigation_md
        inv = investigate(Path(a.incident), provider(ctx, a.provider), "replay",
                          AuditLog(ctx.runs / "adhoc-audit.jsonl"), ctx.source("runbooks"), limits(ctx))
        print(json.dumps(inv.to_dict(), indent=2) if a.json else investigation_md(inv, "", limits(ctx).lead_confidence_min))
        return 0

    def cmd_replay(a) -> int:
        from .replay import run
        name = ctx.provider_name(a.provider)
        out = Path(a.out) if a.out else ctx.runs / "replay" / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
        result = run(ctx.path("incidents"), ctx.path("labels"), ctx.source("runbooks"), provider(ctx, a.provider),
                     out, ctx.gates, limits(ctx))
        print((out / "report.md").read_text(encoding="utf-8"))
        print(f"Full results: {out}")
        return 0 if result["passed"] else 1

    def shadow(a):
        from .shadow import ShadowRunner
        return ShadowRunner(ctx.path("live"), Path(a.workdir) if a.workdir else ctx.runs / "shadow",
                            ctx.source("runbooks"), limits(ctx))

    def cmd_shadow_run(a) -> int:
        runner = shadow(a)
        done = runner.process_new(provider(ctx, a.provider))
        print(f"Investigated {len(done)} new incident(s): {', '.join(done) or 'none'}")
        print(f"Review queue: {runner.outbox}  (on-call was not notified)")
        return 0

    def cmd_shadow_feedback(a) -> int:
        entry = shadow(a).record_feedback(a.incident, a.useful == "yes", a.confirmed_cause, a.by, a.minutes, a.note or "")
        print(json.dumps(entry, indent=2))
        return 0

    def cmd_shadow_report(a) -> int:
        print(json.dumps(shadow(a).report(), indent=2))
        return 0

    i = sub.add_parser("investigate", help="Investigate one incident file")
    i.add_argument("incident")
    i.add_argument("--provider", choices=PROVIDERS)
    i.add_argument("--json", action="store_true")
    i.set_defaults(fn=cmd_investigate)

    r = sub.add_parser("replay", help="Score the investigator on past incidents with known causes")
    r.add_argument("--provider", choices=PROVIDERS)
    r.add_argument("--out", help="output folder (default: <runs>/incident/replay/<provider>-<time>)")
    r.set_defaults(fn=cmd_replay)

    s = sub.add_parser("shadow", help="Shadow mode on live incidents")
    s.add_argument("--workdir", help="default: <runs>/incident/shadow")
    ssub = s.add_subparsers(dest="shadow_cmd", required=True)
    sr = ssub.add_parser("run", help="Investigate new incidents in the inbox")
    sr.add_argument("--provider", choices=PROVIDERS)
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
