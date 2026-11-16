# Author: Pradeep Sahoo
"""Commands for use case 1, registered under `ecc incident`.

    ecc incident investigate <incident.json> [--json]
    ecc incident replay [--out DIR]
    ecc incident shadow run | feedback <ID> ... | report
    ecc incident servicenow pull | replay [--out DIR]

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

    def sn_pull(a):
        from .providers import get_labeller
        from .servicenow import pull
        name = ctx.provider_name(a.provider)
        out = Path(a.out) if a.out else ctx.runs / "servicenow" / f"{name}-{datetime.now():%Y%m%d-%H%M%S}"
        client = ctx.servicenow()
        return pull(client, ctx.settings["servicenow_query"], out, get_labeller(name, ctx.claude)), client

    def cmd_sn_pull(a) -> int:
        r, client = sn_pull(a)
        print(f"{client.instance} ({client.settings.transport}): {len(r.incidents)} incident(s) pulled, "
              f"{len(r.labels)} with a cause stated in the resolution notes, {len(r.unlabelled)} without, "
              f"{len(r.rejected_labels)} label(s) rejected.")
        print(f"Incident files (alert-time fields only): {r.out_dir / 'incidents'}")
        print(f"Labels (scoring only): {r.out_dir / 'labels.json'}")
        print(f"Analysis: {r.out_dir / 'analysis.md'}")
        return 0

    def cmd_sn_replay(a) -> int:
        from .replay import run
        r, client = sn_pull(a)
        result = run(r.out_dir / "incidents", r.out_dir / "labels.json", ctx.source("runbooks"),
                     provider(ctx, a.provider), r.out_dir / "replay", ctx.gates, limits(ctx))
        print((r.out_dir / "analysis.md").read_text(encoding="utf-8"))
        print((r.out_dir / "replay" / "report.md").read_text(encoding="utf-8"))
        print("Note: ServiceNow holds tickets and change records, not metrics, logs or config diffs. Causes that "
              "need those are reported as not established; connect monitoring and the deploy pipeline to close the gap.")
        print(f"Source: {client.instance} ({client.settings.transport}). Full results: {r.out_dir}")
        return 0 if result["passed"] else 1

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

    sn = sub.add_parser("servicenow", help="Replay on past incidents read from ServiceNow (read-only)")
    snsub = sn.add_subparsers(dest="servicenow_cmd", required=True)
    for name, fn, help_ in (("pull", cmd_sn_pull, "Read closed incidents; write alert-time files, labels and an analysis"),
                            ("replay", cmd_sn_replay, "Pull, then replay the investigator and score it against the labels")):
        c = snsub.add_parser(name, help=help_)
        c.add_argument("--provider", choices=PROVIDERS, help="used for both the labeller and the investigator")
        c.add_argument("--out", help="output folder (default: <runs>/incident/servicenow/<provider>-<time>)")
        c.set_defaults(fn=fn)
