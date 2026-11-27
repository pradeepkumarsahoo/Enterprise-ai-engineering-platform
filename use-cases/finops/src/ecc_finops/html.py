# Author: Pradeep Sahoo
"""FinOps report as a single HTML page, in the layout of the prototype's FinOps screen.

Built only from results.json, so it shows exactly what the run produced. Static and
self-contained (inline SVG, no script); light and dark themes follow the viewer's system setting.

Chart: monthly spend by team as stacked columns. Teams keep a fixed colour slot (colour follows
the team, never its rank); unallocated spend is neutral grey. The partial month is drawn as its
forecast, faded and outlined, and labelled. Every segment has a hover tooltip, and the same
numbers are in the table under the chart.
"""
from __future__ import annotations

from html import escape as e

from ecc_core.page import CSS, badge

from .fmt import money, month_label, pct
from .spend import UNALLOCATED

STATUSES = {"proposed": ("blue", "Proposed"), "approved": ("warn", "Approved"), "implemented": ("ok", "Implemented"),
            "rejected": ("crit", "Rejected"), "suppressed": ("neutral", "Suppressed"),
            "high": ("crit", "High"), "medium": ("warn", "Medium"), "low": ("neutral", "Low"),
            "not established": ("neutral", "Not established")}

# categorical slots (validated reference palette, adjacent pairs), light and dark steps
SLOTS = (("#2a78d6", "#3987e5"), ("#eb6834", "#d95926"), ("#1baf7a", "#199e70"), ("#eda100", "#c98500"))
GREY = ("#A3A9B3", "#5B6880")

EXTRA_CSS = """
.g-5 { grid-template-columns:repeat(5,minmax(0,1fr)); }
.g-main { grid-template-columns:minmax(0,7fr) minmax(0,5fr); }
@media (max-width: 1100px) { .g-5 { grid-template-columns:repeat(2,minmax(0,1fr)); } .g-main { grid-template-columns:minmax(0,1fr); } }
.kpi .label { color:var(--muted); font-size:12px; }
.kpi .value { display:block; font-family:var(--f-display); font-size:28px; font-weight:600; margin:2px 0; }
.kpi .delta { font-size:13px; } .kpi .src { display:block; color:var(--muted); font-size:11px; font-family:var(--f-mono); margin-top:6px; }
.up-bad { color:var(--crit); } .ok-txt { color:var(--ok); }
td.num, th.num { text-align:right; font-family:var(--f-mono); white-space:nowrap; }
tr.total td { font-weight:600; border-top:1px solid var(--line); }
.formula { font-family:var(--f-mono); font-size:12px; background:var(--surface-2); border-radius:8px; padding:8px 12px; margin:12px 0; color:var(--muted); }
.legend { display:flex; flex-wrap:wrap; gap:6px 14px; font-size:12px; color:var(--muted); margin:2px 0 6px; }
.legend i { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:-1px; }
.legend i.fc { background:transparent !important; border:1.5px dashed var(--muted); }
.viz { --s1:#2a78d6; --s2:#eb6834; --s3:#1baf7a; --s4:#eda100; --s0:#A3A9B3; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .viz { --s1:#3987e5; --s2:#d95926; --s3:#199e70; --s4:#c98500; --s0:#5B6880; } }
svg.chart { width:100%; height:auto; display:block; }
svg.chart text { font-family:var(--f-mono); font-size:11px; fill:var(--muted); }
svg.chart text.val { fill:var(--ink); font-weight:600; }
svg.chart .grid { stroke:var(--line); stroke-width:1; }
svg.chart .seg:hover { opacity:.8; }
svg.chart .fc { opacity:.45; }
svg.chart .fc-outline { fill:none; stroke:var(--muted); stroke-dasharray:4 3; stroke-width:1.5; }
.anomaly { border-top:1px solid var(--line); padding:12px 0; } .anomaly:first-of-type { border-top:0; padding-top:0; }
.anomaly p { margin:6px 0; }
.spark rect.base { fill:var(--muted); opacity:.45; } .spark rect.hit { fill:var(--crit); }
.spark line { stroke:var(--muted); stroke-dasharray:3 3; stroke-width:1; }
.spark text { font-family:var(--f-mono); font-size:10px; fill:var(--muted); }
details summary { cursor:pointer; color:var(--muted); font-size:12px; margin-top:8px; }
"""


def _b(kind: str, text: str | None = None) -> str:
    return badge(kind, text, STATUSES)


def _colour(team: str, teams: list[str]) -> str:
    if team == UNALLOCATED:
        return "var(--s0)"
    named = [t for t in teams if t != UNALLOCATED]
    i = named.index(team)
    return f"var(--s{i + 1})" if i < len(SLOTS) else "var(--s0)"


def _top_rounded(x: float, y: float, w: float, h: float, r: float = 4) -> str:
    r = min(r, h, w / 2)
    return (f"M{x:.1f},{y + h:.1f} V{y + r:.1f} Q{x:.1f},{y:.1f} {x + r:.1f},{y:.1f} H{x + w - r:.1f} "
            f"Q{x + w:.1f},{y:.1f} {x + w:.1f},{y + r:.1f} V{y + h:.1f} Z")


def _nice_max(v: float) -> tuple[float, float]:
    for step in (10_000, 20_000, 25_000, 50_000, 100_000, 200_000, 250_000, 500_000, 1_000_000):
        if v / step <= 5:
            top = step * (int(v // step) + 1)
            return top, step
    return v, v / 4


def spend_chart(sp: dict, kpis: dict) -> str:
    teams = list(sp["by_team"])
    months = sp["months"]
    cols = [(m, False) for m in months if m != sp["partial"]] + ([(sp["partial"], True)] if sp["partial"] else [])
    value = lambda t, m, fc: max(sp["forecast"][t] if fc else sp["by_team"][t][m], 0.0)
    totals = [sum(value(t, m, fc) for t in teams) for m, fc in cols]
    W, H, L, R, T, B = 680, 260, 56, 8, 22, 26
    top, step = _nice_max(max(totals) * 1.08)
    pw, ph = W - L - R, H - T - B
    slot = pw / len(cols)
    bw = min(34.0, slot * 0.62)
    y = lambda v: T + ph - v / top * ph
    out = [f'<svg class="chart" viewBox="0 0 {W} {H}" role="img" aria-label="Monthly spend by team, stacked columns">']
    tick = 0.0
    while tick <= top + 1:
        out.append(f'<line class="grid" x1="{L}" x2="{W - R}" y1="{y(tick):.1f}" y2="{y(tick):.1f}"/>'
                   f'<text x="{L - 6}" y="{y(tick) + 4:.1f}" text-anchor="end">${tick / 1000:,.0f}k</text>')
        tick += step
    last_complete = max((i for i, (m, fc) in enumerate(cols) if not fc), default=None)
    for i, (m, fc) in enumerate(cols):
        x = L + i * slot + (slot - bw) / 2
        base = 0.0
        visible = [t for t in teams if value(t, m, fc) > 0]
        for j, t in enumerate(visible):
            v = value(t, m, fc)
            y0, y1 = y(base + v), y(base)
            h = max(y1 - y0 - (2 if j < len(visible) - 1 else 0), 0.5)      # 2px surface gap between segments
            label = f"{t} · {month_label(m)}{' forecast' if fc else ''}: {money(v)}"
            shape = (f'<path d="{_top_rounded(x, y0, bw, h)}"' if j == len(visible) - 1
                     else f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{h:.1f}"')
            out.append(f'{shape} class="seg{" fc" if fc else ""}" style="fill:{_colour(t, teams)}">'
                       f'<title>{e(label)}</title>{"</path>" if j == len(visible) - 1 else "</rect>"}')
            base += v
        if fc:
            out.append(f'<path class="fc-outline" d="{_top_rounded(x, y(base), bw, y(0) - y(base))}"/>')
        out.append(f'<text x="{x + bw / 2:.1f}" y="{H - 8}" text-anchor="middle">'
                   f'{month_label(m)[:3]}{"*" if fc else ""}</text>')
        if fc or i == last_complete:
            out.append(f'<text class="val" x="{x + bw / 2:.1f}" y="{y(base) - 6:.1f}" text-anchor="middle">'
                       f'${base / 1000:,.0f}k</text>')
    out.append("</svg>")
    legend = "".join(f'<span><i style="background:{_colour(t, teams)}"></i>{e(t)}</span>' for t in teams)
    if sp["partial"]:
        legend += (f'<span><i class="fc"></i>* {e(month_label(sp["partial"]))} forecast: run-rate from '
                   f'{kpis["days_covered"]} of {kpis["partial_days"]} days</span>')
    return f'<div class="viz"><div class="legend">{legend}</div>{"".join(out)}</div>'


def spend_table(sp: dict, kpis: dict) -> str:
    months = sp["months"]
    head = "".join(f'<th class="num">{e(month_label(m)[:3])}{"*" if m == sp["partial"] else ""}</th>' for m in months)
    head += '<th class="num">Fcst*</th>' if sp["partial"] else ""
    rows = ""
    for t, row in sp["by_team"].items():
        rows += (f"<tr><td>{e(t)}</td>" + "".join(f'<td class="num">{money(row[m])}</td>' for m in months)
                 + (f'<td class="num">{money(sp["forecast"][t])}</td>' if sp["partial"] else "") + "</tr>")
    tot = {m: sum(r[m] for r in sp["by_team"].values()) for m in months}
    rows += ('<tr class="total"><td>Total</td>' + "".join(f'<td class="num">{money(tot[m])}</td>' for m in months)
             + (f'<td class="num">{money(kpis["forecast_total"])}</td>' if sp["partial"] else "") + "</tr>")
    note = f"* {month_label(sp['partial'])} is month to date; Fcst is its run-rate forecast." if sp["partial"] else ""
    return (f'<details open><summary>Table view (USD, net of credits)</summary><div class="scroll"><table>'
            f'<tr><th>Team</th>{head}</tr>{rows}</table></div><p class="sub mono">{e(note)}</p></details>')


def sparkline(a: dict) -> str:
    hist = a["history"]
    months = sorted(hist)
    W, H, pad = 520, 84, 16
    top = max(hist.values()) * 1.1 or 1
    bw = (W - 8) / len(months)
    mean = a["points"][0]["mean"]
    yv = lambda v: H - pad - v / top * (H - pad - 6)
    out = [f'<svg class="spark" viewBox="0 0 {W} {H}" style="width:100%;max-width:{W}px;height:auto" role="img" '
           f'aria-label="{e(a["line_item"])} on {e(a["resource"])} by month">']
    for i, m in enumerate(months):
        v = hist[m]
        hit = m in a["months"]
        out.append(f'<rect class="{"hit" if hit else "base"}" x="{4 + i * bw + 2:.1f}" y="{yv(v):.1f}" '
                   f'width="{bw - 4:.1f}" height="{H - pad - yv(v):.1f}" rx="2"><title>{e(month_label(m))}: '
                   f'{money(v)}{" (run-rate)" if m == max(months) and a["provisional"] else ""}'
                   f'{" · flagged" if hit else ""}</title></rect>')
        if i in (0, len(months) - 1):
            out.append(f'<text x="{4 + i * bw + bw / 2:.1f}" y="{H - 2}" text-anchor="middle">'
                       f'{e(month_label(m)[:3])}</text>')
    out.append(f'<line x1="4" x2="{W - 4}" y1="{yv(mean):.1f}" y2="{yv(mean):.1f}"><title>baseline mean '
               f'{money(mean)}</title></line></svg>')
    return "".join(out)


def report_html(d: dict) -> str:
    k, sp, s, r = d["kpis"], d["spend"], d["kpis"]["savings"], d["rules"]
    up = k["change_vs_prev"] >= 0
    kpis = (
        f'<div class="panel kpi"><span class="label">Spend · {e(month_label(k["last_month"]))}</span>'
        f'<span class="value">{money(k["total_last"])}</span>'
        f'<span class="delta {"up-bad" if up else "ok-txt"}">{"▲" if up else "▼"} {pct(abs(k["change_vs_prev"]))} on '
        f'{e(month_label(k["prev_month"])) if k["prev_month"] else "—"}</span><span class="src">cost export, net of credits</span></div>'
        + (f'<div class="panel kpi"><span class="label">Forecast · {e(month_label(k["partial_month"]))}</span>'
           f'<span class="value">{money(k["forecast_total"])}</span>'
           f'<span class="delta">run-rate from {k["days_covered"]} of {k["partial_days"]} days</span>'
           f'<span class="src">month to date × days in month</span></div>' if k["partial_month"] else "")
        + f'<div class="panel kpi"><span class="label">Unallocated · {e(month_label(k["last_month"]))}</span>'
        f'<span class="value">{pct(k["unallocated_share"])}</span>'
        f'<span class="delta {"up-bad" if k["unallocated_share"] else ""}">{money(k["unallocated_last"])} with no owner</span>'
        f'<span class="src">no team tag, no catalogue owner</span></div>'
        f'<div class="panel kpi"><span class="label">Estimated savings · open</span>'
        f'<span class="value">{money(s["estimated_open_usd"])}</span>'
        f'<span class="delta">a month · {s["open"]} recommendation(s)</span><span class="src">formula per recommendation</span></div>'
        f'<div class="panel kpi"><span class="label">Realised savings · measured</span>'
        f'<span class="value">{money(s["realised_usd"])}</span>'
        f'<span class="delta">a month · {s["measured"]} implemented, {money(s["estimated_implemented_usd"])} estimated</span>'
        f'<span class="src">from the bill, never typed in</span></div>')

    left = (f'<section class="panel"><div class="panel-h"><h2>Monthly spend</h2><span class="sub mono">USD · by team · '
            f'synthetic</span></div>{spend_chart(sp, k)}{spend_table(sp, k)}'
            + (f'<p>{e(d["summary"])}</p>' if d["summary"] else "") + "</section>")

    cards = ""
    for a in d["anomalies"]:
        o = a["points"][0]
        cause = a["cause"]["summary"] if a["cause"] else "Not established."
        expl = f'<p>{e(a["explanation"]["text"])}</p>' if a["explanation"] else ""
        unknown = "".join(f"<li>{e(u)}</li>" for u in a["could_not_establish"])
        cards += (f'<div class="anomaly"><div class="panel-h" style="margin:0"><h3>{e(a["id"])} · {e(a["line_item"])} on '
                  f'{e(a["resource"])}</h3>{_b("crit", "Provisional" if o["provisional"] else "Flagged")}</div>'
                  f'<p><b>{e(a["team"])}: up {pct(o["ratio"])} in {e(month_label(o["month"]))}</b>'
                  + (f' · continuing in {e(", ".join(month_label(m) for m in a["months"][1:]))}' if len(a["months"]) > 1 else "")
                  + f'</p><p class="sub">{money(o["value"])}{" run-rate" if o["provisional"] else ""} against a {len(o["baseline"])}-month mean of {money(o["mean"])}: '
                  f'z = {o["z"]:.1f} standard deviations. Rule: z ≥ {r["z_threshold"]:g}, increase ≥ {money(r["min_increase_usd"])} '
                  f'and ≥ {pct(r["min_increase_ratio"])}.</p>'
                  f'{sparkline(a)}'
                  f'<p class="note">Likely cause: {e(cause)} · confidence {_b(a["confidence"])}</p>{expl}'
                  + (f'<h3 style="margin-top:8px">Could not establish</h3><ul class="clean">{unknown}</ul>' if unknown else "")
                  + f'<p class="mono sub">evidence {e(", ".join(a["evidence"]))}</p></div>')
    flagged = _b("crit" if d["anomalies"] else "ok", f"{len(d['anomalies'])} flagged")
    right = (f'<section class="panel"><div class="panel-h"><h2>Anomalies</h2>{flagged}</div>'
             f'{cards or "<p class=sub>None flagged.</p>"}</section>')

    rows = ""
    for x in d["recommendations"]:
        real = money(x["realised_monthly_usd"]) if x["realised_monthly_usd"] is not None else "—"
        real_t = x["realised_note"] or ("measured after one complete month" if x["status"] == "implemented" else "")
        rows += (f'<tr><td>{e(x["title"])}<div class="mono sub">{e(x["id"])} · {e(x["formula"])}</div>'
                 + (f'<div class="sub">{e(x["decision_note"])}</div>' if x["decision_note"] else "")
                 + f'</td><td>{e(x["team"])}</td><td>{e(x["type"])}</td>'
                 f'<td class="num">{money(x["estimated_monthly_usd"])}{" †" if x["provisional"] else ""}</td>'
                 f'<td class="num" title="{e(real_t)}">{real}</td><td>{_b(x["status"])}</td>'
                 f'<td class="mono">{e(", ".join(x["evidence"]))}</td></tr>')
    rows += (f'<tr class="total"><td>Open ({s["open"]})</td><td></td><td></td><td class="num">{money(s["estimated_open_usd"])}</td>'
             f'<td class="num">—</td><td></td><td></td></tr>'
             f'<tr class="total"><td>Implemented and measured ({s["measured"]})</td><td></td><td></td>'
             f'<td class="num">{money(s["estimated_implemented_usd"])}</td><td class="num">{money(s["realised_usd"])}</td>'
             f'<td></td><td></td></tr>')
    notes = "".join(f'<li><b class="mono">{e(x["id"])}</b> {e(x["note"]["text"])}</li>'
                    for x in d["recommendations"] if x.get("note"))
    rejected = "".join(f"<li>{e(x['item'])}: {e(x['reason'])}</li>" for x in d["rejected_drafts"])
    recs = (f'<section class="panel"><div class="panel-h"><h2>Recommendations</h2><span class="sub">no automated changes '
            f'to cloud resources · the owning team decides</span></div>'
            f'<div class="scroll"><table><tr><th>Recommendation</th><th>Team</th><th>Type</th>'
            f'<th class="num">Est. monthly saving</th><th class="num">Realised (measured)</th><th>Status</th>'
            f'<th>Evidence</th></tr>{rows}</table></div>'
            f'<div class="formula">estimated = formula in code, frozen at approval · realised = mean cost over the {r["realised_baseline_months"]} '
            f'complete months before implementation − mean cost over the complete months since · the two are never '
            f'added together · † provisional: from a part-month run-rate</div>'
            + (f'<h3>Notes to owning teams</h3>{_b("accent", "Draft")}<ul class="clean">{notes}</ul>' if notes else "")
            + (f'<h3 style="margin-top:10px">Drafts rejected by validation</h3><ul class="clean">{rejected}</ul>' if rejected else "")
            + "</section>")

    unknown = "".join(f"<li>{e(u)}</li>" for u in d["could_not_establish"]) or "<li>Nothing.</li>"
    ev = "".join(f'<li><b class="mono">{e(x["id"])}</b> {e(x["summary"])}'
                 + "".join(f" {_b('warn', f)}" for f in x["flags"]) + "</li>" for x in d["evidence"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>FinOps · cloud cost by team</title>
<style>{CSS}{EXTRA_CSS}</style></head>
<body><main>
<header><div><div class="eyebrow">FinOps · cloud cost by team</div>
<h1>Cloud cost by team</h1>
<p class="sub">Analysis <span class="mono">{e(d["analysis_id"])}</span> as of {e(d["as_of"])} · {e(d["rules_version"])} ·
provider <span class="mono">{e(d["provider"])}</span>. From the cost export. Allocation, anomalies, likely causes and
savings estimates are computed by rules; the AI explains them and drafts notes to owning teams. Estimated and realised
savings are tracked separately, and nothing here changes a cloud resource.</p></div>
<div class="badges">{_b("neutral", "Synthetic cost export")}{_b("crit" if d["anomalies"] else "ok", f"{len(d['anomalies'])} anomalies")}</div></header>
<div class="grid g-5">{kpis}</div>
<div class="grid g-main">{left}{right}</div>
{recs}
<div class="grid g-two" style="margin-top:16px">
<section class="panel"><h2>Could not establish</h2><ul class="clean">{unknown}</ul></section>
<section class="panel"><h2>Evidence</h2><ul class="clean">{ev}</ul></section></div>
<footer>Generated by Engineering Command Centre · use case 5 · synthetic data · Author: Pradeep Sahoo</footer>
</main></body></html>
"""
