# Author: Pradeep Sahoo
"""Proposal pack as a single HTML page: requirement document in, architecture out.

Written by every `architecture run` next to the Markdown pack. It is built only
from the run's results, so the page shows exactly what the pipeline produced:
the extracted requirement and its validation, the container diagram (Mermaid,
drawn in code), the option comparison, the ADR draft, NFR traceability, stories
and open questions.

The page is static and self-contained apart from the Mermaid renderer, loaded
from a pinned CDN version. Without network access the diagram's Mermaid source
is shown instead. Light and dark themes follow the viewer's system setting.
"""
from __future__ import annotations

from html import escape

MERMAID_ESM = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs"
BADGE = {"meets": ("ok", "Meets"), "at_risk": ("warn", "At risk"), "fails": ("crit", "Fails"),
         "unknown": ("neutral", "Unknown"), "preferred": ("ok", "Preferred"), "viable": ("blue", "Viable"),
         "rejected": ("crit", "Rejected"), "traced": ("ok", "Traced"), "gap": ("warn", "Gap")}

CSS = """
:root { --bg:#F3F4F0; --surface:#FCFCFA; --surface-2:#ECEFEA; --ink:#0F1B2D; --muted:#56637A; --line:#DCE0E3;
  --accent:#B4481A; --accent-soft:#F8E3D6; --blue:#2A5DB0; --blue-soft:#E1E9F7; --ok:#2E7D4F; --ok-soft:#DDF0E4;
  --warn:#9A6200; --warn-soft:#F6EAD0; --crit:#B42318; --crit-soft:#F8DEDA;
  --shadow:0 1px 2px rgba(15,27,45,.06),0 4px 16px rgba(15,27,45,.05);
  --f-display:'Space Grotesk','Segoe UI',Arial,sans-serif; --f-body:'IBM Plex Sans','Segoe UI',Arial,sans-serif;
  --f-mono:'JetBrains Mono',Consolas,'Courier New',monospace; color-scheme: light; }
@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) {
  --bg:#0B1422; --surface:#111C2D; --surface-2:#172438; --ink:#E8ECF1; --muted:#98A6BA; --line:#24344C;
  --accent:#F08A4B; --accent-soft:#3A2416; --blue:#7AA5F2; --blue-soft:#1B2B47; --ok:#5BC48A; --ok-soft:#14301F;
  --warn:#E3AA45; --warn-soft:#33270F; --crit:#F27D73; --crit-soft:#3A1714; --shadow:0 1px 2px rgba(0,0,0,.3);
  color-scheme: dark; } }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font-family:var(--f-body); font-size:14px; line-height:1.5; }
main { max-width:1440px; margin:0 auto; padding:24px 24px 48px; }
h1,h2,h3 { font-family:var(--f-display); margin:0; letter-spacing:-0.01em; }
h1 { font-size:28px; } h2 { font-size:16px; } h3 { font-size:14px; }
.eyebrow { font-family:var(--f-mono); font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--accent); }
.sub { color:var(--muted); } .mono { font-family:var(--f-mono); font-size:12px; }
header { display:flex; justify-content:space-between; gap:16px; align-items:flex-end; flex-wrap:wrap; margin-bottom:20px; }
header p { margin:6px 0 0; max-width:760px; }
.badges { display:flex; gap:8px; flex-wrap:wrap; }
.badge { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:600; white-space:nowrap; }
.b-ok { background:var(--ok-soft); color:var(--ok); } .b-warn { background:var(--warn-soft); color:var(--warn); }
.b-crit { background:var(--crit-soft); color:var(--crit); } .b-blue { background:var(--blue-soft); color:var(--blue); }
.b-neutral { background:var(--surface-2); color:var(--muted); } .b-accent { background:var(--accent-soft); color:var(--accent); }
.grid { display:grid; gap:16px; margin-bottom:16px; }
.g-flow { grid-template-columns:minmax(0,4fr) auto minmax(0,8fr); align-items:stretch; }
.g-two { grid-template-columns:minmax(0,7fr) minmax(0,5fr); }
@media (max-width: 960px) { .g-flow, .g-two { grid-template-columns:minmax(0,1fr); } .arrow { transform:rotate(90deg); } }
.panel { background:var(--surface); border:1px solid var(--line); border-radius:12px; box-shadow:var(--shadow); padding:16px 18px; min-width:0; }
.panel-h { display:flex; justify-content:space-between; align-items:baseline; gap:12px; margin-bottom:10px; }
.arrow { align-self:center; color:var(--accent); font-size:28px; font-family:var(--f-display); text-align:center; }
.arrow small { display:block; font-size:11px; color:var(--muted); font-family:var(--f-mono); }
.stats { display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:8px; margin:10px 0 12px; }
.stat { background:var(--surface-2); border-radius:8px; padding:8px 10px; }
.stat b { display:block; font-family:var(--f-display); font-size:20px; }
.stat span { font-size:12px; color:var(--muted); }
table { width:100%; border-collapse:collapse; }
th { text-align:left; font-size:11px; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); font-weight:600; padding:6px 8px; border-bottom:1px solid var(--line); }
td { padding:6px 8px; border-bottom:1px solid var(--line); vertical-align:top; }
tr:last-child td { border-bottom:0; }
.scroll { overflow-x:auto; }
td.mono { white-space:nowrap; }
.diagram { background:var(--surface-2); border-radius:10px; padding:12px; overflow-x:auto; }
.diagram pre.mermaid { margin:0; text-align:center; font-family:var(--f-mono); font-size:12px; }
ul.clean { margin:6px 0 0; padding-left:18px; } ul.clean li { margin:3px 0; }
.note { border-left:3px solid var(--warn); background:var(--warn-soft); color:var(--ink); padding:8px 12px; border-radius:6px; margin-top:10px; font-size:13px; }
.story { border-top:1px solid var(--line); padding:10px 0; } .story:first-of-type { border-top:0; }
footer { color:var(--muted); font-size:12px; margin-top:24px; }
"""


def _b(kind: str, text: str | None = None) -> str:
    """A badge for a status (meets, gap, ...) or directly for a colour (ok, warn, crit, blue, accent, neutral)."""
    colours = ("ok", "warn", "crit", "blue", "accent", "neutral")
    cls, label = (kind, kind) if kind in colours else BADGE.get(kind, ("neutral", kind))
    return f'<span class="badge b-{cls}">{escape(text or label)}</span>'


def proposal_html(result: dict, requirement: dict, mermaid_url: str = MERMAID_ESM) -> str:
    e = escape
    nfrs = {n["id"]: n for n in requirement["nfrs"]}
    options = result["options"]
    cells = {(c["pattern_id"], c["nfr_id"]): c for c in result["cells"]}
    traces = result["traceability"]
    traced = sum(t["status"] == "traced" for t in traces)
    src = result.get("requirement_source") or {}
    from_doc = bool(src.get("document"))
    adr, diagram = result.get("adr"), result.get("diagram")
    pref = next((o for o in options if o["status"] == "preferred"), None)

    head = (f'<header><div><div class="eyebrow">Architecture &amp; ADLC · '
            f'{"from requirement document" if from_doc else "from structured requirement"}</div>'
            f'<h1>{e(requirement["title"])}</h1>'
            f'<p class="sub">{e(result["requirement_id"])} · regions {e(", ".join(requirement["regions"]))} · '
            f'as of {e(result["as_of"])} · provider <span class="mono">{e(result["provider"])}</span>. '
            'Options are scored and the diagram is drawn in code; the model only drafts wording. '
            'Nothing has been written to the ADR repository or the backlog.</p></div>'
            '<div class="badges">' + (_b("warn", "Requirement · needs confirmation") if from_doc else "")
            + _b("accent", "Proposal · needs review") + "</div></header>")

    # ---- requirement panel
    nrows = "".join(
        f'<tr><td>{e(n["name"])} <span class="sub">({e(n["priority"])})</span></td>'
        f'<td class="mono">{e(t["target"])}</td><td>{_b(t["status"])}</td></tr>'
        for n, t in ((nfrs[t["nfr_id"]], t) for t in traces))
    rejected = result.get("extraction_rejected") or []
    flags = src.get("flags") or []
    req_panel = (
        '<section class="panel"><div class="panel-h"><h2>Requirement document</h2>'
        f'<span class="mono">{e(src.get("document") or "requirement.json")}</span></div>'
        + (f'<div class="sub">{e(src.get("status", ""))}</div>' if from_doc else "")
        + '<div class="stats">'
        f'<div class="stat"><b>{len(requirement["capabilities"])}</b><span>capabilities</span></div>'
        f'<div class="stat"><b>{len(requirement["nfrs"])}</b><span>NFRs</span></div>'
        f'<div class="stat"><b>{len(result["open_questions"])}</b><span>open questions</span></div>'
        f'<div class="stat"><b>{len(rejected)}</b><span>items rejected</span></div></div>'
        f'<table><tr><th>NFR</th><th>Target</th><th>Trace</th></tr>{nrows}</table>'
        + ("".join(f'<div class="note">Not extracted: {e(r)}</div>' for r in rejected))
        + (f'<div class="note">Document flags: {e(", ".join(flags))}. Secrets were redacted and instruction-like '
           'text was treated as data before the model saw the document.</div>' if flags else "")
        + "</section>")

    # ---- diagram panel
    if diagram:
        issues = "".join(f'<div class="note">{e(i)}</div>' for i in diagram["issues"])
        dia_panel = ('<section class="panel"><div class="panel-h">'
                     f'<h2>Container view · {e(diagram["pattern_id"])} {e(pref["name"] if pref else "")}</h2>'
                     f'<span class="sub">{traced} of {len(traces)} NFRs traced</span></div>'
                     f'<div class="diagram"><pre class="mermaid">{e(diagram["mermaid"])}</pre></div>'
                     '<p class="sub" style="margin:8px 0 0">Drawn from the pattern library. Each component lists '
                     'the NFRs traced to it.</p>' + issues + "</section>")
    else:
        dia_panel = ('<section class="panel"><h2>Container view</h2><p class="sub">No diagram: '
                     + ("the preferred pattern defines no components." if pref else "no option meets every must-have NFR.")
                     + "</p></section>")
    top = (f'<div class="grid g-flow">{req_panel}<div class="arrow" aria-hidden="true">→<small>assess · draft'
           f'<br>trace · draw</small></div>{dia_panel}</div>')

    # ---- option comparison
    th = "".join(f'<th>{e(o["pattern_id"])} · {e(o["name"])}</th>' for o in options)
    rows = "".join(
        f'<tr><td>{e(n["id"])} {e(n["name"])}</td>'
        + "".join(f'<td>{_b(cells[(o["pattern_id"], n["id"])]["status"])}</td>' for o in options) + "</tr>"
        for n in requirement["nfrs"])
    rows += "<tr><td>ADR conflicts</td>" + "".join(
        f'<td class="mono">{e(", ".join(o["adr_conflicts"]) or "none")}</td>' for o in options) + "</tr>"
    rows += "<tr><td><b>Result</b></td>" + "".join(
        f'<td>{_b(o["status"])}' + (f'<div class="sub" style="font-size:12px">{e(o["condition"])}</div>' if o["condition"] else "")
        + "</td>" for o in options) + "</tr>"
    compare = ('<section class="panel"><div class="panel-h"><h2>Option comparison</h2>'
               '<span class="sub">scored in code, not by the model</span></div>'
               f'<div class="scroll"><table><tr><th>NFR</th>{th}</tr>{rows}</table></div></section>')

    # ---- ADR + open questions
    if adr:
        alts = "".join(f'<li><b>{e(a["option_id"])}</b>: {e(a["why_not"])}</li>' for a in adr["alternatives"])
        warn = (f'<div class="note">The draft chooses {e(adr["chosen_option"])}, but the assessment preferred '
                f'{e(result["preferred"])}. The review board should decide.</div>' if adr["disagrees_with_ranking"] else "")
        adr_html = (f'<div class="panel-h"><h2>{e(adr["id"])} · {e(adr["title"])}</h2>{_b("accent", "Draft")}</div>'
                    f'{warn}<p><b>Decision.</b> {e(adr["decision"])}</p>'
                    f'<p class="sub"><b>Context.</b> {e(adr["context"])}</p>'
                    f'<h3>Alternatives</h3><ul class="clean">{alts}</ul>'
                    f'<p class="sub" style="font-size:12px">{e(adr["status"])}</p>')
    else:
        adr_html = f'<h2>{e(result["next_adr_id"])}</h2><p class="sub">No ADR drafted.</p>'
    questions = "".join(f'<li><b>{e(q["id"])}</b> {e(q["question"])}</li>' for q in result["open_questions"])
    side = (f'<section class="panel">{adr_html}<h3 style="margin-top:14px">Open questions for the business</h3>'
            f'<ul class="clean">{questions}</ul></section>')

    # ---- traceability + stories
    trows = "".join(
        f'<tr><td>{e(t["nfr_id"])} {e(t["name"])}</td><td>{e(t["component"] or "—")}</td>'
        f'<td>{e(t["mechanism"] or "—")}</td><td class="mono">{e(", ".join(t["adrs"]) or "—")}</td>'
        f'<td class="mono">{e(", ".join(t["stories"]) or "—")}</td>'
        f'<td>{_b(t["status"])}' + (f' <span class="sub">{e(t["reason"])}</span>' if t["reason"] else "") + "</td></tr>"
        for t in traces)
    trace_panel = ('<section class="panel"><div class="panel-h"><h2>NFR traceability</h2>'
                   f'<span class="sub">{traced} of {len(traces)} traced</span></div><div class="scroll"><table>'
                   '<tr><th>NFR</th><th>Component</th><th>Mechanism</th><th>ADRs</th><th>Stories</th><th>Status</th></tr>'
                   f'{trows}</table></div></section>')
    stories = "".join(
        f'<div class="story"><div class="panel-h" style="margin:0"><h3>{e(s["id"])} · {e(s["title"])}</h3>'
        f'<span class="mono">{e(", ".join(s["capability_ids"] + s["nfr_ids"]))}</span></div>'
        f'<div class="sub">As a {e(s["as_a"])}, I want {e(s["i_want"])}.</div>'
        f'<ul class="clean">{"".join(f"<li>{e(c)}</li>" for c in s["acceptance_criteria"])}</ul></div>'
        for s in result["stories"]) or '<p class="sub">None.</p>'
    story_panel = ('<section class="panel"><div class="panel-h"><h2>User stories</h2>'
                   f'{_b("accent", "Drafts · need product owner")}</div>{stories}</section>')

    rejected_drafts = result.get("rejected_drafts") or []
    rej = ("".join(f'<div class="note">{e(r["item"])}: {e(r["reason"])}</div>' for r in rejected_drafts))

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Architecture proposal · {e(result["requirement_id"])}</title>
<style>{CSS}</style></head>
<body><main>
{head}
{top}
<div class="grid g-two">{compare}{side}</div>
{rej}
<div class="grid g-two">{trace_panel}{story_panel}</div>
<footer>Generated by Engineering Command Centre · use case 3 · synthetic data · Author: Pradeep Sahoo</footer>
</main>
<script type="module">
  try {{
    const {{ default: mermaid }} = await import("{e(mermaid_url)}");
    const css = getComputedStyle(document.documentElement);
    const v = (n) => css.getPropertyValue(n).trim();
    mermaid.initialize({{ startOnLoad: false, theme: "base", securityLevel: "strict", flowchart: {{ htmlLabels: true, padding: 12, subGraphTitleMargin: {{ top: 6, bottom: 14 }} }},
      themeVariables: {{ fontFamily: "Segoe UI, Arial, sans-serif", fontSize: "13px", primaryColor: v("--surface"),
        primaryTextColor: v("--ink"), primaryBorderColor: v("--accent"), lineColor: v("--muted"),
        clusterBkg: v("--bg"), clusterBorder: v("--line"), edgeLabelBackground: v("--surface-2"),
        tertiaryColor: v("--surface-2") }} }});
    await mermaid.run({{ querySelector: "pre.mermaid" }});
  }} catch (err) {{
    document.querySelectorAll("pre.mermaid").forEach((p) => p.insertAdjacentHTML("beforebegin",
      '<p class="sub">Diagram renderer unavailable offline; Mermaid source shown.</p>'));
  }}
  document.documentElement.dataset.rendered = "true";
</script>
</body></html>
"""
