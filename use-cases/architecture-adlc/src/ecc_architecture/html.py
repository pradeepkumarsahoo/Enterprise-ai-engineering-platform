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

from ecc_core.page import CSS, badge

MERMAID_ESM = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.esm.min.mjs"
STATUS_BADGES = {"meets": ("ok", "Meets"), "at_risk": ("warn", "At risk"), "fails": ("crit", "Fails"),
                 "unknown": ("neutral", "Unknown"), "preferred": ("ok", "Preferred"), "viable": ("blue", "Viable"),
                 "rejected": ("crit", "Rejected"), "traced": ("ok", "Traced"), "gap": ("warn", "Gap")}


def _b(kind: str, text: str | None = None) -> str:
    return badge(kind, text, STATUS_BADGES)


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
