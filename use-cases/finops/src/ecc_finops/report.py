# Author: Pradeep Sahoo
"""FinOps report as Markdown (use case 5). Built only from results.json, like the HTML page."""
from __future__ import annotations

from .fmt import day_label, money, month_label, pct


def report_md(d: dict) -> str:
    k, sp = d["kpis"], d["spend"]
    months = sp["months"]
    L = ["# FinOps · cloud cost by team", "",
         f"> Analysis `{d['analysis_id']}` as of {d['as_of']} · {d['rules_version']} · provider `{d['provider']}`. "
         "Allocation, anomalies, causes and savings estimates come from rules in code; the model only explains "
         "them. Nothing here changes a cloud resource.", ""]
    if d["summary"]:
        L += ["## Summary", "", d["summary"], ""]
    L += ["## Monthly spend by team (USD, amortised, net of credits)", "",
          "| Team | " + " | ".join(month_label(m) + (" (to date)" if m == sp["partial"] else "") for m in months)
          + (f" | {month_label(sp['partial'])} forecast |" if sp["partial"] else " |"),
          "|---|" + "---:|" * (len(months) + (1 if sp["partial"] else 0))]
    for team, row in sp["by_team"].items():
        L.append(f"| {team} | " + " | ".join(money(row[m]) for m in months)
                 + (f" | {money(sp['forecast'][team])} |" if sp["partial"] else " |"))
    tot = {m: sum(r[m] for r in sp["by_team"].values()) for m in months}
    L.append("| **Total** | " + " | ".join(f"**{money(tot[m])}**" for m in months)
             + (f" | **{money(k['forecast_total'])}** |" if sp["partial"] else " |"))
    L += ["", f"Forecast = month to date × {k['partial_days']} / {k['days_covered']} days (run-rate). "
          f"Unallocated in {month_label(k['last_month'])}: {money(k['unallocated_last'])} "
          f"({pct(k['unallocated_share'])}).", ""]
    if sp.get("billed"):
        L += ["Billed (invoice) per month: " + ", ".join(f"{month_label(m)} {money(sp['billed'][m])}" for m in months)
              + ". Billed and amortised differ by commitment purchases being spread over their term.", ""]
    L += [f"Cost export: `{d.get('export_format', 'focus')}`.", "", "## Anomalies", ""]
    if not d["anomalies"]:
        L += ["None flagged.", ""]
    for a in d["anomalies"]:
        o = a["points"][0]
        L += [f"### {a['id']} · {a['line_item']} on {a['resource']} ({a['team']})"
              + (" · provisional" if a["provisional"] else ""), "",
              f"- Months: {', '.join(month_label(m) for m in a['months'])}",
              f"- {month_label(o['month'])}: {money(o['value'])} vs baseline mean {money(o['mean'])} "
              f"(sd {money(o['sd'])}), z = {o['z']:.1f}, +{pct(o['ratio'])}",
              f"- Likely cause ({a['confidence']} confidence): {a['cause']['summary'] if a['cause'] else 'not established'}"]
        alerts = [x for x in d.get("daily", {}).get("alerts", []) if x["anomaly"] == a["id"]]
        L += [f"- Daily alert {x['id']}: rose on {day_label(x['start'])}, raised on {day_label(x['confirmed'])} "
              f"(the month closes {day_label(x['month_closes'])})" for x in alerts]
        if a["explanation"]:
            L.append(f"- Explanation: {a['explanation']['text']}")
        L += [f"- Could not establish: {u}" for u in a["could_not_establish"]]
        L += [f"- Evidence: {', '.join(a['evidence'])}", ""]
    daily = d.get("daily", {})
    L += ["## Daily alerts", ""]
    if not daily.get("available"):
        L += ["The cost export is not daily, so there is no daily view.", ""]
    elif not daily["alerts"]:
        L += ["None raised.", ""]
    else:
        L += ["| Alert | Series | Rose on | Raised on | Day vs mean | Monthly anomaly |", "|---|---|---|---|---:|---|"]
        L += [f"| {x['id']} | {x['line_item']} on {x['resource']} | {day_label(x['start'])} | {day_label(x['confirmed'])} | "
              f"{money(x['days'][0]['value'])} vs {money(x['days'][0]['mean'])} (+{pct(x['days'][0]['ratio'])}) | "
              f"{x['anomaly'] or 'early signal'} |" for x in daily["alerts"]]
        L += [""]
    if d.get("commitments"):
        L += ["## Reservations and savings plans", "",
              "| Commitment | Team | Covers | Ends | Used | Unused | Utilisation | Billed / amortised in window |",
              "|---|---|---|---|---:|---:|---:|---|"]
        for c in d["commitments"]:
            util = pct(c["utilisation"]) if c["utilisation"] is not None else "—"
            flags = [w for w, on in (("underused", c["underused"]), ("renewal due", c["expiring"])) if on]
            billed = money(c["billed_window"]) if c["billed_window"] is not None else "—"
            L.append(f"| {c['id']} ({c['type']}, {c['payment']}) | {c['team']} | {c['covers']} | {c['end']} "
                     f"({c['days_to_expiry']} days) | {money(c['used'])} | {money(c['unused'])} | {util}"
                     f"{' · ' + ', '.join(flags) if flags else ''} | {billed} / {money(c['amortised_window'])} |")
        L += ["", f"Used and unused are for {month_label(d['commitments'][0]['month'])}, from the cost export.", ""]
    L += ["## Recommendations", "",
          "Estimated savings come from the formula shown; realised savings are measured from the bill after at "
          "least one complete month. The two columns are never added together.", "",
          "| Recommendation | Team | Type | Est. monthly saving | Realised (measured) | Status | Evidence |",
          "|---|---|---|---:|---:|---|---|"]
    for x in d["recommendations"]:
        real = money(x["realised_monthly_usd"]) if x["realised_monthly_usd"] is not None else "—"
        L.append(f"| {x['title']} (`{x['id']}`) | {x['team']} | {x['type']} | {money(x['estimated_monthly_usd'])}"
                 f"{' (provisional)' if x['provisional'] else ''} | {real} | {x['status']} | {', '.join(x['evidence'])} |")
    s = k["savings"]
    L += [f"| **Open** ({s['open']}) | | | **{money(s['estimated_open_usd'])}** | | | |",
          f"| **Implemented, measured** ({s['measured']}) | | | {money(s['estimated_implemented_usd'])} at approval | "
          f"**{money(s['realised_usd'])}** | | |", ""]
    L += [f"- `{x['id']}`: {x['formula']}" + (f"; realised: {x['realised_note']}" if x["realised_note"] else "")
          + (f"; {x['decision_note']}" if x["decision_note"] else "") for x in d["recommendations"]]
    drafted = [x for x in d["recommendations"] if x.get("note")]
    if drafted:
        L += ["", "### Notes to owning teams (draft)", ""] + [f"- **{x['id']}**: {x['note']['text']}" for x in drafted]
    if d["rejected_drafts"]:
        L += ["", "Drafts rejected by validation:", ""] + [f"- {x['item']}: {x['reason']}" for x in d["rejected_drafts"]]
    L += ["", "## Could not establish", ""] + ([f"- {u}" for u in d["could_not_establish"]] or ["- nothing"])
    L += ["", "## Evidence", ""]
    L += [f"- **{e['id']}** {e['summary']}" + (f" _[{', '.join(e['flags'])}]_" if e["flags"] else "")
          for e in d["evidence"]]
    L += ["", "_Generated by Engineering Command Centre · use case 5 · synthetic data · Author: Pradeep Sahoo_", ""]
    return "\n".join(L)
