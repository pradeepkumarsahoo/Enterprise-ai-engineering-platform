# Author: Pradeep Sahoo
"""Cost by team dashboard (use case 5): one interactive HTML page, written by `ecc finops dashboard`.

The page carries the run's data and recomputes in the browser as the viewer customises it:
- View: allocation by today's tags, with the tag proposals teams have approved, or with every
  proposal (what the tagging agent would fix);
- Basis: amortised (commitments spread over their term) or billed (the invoice);
- Months, environments and service categories to include;
- Shared costs (resources tagged shared=true, and optionally unallocated cost): shown as their own
  row, or split across teams evenly, in proportion to each team's direct cost that month, or by
  fixed percentages;
- Monthly budget per team, compared with the latest complete month and the partial month's forecast.

Every figure is a sum of cost export lines; nothing is estimated by a model. Customisations are kept
in the viewer's browser only, and "Copy as configuration" gives the TOML to make them the default.
Static and self-contained: no network, no server; light and dark themes follow the system.
"""
from __future__ import annotations

import json
from html import escape as e

from ecc_core.page import CSS

from .fmt import month_label
from .html import EXTRA_CSS
from .rules import Rules
from .sources import FinOpsInputs
from .spend import UNALLOCATED, allocate_tags, coverage

VIEWS = (("today", "Today's tags"), ("approved", "With approved tag proposals"),
         ("proposed", "With all tag proposals"))


def _after(tags: dict, p: dict) -> dict:
    """Tags (keys lower case, as the cost export has them) after a proposal."""
    gone = {k.lower() for k in p["remove"]}
    return {k: v for k, v in tags.items() if k not in gone} | {k.lower(): v for k, v in p["set"].items()}


def dashboard_data(inp: FinOpsInputs, r: Rules, tag_run: dict | None, budgets: dict) -> dict:
    cov = coverage(inp.lines)
    known = inp.known_teams
    props = {p["resource"]: p for p in (tag_run or {}).get("proposals", [])}
    rows: dict[tuple, dict] = {}
    res_tags: dict[str, dict] = {}
    for l in inp.lines:
        res_tags.setdefault(l.resource, l.tags)
        k = (l.month, l.resource, l.category, l.tags.get("env", ""))
        x = rows.setdefault(k, {"m": l.month, "r": l.resource, "c": l.category, "e": l.tags.get("env", "") or "untagged",
                                "a": 0.0, "b": 0.0})
        x["a"] += l.cost
        x["b"] += l.billed or 0.0
    resources = {}
    for res, tags in res_tags.items():
        p = props.get(res)
        views = {}
        for v, _ in VIEWS:
            t = tags
            if p and (v == "proposed" and p["status"] != "rejected" or v == "approved" and p["status"] == "approved"):
                t = _after(tags, p)
            team = allocate_tags(t, inp, known)[0]
            views[v] = {"team": team, "shared": t.get("shared", "").lower() == "true",
                        "env": t.get("env", "") or "untagged"}
        resources[res] = {"views": views, "proposal": p["id"] if p else None,
                          "status": p["status"] if p else None}
    teams = sorted({v["team"] for x in resources.values() for v in x["views"].values()} - {UNALLOCATED}
                   | set(budgets.get("monthly", {})))
    return {
        "months": cov.months, "complete": cov.complete, "partial": cov.partial, "scale": cov.scale,
        "run_rate": cov.run_rate if cov.partial else "",
        "rows": [{**x, "a": round(x["a"], 2), "b": round(x["b"], 2)} for x in rows.values()],
        "resources": resources, "teams": teams,
        "categories": sorted({x["c"] for x in rows.values()}),
        "envs": sorted({v["env"] for x in resources.values() for v in x["views"].values()}),
        "budgets": budgets.get("monthly", {}), "has_billed": inp.has_billed,
        "defaults": {"split": r.shared_split, "fixed": r.shared_split_fixed,
                     "unallocated_shared": r.unallocated_as_shared},
        "views": VIEWS, "export_format": inp.export_format,
        "tagging": None if not tag_run else {"kpis": tag_run["kpis"], "proposals": [
            {k: p[k] for k in ("id", "resource", "set", "remove", "team", "status", "monthly_cost", "allocation_now",
                               "allocation_after")} for p in tag_run["proposals"]]},
        "as_of": r.as_of,
    }


DASH_CSS = """
.controls { display:flex; flex-wrap:wrap; gap:10px 18px; align-items:flex-end; }
.controls label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:var(--muted); }
.controls select, .controls input[type=number] { font:inherit; font-size:13px; padding:6px 8px; border-radius:8px;
  border:1px solid var(--line); background:var(--surface); color:var(--ink); }
.chips { display:flex; flex-wrap:wrap; gap:6px; }
.chip { font-size:12px; padding:4px 10px; border-radius:999px; border:1px solid var(--line); background:var(--surface);
  color:var(--ink); cursor:pointer; }
.chip[aria-pressed="false"] { opacity:.45; text-decoration:line-through; }
.btn { font:inherit; font-size:13px; padding:6px 12px; border-radius:8px; border:1px solid var(--line);
  background:var(--surface-2); color:var(--ink); cursor:pointer; }
.btn:hover { border-color:var(--muted); }
.fixed-grid { display:flex; flex-wrap:wrap; gap:8px; }
.fixed-grid input { width:70px; }
td input.budget { width:96px; text-align:right; font-family:var(--f-mono); }
.bar { height:6px; border-radius:3px; background:var(--surface-2); position:relative; margin-top:4px; min-width:90px; }
.bar i { position:absolute; left:0; top:0; bottom:0; border-radius:3px; background:var(--ok); }
.bar i.over { background:var(--crit); } .bar i.near { background:var(--warn); }
pre.cfg { font-family:var(--f-mono); font-size:12px; background:var(--surface-2); padding:10px 12px; border-radius:8px;
  white-space:pre-wrap; }
.g-4 { grid-template-columns:repeat(4,minmax(0,1fr)); }
@media (max-width: 900px) { .g-4 { grid-template-columns:repeat(2,minmax(0,1fr)); } }
"""

SCRIPT = r"""
const D = JSON.parse(document.getElementById('data').textContent);
const UN = 'Unallocated', SH = 'Shared';
const fmt = (v) => (v < 0 ? '-$' : '$') + Math.abs(Math.round(v)).toLocaleString('en-US');
const pct = (v) => Math.round(v * 100) + '%';
const mlabel = (m) => new Date(m + '-01T00:00:00Z').toLocaleString('en-GB', { month: 'short', year: 'numeric', timeZone: 'UTC' });
const KEY = 'ecc-finops-dashboard-v1';
const defaults = () => ({ view: 'today', basis: 'a', from: D.months[0], to: D.months[D.months.length - 1],
  envs: D.envs.slice(), cats: D.categories.slice(), split: D.defaults.split, unShared: D.defaults.unallocated_shared,
  fixed: parseFixed(D.defaults.fixed), budgets: Object.assign({}, D.budgets) });
function parseFixed(text) {
  const out = {}; (text || '').split(',').forEach((p) => { const [t, v] = p.split(':'); if (t && v) out[t.trim()] = +v; });
  D.teams.forEach((t) => { if (!(t in out)) out[t] = 0; }); return out;
}
let S;
try { S = Object.assign(defaults(), JSON.parse(localStorage.getItem(KEY) || '{}')); } catch (err) { S = defaults(); }
// a link can carry a view: #view=proposed&split=even&basis=b&unshared=1&from=2026-06&to=2026-11
new URLSearchParams(location.hash.slice(1)).forEach((v, k) => {
  if (k === 'unshared') S.unShared = v === '1';
  else if (['view', 'basis', 'split', 'from', 'to'].includes(k)) S[k] = v;
});
const save = () => {
  try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (err) { /* storage unavailable */ }
  const h = `view=${S.view}&basis=${S.basis}&split=${S.split}&unshared=${S.unShared ? 1 : 0}&from=${S.from}&to=${S.to}`;
  try { history.replaceState(null, '', '#' + h); } catch (err) { /* file: URLs may refuse */ }
};
const $ = (s) => document.querySelector(s);
const SLOT = (t) => { const i = D.teams.indexOf(t); return t === UN ? 'var(--s0)' : t === SH ? 'var(--s5)' : `var(--s${(i % 4) + 1})`; };

function compute() {
  const months = D.months.filter((m) => m >= S.from && m <= S.to);
  const res = {}; // month -> {team: cost}
  const pools = {}; const directs = {};
  months.forEach((m) => { res[m] = {}; pools[m] = 0; directs[m] = {}; });
  D.rows.forEach((row) => {
    if (!(row.m in res)) return;
    const v = D.resources[row.r].views[S.view];
    if (!S.envs.includes(v.env) || !S.cats.includes(row.c)) return;
    const cost = S.basis === 'b' ? row.b : row.a;
    if (v.shared || (S.unShared && v.team === UN)) { pools[row.m] += cost; return; }
    directs[row.m][v.team] = (directs[row.m][v.team] || 0) + cost;
  });
  months.forEach((m) => {
    const direct = directs[m]; Object.assign(res[m], direct);
    const pool = pools[m]; if (!pool) return;
    const named = D.teams.filter((t) => t !== UN);
    let weights = {};
    if (S.split === 'even') named.forEach((t) => { weights[t] = 1; });
    else if (S.split === 'proportional') named.forEach((t) => { weights[t] = Math.max(direct[t] || 0, 0); });
    else if (S.split === 'fixed') named.forEach((t) => { weights[t] = Math.max(+S.fixed[t] || 0, 0); });
    const total = Object.values(weights).reduce((a, b) => a + b, 0);
    if (S.split === 'none' || !total) { res[m][SH] = (res[m][SH] || 0) + pool; return; }
    named.forEach((t) => { if (weights[t]) res[m][t] = (res[m][t] || 0) + pool * weights[t] / total; });
  });
  const teams = D.teams.filter((t) => months.some((m) => Math.abs(res[m][t] || 0) > 0.5))
    .concat([SH, UN].filter((t) => months.some((m) => Math.abs(res[m][t] || 0) > 0.5)));
  const forecast = {};
  if (D.partial && res[D.partial]) teams.forEach((t) => { forecast[t] = (res[D.partial][t] || 0) * D.scale; });
  return { months, res, teams, forecast, pools };
}

function chart(c) {
  const cols = c.months.map((m) => ({ m, fc: m === D.partial }));
  const val = (t, col) => Math.max(col.fc ? (c.forecast[t] || 0) : (c.res[col.m][t] || 0), 0);
  const totals = cols.map((col) => c.teams.reduce((a, t) => a + val(t, col), 0));
  const W = 1000, H = 300, L = 56, R = 8, T = 22, B = 26, pw = W - L - R, ph = H - T - B;
  const max = Math.max(...totals, 1) * 1.08;
  const step = [5e3, 1e4, 2e4, 25e3, 5e4, 1e5, 2e5, 25e4, 5e5, 1e6].find((s) => max / s <= 5) || max / 4;
  const top = step * Math.ceil(max / step);
  const y = (v) => T + ph - (v / top) * ph;
  const slot = pw / Math.max(cols.length, 1), bw = Math.min(34, slot * 0.62);
  let s = `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Monthly cost by team, stacked columns">`;
  for (let v = 0; v <= top + 1; v += step) s += `<line class="grid" x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}"/><text x="${L - 6}" y="${y(v) + 4}" text-anchor="end">$${Math.round(v / 1000)}k</text>`;
  cols.forEach((col, i) => {
    const x = L + i * slot + (slot - bw) / 2; let base = 0;
    const vis = c.teams.filter((t) => val(t, col) > 0);
    vis.forEach((t, j) => {
      const v = val(t, col), y0 = y(base + v), h = Math.max(y(base) - y0 - (j < vis.length - 1 ? 2 : 0), 0.5);
      s += `<rect class="seg${col.fc ? ' fc' : ''}" x="${x}" y="${y0}" width="${bw}" height="${h}" rx="${j === vis.length - 1 ? 3 : 0}" style="fill:${SLOT(t)}"><title>${esc(t)} · ${mlabel(col.m)}${col.fc ? ' forecast' : ''}: ${fmt(v)}</title></rect>`;
      base += v;
    });
    if (col.fc) s += `<rect class="fc-outline" x="${x}" y="${y(base)}" width="${bw}" height="${y(0) - y(base)}" rx="3"/>`;
    s += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${mlabel(col.m).slice(0, 3)}${col.fc ? '*' : ''}</text>`;
    if (i === cols.length - 1 || i === cols.length - 2) s += `<text class="val" x="${x + bw / 2}" y="${y(base) - 6}" text-anchor="middle">$${Math.round(base / 1000)}k</text>`;
  });
  s += '</svg>';
  const legend = c.teams.map((t) => `<span><i style="background:${SLOT(t)}"></i>${esc(t)}</span>`).join('')
    + (D.partial && c.months.includes(D.partial) ? `<span><i class="fc"></i>* ${mlabel(D.partial)} forecast: ${esc(D.run_rate)}</span>` : '');
  $('#chart').innerHTML = `<div class="viz"><div class="legend">${legend}</div>${s}</div>`;
}

function esc(t) { return String(t).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch])); }

function table(c) {
  const last = c.months.filter((m) => D.complete.includes(m)).pop();
  const hasFc = D.partial && c.months.includes(D.partial);
  let h = '<tr><th>Team</th>' + c.months.map((m) => `<th class="num">${mlabel(m).slice(0, 3)}${m === D.partial ? '*' : ''}</th>`).join('')
    + (hasFc ? '<th class="num">Fcst*</th>' : '') + '<th class="num">Budget / month</th><th>vs budget</th></tr>';
  c.teams.forEach((t) => {
    const b = S.budgets[t];
    const basis = hasFc ? c.forecast[t] || 0 : (last ? c.res[last][t] || 0 : 0);
    const ratio = b ? basis / b : 0;
    const cls = ratio > 1 ? 'over' : ratio > 0.9 ? 'near' : '';
    const budgetCell = (t === UN || t === SH) ? '<td></td><td class="sub">no owner</td>'
      : `<td class="num"><input class="budget" type="number" min="0" step="500" data-team="${esc(t)}" value="${b || ''}" aria-label="Monthly budget for ${esc(t)}"></td>`
        + `<td>${b ? `<span class="${ratio > 1 ? 'up-bad' : ''}">${pct(ratio)} ${hasFc ? 'forecast' : mlabel(last)}</span><div class="bar"><i class="${cls}" style="width:${Math.min(ratio, 1) * 100}%"></i></div>` : '<span class="sub">no budget</span>'}</td>`;
    h += `<tr><td><i class="dot" style="background:${SLOT(t)}"></i>${esc(t)}</td>` + c.months.map((m) => `<td class="num">${fmt(c.res[m][t] || 0)}</td>`).join('')
      + (hasFc ? `<td class="num">${fmt(c.forecast[t] || 0)}</td>` : '') + budgetCell + '</tr>';
  });
  const tot = (m) => c.teams.reduce((a, t) => a + (c.res[m][t] || 0), 0);
  h += '<tr class="total"><td>Total</td>' + c.months.map((m) => `<td class="num">${fmt(tot(m))}</td>`).join('')
    + (hasFc ? `<td class="num">${fmt(c.teams.reduce((a, t) => a + (c.forecast[t] || 0), 0))}</td>` : '') + '<td></td><td></td></tr>';
  $('#table').innerHTML = h;
  document.querySelectorAll('input.budget').forEach((el) => el.addEventListener('change', () => {
    const v = parseFloat(el.value); if (v > 0) S.budgets[el.dataset.team] = v; else delete S.budgets[el.dataset.team];
    render();
  }));
}

function kpis(c) {
  const last = c.months.filter((m) => D.complete.includes(m)).pop();
  const tot = last ? c.teams.reduce((a, t) => a + (c.res[last][t] || 0), 0) : 0;
  const un = last ? (c.res[last][UN] || 0) : 0;
  const pool = last ? c.pools[last] : 0;
  const hasFc = D.partial && c.months.includes(D.partial);
  const over = c.teams.filter((t) => S.budgets[t] && (hasFc ? c.forecast[t] || 0 : (last ? c.res[last][t] || 0 : 0)) > S.budgets[t]);
  const splitText = { none: 'shown as its own row', even: 'split evenly', proportional: 'split by direct cost', fixed: 'split by fixed %' }[S.split];
  $('#kpis').innerHTML = [
    ['Spend · ' + (last ? mlabel(last) : '—'), fmt(tot), S.basis === 'b' ? 'billed (invoice)' : 'amortised', 'cost export'],
    ['Unallocated · ' + (last ? mlabel(last) : '—'), fmt(un), tot ? pct(un / tot) + ' of spend' : '', 'no valid team tag or catalogue owner'],
    ['Shared pool · ' + (last ? mlabel(last) : '—'), fmt(pool), splitText, 'shared=true' + (S.unShared ? ' + unallocated' : '')],
    ['Over budget', String(over.length), over.length ? over.join(', ') : 'no team over budget', hasFc ? mlabel(D.partial) + ' forecast' : 'latest complete month'],
  ].map(([l, v, d, s]) => `<div class="panel kpi"><span class="label">${esc(l)}</span><span class="value">${esc(v)}</span><span class="delta${l === 'Over budget' && over.length ? ' up-bad' : ''}">${esc(d)}</span><span class="src">${esc(s)}</span></div>`).join('');
}

function config() {
  const fixed = Object.entries(S.fixed).filter(([, v]) => +v > 0).map(([t, v]) => `${t}:${v}`).join(',');
  const budgets = Object.entries(S.budgets).map(([t, v]) => `  "${t}": ${v}`).join(',\n');
  $('#cfg').textContent = `# config/product.toml, [use_cases.finops.settings]\nshared_split = "${S.split}"\nshared_split_fixed = "${fixed}"\nunallocated_as_shared = ${S.unShared}\n\n# use-cases/finops/data/synthetic/budgets.json, "monthly"\n{\n${budgets}\n}`;
}

function csv(c) {
  const head = ['team'].concat(c.months).concat(D.partial && c.months.includes(D.partial) ? ['forecast'] : []);
  const lines = [head.join(',')].concat(c.teams.map((t) => [`"${t}"`].concat(c.months.map((m) => (c.res[m][t] || 0).toFixed(2)))
    .concat(D.partial && c.months.includes(D.partial) ? [(c.forecast[t] || 0).toFixed(2)] : []).join(',')));
  const a = document.createElement('a');
  a.href = URL.createObjectURL(new Blob([lines.join('\n') + '\n'], { type: 'text/csv' }));
  a.download = `cost-by-team-${S.view}-${S.basis === 'b' ? 'billed' : 'amortised'}.csv`; a.click();
}

function controls() {
  const opt = (v, t, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(t)}</option>`;
  $('#view').innerHTML = D.views.map(([v, t]) => opt(v, t, S.view)).join('');
  $('#basis').innerHTML = opt('a', 'Amortised', S.basis) + (D.has_billed ? opt('b', 'Billed (invoice)', S.basis) : '');
  $('#from').innerHTML = D.months.map((m) => opt(m, mlabel(m), S.from)).join('');
  $('#to').innerHTML = D.months.map((m) => opt(m, mlabel(m), S.to)).join('');
  $('#split').innerHTML = [['none', 'Show as its own row'], ['even', 'Split evenly'], ['proportional', 'Split by direct cost'], ['fixed', 'Split by fixed %']].map(([v, t]) => opt(v, t, S.split)).join('');
  $('#unshared').checked = S.unShared;
  const chips = (id, all, sel, key) => { $(id).innerHTML = all.map((x) => `<button class="chip" type="button" data-k="${key}" data-v="${esc(x)}" aria-pressed="${sel.includes(x)}">${esc(x)}</button>`).join(''); };
  chips('#envs', D.envs, S.envs, 'envs'); chips('#cats', D.categories, S.cats, 'cats');
  $('#fixed').hidden = S.split !== 'fixed';
  $('#fixed .fixed-grid').innerHTML = D.teams.map((t) => `<label>${esc(t)}<input type="number" min="0" step="5" data-team="${esc(t)}" value="${+S.fixed[t] || 0}"></label>`).join('');
  document.querySelectorAll('#fixed input').forEach((el) => el.addEventListener('change', () => { S.fixed[el.dataset.team] = +el.value || 0; render(); }));
  document.querySelectorAll('.chip').forEach((el) => el.addEventListener('click', () => {
    const list = S[el.dataset.k], v = el.dataset.v;
    S[el.dataset.k] = list.includes(v) ? list.filter((x) => x !== v) : list.concat([v]); render(true);
  }));
}

function tagging() {
  if (!D.tagging) { $('#tagging').innerHTML = '<p class="sub">No tagging check yet: run <span class="mono">ecc finops tags check</span>.</p>'; return; }
  const k = D.tagging.kpis;
  $('#tagging').innerHTML = `<p class="sub">${k.resources} resources checked · ${k.compliant} compliant · ${k.waiting} proposals waiting for the owning team · ${k.needs_owner} with no owner established · ${k.approved} approved. The agent proposes; nothing is tagged until the team applies it.</p>`
    + '<div class="scroll"><table><tr><th>Proposal</th><th>Tags</th><th>Approver team</th><th class="num">Monthly cost</th><th>Allocation</th><th>Status</th></tr>'
    + D.tagging.proposals.map((p) => `<tr><td class="mono">${esc(p.id)}</td><td class="mono">${Object.entries(p.set).map(([a, b]) => esc(a + '=' + b)).join(', ')}${p.remove.length ? ' · remove ' + esc(p.remove.join(', ')) : ''}</td><td>${esc(p.team || '—')}</td><td class="num">${p.monthly_cost == null ? '—' : fmt(p.monthly_cost)}</td><td>${esc(p.allocation_now)} → ${esc(p.allocation_after)}</td><td>${esc(p.status)}</td></tr>`).join('')
    + '</table></div>';
}

function render(redraw) {
  if (redraw) controls();
  $('#fixed').hidden = S.split !== 'fixed';
  const c = compute(); kpis(c); chart(c); table(c); config(); save();
  $('#csv').onclick = () => csv(c);
}

controls(); tagging();
['view', 'basis', 'from', 'to', 'split'].forEach((id) => $('#' + id).addEventListener('change', (ev) => {
  S[id] = ev.target.value; if (S.from > S.to) S.to = S.from; render(true);
}));
$('#unshared').addEventListener('change', (ev) => { S.unShared = ev.target.checked; render(); });
$('#reset').addEventListener('click', () => { S = defaults(); render(true); });
render();
"""


def dashboard_html(data: dict) -> str:
    blob = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    partial = f" · {month_label(data['partial'])} to date ({e(data['run_rate'])})" if data["partial"] else ""
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cost by Team</title>
<style>{CSS}{EXTRA_CSS}{DASH_CSS}
.viz {{ --s5:#7c6fd6; }} i.dot {{ display:inline-block; width:9px; height:9px; border-radius:2px; margin-right:8px; }}
</style></head>
<body><main class="viz">
<header><div><div class="eyebrow">FinOps · cost by team</div><h1>Cost by team</h1>
<p class="sub">As of {e(data['as_of'])} · cost export <span class="mono">{e(data['export_format'])}</span>{partial}. Every figure is a sum of
cost export lines. Customise the view below; your settings stay in this browser, and "Copy as configuration" makes them the
default for everyone.</p></div></header>
<section class="panel"><div class="controls">
<label>View<select id="view"></select></label>
<label>Cost basis<select id="basis"></select></label>
<label>From<select id="from"></select></label>
<label>To<select id="to"></select></label>
<label>Shared costs<select id="split"></select></label>
<label style="flex-direction:row;align-items:center;gap:6px"><input type="checkbox" id="unshared"> Treat unallocated as shared</label>
<button class="btn" id="reset" type="button">Reset</button>
<button class="btn" id="csv" type="button">Download CSV</button>
</div>
<div class="controls" style="margin-top:12px"><div><div class="sub" style="font-size:12px;margin-bottom:4px">Environments</div><div class="chips" id="envs"></div></div>
<div><div class="sub" style="font-size:12px;margin-bottom:4px">Categories</div><div class="chips" id="cats"></div></div></div>
<div id="fixed" hidden style="margin-top:12px"><div class="sub" style="font-size:12px;margin-bottom:4px">Fixed split (percent; normalised to 100)</div><div class="fixed-grid controls"></div></div>
</section>
<div class="grid g-4" id="kpis"></div>
<section class="panel"><div class="panel-h"><h2>Monthly cost by team</h2><span class="sub mono">USD</span></div><div id="chart"></div>
<div class="scroll"><table id="table"></table></div><p class="sub mono">* partial month: month to date; Fcst is its run-rate forecast. Budgets are monthly and editable.</p></section>
<section class="panel"><div class="panel-h"><h2>Tagging agent</h2><span class="sub">proposals only · nothing is tagged until the owning team applies it</span></div><div id="tagging"></div></section>
<section class="panel"><div class="panel-h"><h2>Copy as configuration</h2><span class="sub">make these settings the default</span></div><pre class="cfg" id="cfg"></pre></section>
<footer>Generated by Engineering Command Centre · use case 5 · synthetic data · Author: Pradeep Sahoo</footer>
</main>
<script type="application/json" id="data">{blob}</script>
<script>{SCRIPT}</script>
</body></html>
"""
