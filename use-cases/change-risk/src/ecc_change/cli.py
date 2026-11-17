# Author: Pradeep Sahoo
"""Commands for use case 4, registered under `ecc change`.

    ecc change assess [CHG ...]                    score upcoming changes (all, or the ones named)
    ecc change backtest                            score past changes as of their start vs what followed
    ecc change approve <CHG> --by NAME --role ROLE [--reject] [--note TEXT]
    ecc change status                              release gate state of every assessed change

Weights, thresholds and gates come from [use_cases.change] in the product configuration;
changes and incidents come from ServiceNow through the read-only connector.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecc_core.plugin import Context

PROVIDERS = ["mock", "claude"]


def register(p: argparse.ArgumentParser, ctx: Context) -> None:
    from .gate import RELEASE_ROLES
    p.add_argument("--workdir", help="default: <runs>/change")
    sub = p.add_subparsers(dest="change_cmd", required=True)

    def workdir(a) -> Path:
        return Path(a.workdir) if a.workdir else ctx.runs

    def rules():
        from .factors import Rules
        return Rules.from_settings(ctx.settings)

    def inputs():
        from .sources import ChangeInputs
        return ChangeInputs.load(ctx.servicenow(), ctx.path("changesets_dir"), ctx.path("calendar"),
                                 ctx.source("catalogue"), ctx.source("runbooks"))

    def cmd_assess(a) -> int:
        from . import get_drafter
        from .review import assess_changes, upcoming
        inp, r = inputs(), rules()
        numbers = a.changes or upcoming(inp, r)
        out = assess_changes(inp, numbers, r, get_drafter(ctx.provider_name(a.provider), ctx.claude), workdir(a))
        print(f"{'Change':<12} {'Service':<18} {'Score':>5}  {'Band':<7} {'Approvers':>9}  Conditions  Rejected")
        for n, d in out.items():
            print(f"{n:<12} {d['service']:<18} {d['score']:>5}  {d['band']:<7} {d['required_approvers']:>9}  "
                  f"{len(d['conditions']):>10}  {len(d['rejected_conditions']):>8}")
        print(f"Reports: {workdir(a) / 'reports'}  (open the .html files in a browser; nothing was approved or deployed)")
        return 0

    def cmd_backtest(a) -> int:
        from .review import backtest
        labels_path = ctx.path("changesets_dir").parent / "labels.json"
        labels = json.loads(labels_path.read_text(encoding="utf-8")) if labels_path.exists() else None
        result = backtest(inputs(), rules(), ctx.gates, labels)
        out = workdir(a)
        out.mkdir(parents=True, exist_ok=True)
        (out / "backtest.md").write_text(result["report_md"], encoding="utf-8")
        (out / "backtest.json").write_text(json.dumps({k: v for k, v in result.items() if k != "report_md"}, indent=2),
                                           encoding="utf-8")
        print(result["report_md"])
        print(f"Full results: {out / 'backtest.json'}")
        return 0 if result["passed"] else 1

    def cmd_approve(a) -> int:
        from .gate import decide
        from .review import assessed, render_reports
        entry = decide(assessed(workdir(a), a.change), workdir(a), a.by, a.role, not a.reject, a.note or "")
        render_reports(workdir(a), a.change)
        print(json.dumps(entry, indent=2))
        return 0

    def cmd_status(a) -> int:
        from .gate import status
        from .review import _results
        rows = _results(workdir(a))["assessments"]
        if not rows:
            print("No change has been assessed yet; run `ecc change assess`.")
            return 0
        for n, d in sorted(rows.items()):
            g = status(d, workdir(a))
            print(f"{n:<12} {d['service']:<18} {d['score']:>5} {d['band']:<7} {g['state']:<28} "
                  f"approved by: {', '.join(g['approvers']) or '—'}")
        return 0

    s = sub.add_parser("assess", help="Score changes, draft release conditions, write reports")
    s.add_argument("changes", nargs="*", help="change numbers (default: every upcoming change)")
    s.add_argument("--provider", choices=PROVIDERS)
    s.set_defaults(fn=cmd_assess)
    b = sub.add_parser("backtest", help="Score past changes as of their start and compare with what followed")
    b.set_defaults(fn=cmd_backtest)
    ap = sub.add_parser("approve", help="Record an approver's decision on the release gate")
    ap.add_argument("change")
    ap.add_argument("--by", required=True)
    ap.add_argument("--role", required=True, choices=list(RELEASE_ROLES))
    ap.add_argument("--reject", action="store_true", help="reject instead of approve")
    ap.add_argument("--note")
    ap.set_defaults(fn=cmd_approve)
    st = sub.add_parser("status", help="Release gate state of every assessed change")
    st.set_defaults(fn=cmd_status)
