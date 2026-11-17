# Author: Pradeep Sahoo
"""Shared look for the HTML pages use cases write (proposal pages, risk reports).

Design tokens match the stakeholder prototype; light and dark themes follow the viewer's system
setting. Use cases add their own layout classes on top.
"""
from __future__ import annotations

from html import escape

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


def badge(kind: str, text: str | None = None, statuses: dict | None = None) -> str:
    """A badge for a status (looked up in statuses) or directly for a colour (ok, warn, crit, blue, accent, neutral)."""
    colours = ("ok", "warn", "crit", "blue", "accent", "neutral")
    cls, label = (kind, kind) if kind in colours else (statuses or {}).get(kind, ("neutral", kind))
    return f'<span class="badge b-{cls}">{escape(text or label)}</span>'
