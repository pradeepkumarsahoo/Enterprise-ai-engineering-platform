# Author: Pradeep Sahoo
"""Commands for use case 5, registered under `ecc finops`.

    ecc finops analyse                                       spend, anomalies, causes, recommendations, report
    ecc finops status                                        recommendations and their savings
    ecc finops decide <REC> --by NAME [--role ROLE] --note TEXT [--reject]
    ecc finops implemented <REC> --by NAME --on YYYY-MM-DD [--change CHG]
    ecc finops evaluate                                      anomalies, causes and savings vs labels; gates
    ecc finops tags check                                    tagging agent: check every resource, propose fixes
    ecc finops tags decide <TAG> --by NAME --note TEXT [--reject]   the owning team decides a proposal
    ecc finops tags status | tags plan | tags evaluate
    ecc finops dashboard                                     cost by team, customisable (runs/finops/dashboard.html)

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
        from .rules import Rules
        return Rules.from_settings(ctx.settings)

    def inputs():
        from .sources import FinOpsInputs
        r = rules()
        return FinOpsInputs.load(ctx.servicenow(), ctx.path("finops_dir"), ctx.source("catalogue"),
                                 ctx.source("team_directory"), r.cost_export_file, r.cost_export_format)

    def directory() -> dict:
        from .sources import _json
        return _json(ctx.source("team_directory"))

    def show(res: dict) -> None:
        from .fmt import money, month_label, pct
        k = res["kpis"]
        print(f"Spend {month_label(k['last_month'])}: {money(k['total_last'])} ({pct(k['change_vs_prev'])} on "
              f"{month_label(k['prev_month'])})" + (f" · {month_label(k['partial_month'])} forecast "
                                                    f"{money(k['forecast_total'])}" if k["partial_month"] else "")
              + f" · unallocated {pct(k['unallocated_share'])}")
        for a in res["anomalies"]:
            print(f"  {a['id']}  {a['resource']} · {a['line_item']}  {', '.join(a['months'])}  "
                  f"cause: {(a['cause'] or {}).get('config') or (a['cause'] or {}).get('change') or '—'} "
                  f"({a['confidence']})" + (f"  daily: {', '.join(a['daily'])}" if a.get("daily") else ""))
        for x in res.get("daily", {}).get("alerts", []):
            print(f"  {x['id']}  {x['resource']} · {x['line_item']}  from {x['start']}, raised {x['confirmed']}"
                  f"  -> {x['anomaly'] or 'early signal'}")
        for c in res.get("commitments", []):
            util = pct(c["utilisation"]) if c["utilisation"] is not None else "—"
            print(f"  {c['id']}  {c['team']}  utilisation {util}  ends {c['end']} ({c['days_to_expiry']} days)"
                  + ("  UNDERUSED" if c["underused"] else "") + ("  RENEWAL DUE" if c["expiring"] else ""))
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
        entry = decide(find(res, a.rec), workdir(a), a.by, a.role, not a.reject, a.note, res["analysis_id"],
                       directory())
        refresh(workdir(a))
        print(json.dumps(entry, indent=2))
        return 0

    def cmd_implemented(a) -> int:
        from .ledger import record_implemented
        from .review import find, refresh, results
        res = results(workdir(a))
        entry = record_implemented(find(res, a.rec), workdir(a), a.by, a.on, a.change or "", rules().as_of,
                                   res["analysis_id"], directory())
        refresh(workdir(a))
        print(json.dumps(entry, indent=2))
        print("The realised saving is measured from the bill after one complete month, at the next analysis.")
        return 0

    def cmd_evaluate(a) -> int:
        from . import get_drafter
        from .evaluation import evaluate
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

    def inventory():
        from .inventory import read_inventory
        return read_inventory(ctx.path("finops_dir") / "inventory.json")

    def show_tags(run: dict) -> None:
        from .fmt import money, month_label
        k = run["kpis"]
        print(f"{k['resources']} resources checked · {k['compliant']} compliant · {k['proposals']} proposals "
              f"({k['waiting']} waiting, {k['needs_owner']} need an owner, {k['approved']} approved, "
              f"{k['rejected']} rejected)")
        print(f"{'Proposal':<30} {'Set':<46} {'Approver':<22} {'Cost/mo':>9}  Status")
        for p in run["proposals"]:
            tags = ", ".join(f"{a}={b}" for a, b in p["set"].items()) + (f" -{','.join(p['remove'])}" if p["remove"] else "")
            cost = money(p["monthly_cost"]) if p["monthly_cost"] is not None else "—"
            print(f"{p['id']:<30} {tags:<46} {p['team'] or '—':<22} {cost:>9}  {p['status']}")
        print(f"Unallocated in {month_label(k['month'])}: {money(k['unallocated_now'])}; approving the proposals "
              f"would allocate {money(k['unallocated_fixed_by_proposals'])}. Nothing was tagged: teams apply "
              "approved tags themselves.")

    def cmd_tags(a) -> int:
        from . import get_tag_drafter
        from . import tagging as T
        if a.tags_cmd == "check":
            run = T.check(inventory(), inputs(), get_tag_drafter(ctx.provider_name(a.provider), ctx.claude), workdir(a))
            show_tags(run)
            print(f"Report: {workdir(a) / 'tags' / 'tagging-report.md'}")
        elif a.tags_cmd == "status":
            show_tags(T.results(workdir(a)))
        elif a.tags_cmd == "decide":
            run = T.results(workdir(a))
            entry = T.decide(T.find(run, a.proposal), workdir(a) / "tags", a.by, a.role, not a.reject, a.note,
                             run["run_id"], directory())
            T.refresh(workdir(a))
            print(json.dumps(entry, indent=2))
        elif a.tags_cmd == "plan":
            run = T.refresh(workdir(a))
            approved = [p for p in run["proposals"] if p["status"] == "approved"]
            print((workdir(a) / "tags" / "tagging-plan.sh").read_text(encoding="utf-8"))
            print(f"{len(approved)} approved proposal(s). This plan is NOT run here: the owning team runs it through "
                  "its own change process.")
        elif a.tags_cmd == "evaluate":
            from ecc_core.audit import AuditLog
            labels = json.loads((ctx.path("finops_dir") / "tagging_labels.json").read_text(encoding="utf-8"))
            run = T.check(inventory(), inputs(), get_tag_drafter(ctx.provider_name(a.provider), ctx.claude), workdir(a))
            m = T.evaluate_tags(run, labels, AuditLog(workdir(a) / "tags" / "audit.jsonl").entries())
            m["rejected_drafts"] = len(run["rejected_drafts"])
            ok = (m["tag_precision"] >= ctx.gates["tag_precision_min"] and m["tag_recall"] >= ctx.gates["tag_recall_min"]
                  and m["cloud_changes"] <= ctx.gates["cloud_changes_max"]
                  and m["rejected_drafts"] <= ctx.gates["rejected_drafts_max"])
            print(json.dumps({**m, "passed": ok}, indent=2))
            return 0 if ok else 1
        return 0

    def cmd_dashboard(a) -> int:
        from .dashboard import dashboard_data, dashboard_html
        from .sources import _json
        from . import tagging as T
        try:
            run = T.refresh(workdir(a))
        except ValueError:
            run = None
            print("No tagging check yet: the dashboard shows today's tags only (run `ecc finops tags check`).")
        budgets_path = ctx.path("finops_dir") / "budgets.json"
        budgets = _json(budgets_path) if budgets_path.exists() else {}
        out = workdir(a) / "dashboard.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(dashboard_html(dashboard_data(inputs(), rules(), run, budgets)), encoding="utf-8")
        print(f"Dashboard: {out}  (open in a browser)")
        return 0

    s = sub.add_parser("analyse", help="Spend by team, anomalies and causes, recommendations, report")
    s.add_argument("--provider", choices=PROVIDERS)
    s.set_defaults(fn=cmd_analyse)
    st = sub.add_parser("status", help="Recommendations and their estimated and realised savings")
    st.set_defaults(fn=cmd_status)
    d = sub.add_parser("decide", help="Record the owning team's decision on a recommendation")
    d.add_argument("rec")
    d.add_argument("--by", required=True)
    d.add_argument("--role", choices=list(OWNER_ROLES), help="optional; must match the team directory")
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
    tg = sub.add_parser("tags", help="Tagging agent: check every resource and propose tag fixes (never applies them)")
    tsub = tg.add_subparsers(dest="tags_cmd", required=True)
    for name, text in (("check", "Check every resource against the tag policy and propose fixes"),
                       ("evaluate", "Score the proposals against labels")):
        x = tsub.add_parser(name, help=text)
        x.add_argument("--provider", choices=PROVIDERS)
        x.set_defaults(fn=cmd_tags)
    tsub.add_parser("status", help="Proposals and their status").set_defaults(fn=cmd_tags)
    tsub.add_parser("plan", help="Print the approved tagging plan (for the team to run)").set_defaults(fn=cmd_tags)
    td = tsub.add_parser("decide", help="The owning team approves or rejects a tag proposal")
    td.add_argument("proposal")
    td.add_argument("--by", required=True)
    td.add_argument("--role", choices=list(OWNER_ROLES), help="optional; must match the team directory")
    td.add_argument("--note", required=True)
    td.add_argument("--reject", action="store_true")
    td.set_defaults(fn=cmd_tags)
    db = sub.add_parser("dashboard", help="Cost by team, customisable: runs/finops/dashboard.html")
    db.set_defaults(fn=cmd_dashboard)
