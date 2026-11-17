# Author: Pradeep Sahoo
"""Change risk report as a single HTML page, in the layout of the prototype's Change risk screen.

Built only from the assessment and the gate status, so it shows exactly what the run produced.
Static and self-contained; light and dark themes follow the viewer's system setting.
"""
from __future__ import annotations

from html import escape as e

from ecc_core.page import CSS, badge

STATUSES = {"low": ("ok", "Low"), "medium": ("warn", "Medium"), "high": ("crit", "High")}

EXTRA_CSS = """
.g-4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
.g-main { grid-template-columns:minmax(0,7fr) minmax(0,5fr); }
@media (max-width: 960px) { .g-4 { grid-template-columns:repeat(2,minmax(0,1fr)); } .g-main { grid-template-columns:minmax(0,1fr); } }
.kpi .label { color:var(--muted); font-size:12px; }
.kpi .value { display:block; font-family:var(--f-display); font-size:30px; font-weight:600; margin:2px 0; }
.kpi .delta { font-size:13px; } .kpi .src { display:block; color:var(--muted); font-size:11px; font-family:var(--f-mono); margin-top:6px; }
.up-bad { color:var(--crit); } .ok-txt { color:var(--ok); }
td.num { text-align:right; font-family:var(--f-mono); white-space:nowrap; }
.formula { font-family:var(--f-mono); font-size:12px; background:var(--surface-2); border-radius:8px; padding:8px 12px; margin:12px 0; color:var(--muted); }
.timeline { border-left:2px solid var(--line); margin:6px 0 14px 6px; padding-left:14px; }
.tl-item { margin:0 0 12px; } .tl-item b { display:block; } .tl-item p { margin:0; color:var(--muted); font-size:13px; }
.gate { border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin-top:12px; background:var(--surface-2); }
"""


def _b(kind: str, text: str | None = None) -> str:
    return badge(kind, text, STATUSES)


def report_html(d: dict, gate: dict) -> str:
    k = d["kpis"]
    kinds = k.get("files_by_kind", {})
    detail = ", ".join(f"{n} {kind}" for kind, n in sorted(kinds.items()) if kind not in ("code", "test")) or "code only"
    cov = k.get("coverage_pct")
    cov_bad = cov is not None and cov < k["coverage_gate_pct"]
    band_txt = {"high": f"High · {d['required_approvers']} approvers required",
                "medium": "Medium · 1 approver", "low": "Low · 1 approver"}[d["band"]]
    kpis = (
        f'<div class="panel kpi"><span class="label">Change risk score</span><span class="value">{d["score"]} / 10</span>'
        f'<span class="delta {"up-bad" if d["band"] != "low" else "ok-txt"}">{e(band_txt)}</span>'
        f'<span class="src">{e(d["rules_version"])}</span></div>'
        f'<div class="panel kpi"><span class="label">Files changed</span><span class="value">{k["files_changed"]}</span>'
        f'<span class="delta">incl. {e(detail)}</span><span class="src">from the pull requests</span></div>'
        f'<div class="panel kpi"><span class="label">Downstream consumers</span><span class="value">{k["consumers"]}</span>'
        f'<span class="delta {"up-bad" if k["consumers"] else ""}">{"of a changed contract" if k["consumers"] else "no contract changed"}</span>'
        f'<span class="src">from the service catalogue</span></div>'
        f'<div class="panel kpi"><span class="label">Coverage on changed lines</span>'
        f'<span class="value">{f"{cov}%" if cov is not None else "n/a"}</span>'
        f'<span class="delta {"up-bad" if cov_bad else ""}">gate is {k["coverage_gate_pct"]}%</span>'
        f'<span class="src">from CI</span></div>')

    rows = "".join(f'<tr><td>{e(f["title"])}</td><td>{e(f["signal"])}</td><td class="num">+{f["weight"]:g}</td>'
                   f'<td class="mono">{e(", ".join(f["evidence"]))}</td></tr>' for f in d["factors"]) \
        or '<tr><td colspan="4" class="sub">No risk factor fired.</td></tr>'
    unknown = "".join(f"<li>{e(u)}</li>" for u in d["could_not_establish"]) or "<li>Nothing.</li>"
    left = (f'<section class="panel"><div class="panel-h"><h2>Risk factors</h2><span class="sub">each factor links to a record</span></div>'
            f'<div class="scroll"><table><tr><th>Factor</th><th>Signal</th><th>Weight</th><th>Evidence</th></tr>{rows}</table></div>'
            f'<div class="formula">risk = Σ factor weights, capped at 10 · rules in code, weights in the product '
            f'configuration · the model never changes a weight</div>'
            + (f'<p>{e(d["summary"])}</p>' if d["summary"] else "")
            + f'<h3>Could not establish</h3><ul class="clean">{unknown}</ul></section>')

    sims = "".join(f'<div class="tl-item"><b>{e(s["change"])} → {e(s["incident"])}</b>'
                   f'<p>{e(s["ci"])} · same {e(", ".join(s["matched_on"]))}</p></div>' for s in d["similar"]) \
        or '<p class="sub">None in the incident history.</p>'
    conds = "".join(f'<li>{e(c["text"])} <span class="mono sub">{e(", ".join(c["evidence"]))}</span></li>'
                    for c in d["conditions"]) or "<li>None.</li>"
    state = gate["state"]
    gate_badge = _b("ok" if state == "approved" else "crit" if state == "rejected" else "warn", state)
    approvers = ", ".join(gate["approvers"]) or "none yet"
    right = (f'<section class="panel"><div class="panel-h"><h2>Similar past changes</h2><span class="sub">from incident history</span></div>'
             f'<div class="timeline">{sims}</div>'
             f'<div class="panel-h"><h2>Suggested release conditions</h2>{_b("accent", "Draft")}</div><ul class="clean">{conds}</ul>'
             f'<div class="gate"><div class="panel-h" style="margin:0"><h3>Release gate</h3>{gate_badge}</div>'
             f'<p class="sub" style="margin:6px 0 0">Needs {gate["required_approvers"]} approver(s) · approved by: {e(approvers)} · '
             f'requester {e(d["requested_by"])} cannot approve · assessment <span class="mono">{e(d["assessment_id"])}</span></p></div>'
             '</section>')

    ev = "".join(f'<li><b class="mono">{e(x["id"])}</b> {e(x["summary"])}</li>' for x in d["evidence"])
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Change risk · {e(d["change"])}</title>
<style>{CSS}{EXTRA_CSS}</style></head>
<body><main>
<header><div><div class="eyebrow">Change risk · pre-deploy assessment</div>
<h1>{e(d["title"])}</h1>
<p class="sub">{e(d["change"])} · {e(d["service"])} · planned {e(d["planned_start"])} UTC · requested by {e(d["requested_by"])} ·
provider <span class="mono">{e(d["provider"])}</span>. Risk factors are computed by rules from the change set, the
service catalogue, test results and incident history. The AI summarises them and suggests release conditions; it does
not set the score.</p></div>
<div class="badges">{_b(d["band"], f"Risk · {d['band']}")}{gate_badge}</div></header>
<div class="grid g-4">{kpis}</div>
<div class="grid g-main">{left}{right}</div>
<section class="panel"><h2>Evidence</h2><ul class="clean">{ev}</ul></section>
<footer>Generated by Engineering Command Centre · use case 4 · synthetic data · Author: Pradeep Sahoo</footer>
</main></body></html>
"""
