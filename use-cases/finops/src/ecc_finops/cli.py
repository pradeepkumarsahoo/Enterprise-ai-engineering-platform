# Author: Pradeep Sahoo
"""Commands for use case 5, registered under `ecc finops`.

    ecc finops analyse                                       spend, anomalies, causes, recommendations, report
    ecc finops status                                        recommendations and their savings
    ecc finops decide <REC> --by NAME --role ROLE --note TEXT [--reject]
    ecc finops implemented <REC> --by NAME --on YYYY-MM-DD [--change CHG]
    ecc finops evaluate                                      anomalies, causes and savings vs labels; gates

Thresholds and gates come from [use_cases.finops] in the product configuration; change requests
come from ServiceNow through the read-only connector.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ecc_core.plugin import Context

PROVIDERS = ["mock", "claude"]


def register(p: argparse.ArgumentParser, ctx: Context) -> None:
    from .ledger import OWNER_ROLES
    p.add_argument("--workdir", help="default: <runs>/finops")
    sub = p.add_subparsers(dest="finops_cmd", required=True)

    def workdir(a) -> Path:
        return Path(a.workdir) if a.workdir else ctx.runs

    def rules():
        from .analysis import Rules
        return Rules.from_settings(ctx.settings)

    def inputs():
        from .sources import FinOpsInputs
        return FinOpsInputs.load(ctx.servicenow(), ctx.path("finops_dir"), ctx.source("catalogue"))

    def show(res: dict) -> None:
        from .analysis import money, month_label, pct
        k = res["kpis"]
        print(f"Spend {month_label(k['last_month'])}: {money(k['total_last'])} ({pct(k['change_vs_prev'])} on "
              f"{month_label(k['prev_month'])})" + (f" · {month_label(k['partial_month'])} forecast "
                                                    f"{money(k['forecast_total'])}" if k["partial_month"] else "")
              + f" · unallocated {pct(k['unallocated_share'])}")
        for a in res["anomalies"]:
            print(f"  {a['id']}  {a['resource']} · {a['line_item']}  {', '.join(a['months'])}  "
                  f"cause: {(a['cause'] or {}).get('config') or (a['cause'] or {}).get('change') or '—'} "
                  f"({a['confidence']})")
        print(f"{'Recommendation':<38} {'Team':<22} {'Estimated':>10} {'Realised':>10}  Status")
        for x in res["recommendations"]:
            real = money(x["realised_monthly_usd"]) if x["realised_monthly_usd"] is not None else "—"
            print(f"{x['id']:<38} {x['team']:<22} {money(x['estimated_monthly_usd']):>10} {real:>10}  {x['status']}")
        s = k["savings"]
        print(f"Open estimated: {money(s['estimated_open_usd'])}/month · realised (measured): "
              f"{money(s['realised_usd'])}/month — tracked separately")

    def cmd_analyse(a) -> int:
        from . import get_drafter
        from .review import analyse
        res = analyse(inputs(), rules(), get_drafter(ctx.provider_name(a.provider), ctx.claude), workdir(a))
        show(res)
        if res["rejected_drafts"]:
            print(f"{len(res['rejected_drafts'])} drafted item(s) rejected by validation; see the report")
        print(f"Report: {workdir(a) / 'report.html'}  (open in a browser; nothing was changed in the cloud)")
        return 0

    def cmd_status(a) -> int:
        from .review import results
        show(results(workdir(a)))
        return 0

    def cmd_decide(a) -> int:
        from .ledger import decide
        from .review import find, refresh, results
        res = results(workdir(a))
        entry = decide(find(res, a.rec), workdir(a), a.by, a.role, not a.reject, a.note, res["analysis_id"])
        refresh(workdir(a))
        print(json.dumps(entry, indent=2))
        return 0

    def cmd_implemented(a) -> int:
        from .ledger import record_implemented
        from .review import find, refresh, results
        res = results(workdir(a))
        entry = record_implemented(find(res, a.rec), workdir(a), a.by, a.on, a.change or "", rules().as_of,
                                   res["analysis_id"])
        refresh(workdir(a))
        print(json.dumps(entry, indent=2))
        print("The realised saving is measured from the bill after one complete month, at the next analysis.")
        return 0

    def cmd_evaluate(a) -> int:
        from . import get_drafter
        from .review import evaluate
        labels = json.loads((ctx.path("finops_dir") / "labels.json").read_text(encoding="utf-8"))
        out = workdir(a) / "evaluation"
        result = evaluate(inputs(), rules(), get_drafter(ctx.provider_name(a.provider), ctx.claude), ctx.gates,
                          labels, out)
        (out / "evaluation.md").write_text(result["report_md"], encoding="utf-8")
        (out / "evaluation.json").write_text(json.dumps({k: v for k, v in result.items() if k != "report_md"},
                                                        indent=2), encoding="utf-8")
        print(result["report_md"])
        print(f"Full results: {out / 'evaluation.json'}")
        return 0 if result["passed"] else 1

    s = sub.add_parser("analyse", help="Spend by team, anomalies and causes, recommendations, report")
    s.add_argument("--provider", choices=PROVIDERS)
    s.set_defaults(fn=cmd_analyse)
    st = sub.add_parser("status", help="Recommendations and their estimated and realised savings")
    st.set_defaults(fn=cmd_status)
    d = sub.add_parser("decide", help="Record the owning team's decision on a recommendation")
    d.add_argument("rec")
    d.add_argument("--by", required=True)
    d.add_argument("--role", required=True, choices=list(OWNER_ROLES))
    d.add_argument("--note", required=True, help="the reason (required)")
    d.add_argument("--reject", action="store_true", help="reject instead of approve")
    d.set_defaults(fn=cmd_decide)
    im = sub.add_parser("implemented", help="Record that the owning team made an approved change")
    im.add_argument("rec")
    im.add_argument("--by", required=True)
    im.add_argument("--on", required=True, help="date the change was made, YYYY-MM-DD")
    im.add_argument("--change", help="change request number")
    im.set_defaults(fn=cmd_implemented)
    ev = sub.add_parser("evaluate", help="Score anomalies, causes and savings against labels")
    ev.add_argument("--provider", choices=PROVIDERS)
    ev.set_defaults(fn=cmd_evaluate)
