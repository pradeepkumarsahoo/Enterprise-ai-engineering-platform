# Author: Pradeep Sahoo
"""Container diagram of the preferred option, drawn in code (Mermaid).

The diagram comes from the pattern library, not from the model, so it can only
show components and connections the architecture team has defined. Each
component is labelled with the NFRs traced to it, so the picture and the
traceability matrix always agree. Cell-scoped components are drawn once inside
a "regional cell" boundary that names the regions.

Mermaid renders in GitHub, GitLab, Azure DevOps wikis, Confluence (with the
Mermaid macro) and VS Code, and can be exported to SVG or PNG with mermaid-cli.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

SCOPES = ("client", "edge", "cell")


@dataclass
class Diagram:
    pattern_id: str
    mermaid: str
    components: list[str]
    nfrs_shown: list[str]
    issues: list[str] = field(default_factory=list)   # inconsistencies between the pattern and the trace


def _node(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def _label(*lines: str) -> str:
    return '"' + "<br/>".join(l.replace('"', "#quot;") for l in lines if l) + '"'


def container_diagram(pattern: dict, regions: list[str], traces: list) -> Diagram | None:
    """traces: Trace objects from assess.trace. Returns None when the pattern defines no components."""
    comps = pattern.get("components") or []
    if not comps:
        return None
    names = [c["name"] for c in comps]
    issues: list[str] = []
    nfrs_at: dict[str, list[str]] = {n: [] for n in names}
    for t in traces:
        if t.status != "traced":
            continue
        if t.component in nfrs_at:
            nfrs_at[t.component].append(t.nfr_id)
        else:
            issues.append(f"{t.nfr_id} is traced to {t.component!r}, which the pattern does not define")
    for c in comps:
        if c.get("scope") not in SCOPES:
            issues.append(f"{c['name']} has unknown scope {c.get('scope')!r}")

    def node(c) -> str:
        nfr = " · ".join(nfrs_at[c["name"]])
        return f"{_node(c['name'])}[{_label(c['name'], c.get('role', ''), nfr)}]"

    L = ["flowchart TB"]
    L += [f"    {node(c)}" for c in comps if c.get("scope") == "client"]
    edge = [c for c in comps if c.get("scope") == "edge"]
    if edge:
        L += ['    subgraph edge["Global edge"]', "        direction TB"] + [f"        {node(c)}" for c in edge] + ["    end"]
    cell = [c for c in comps if c.get("scope") == "cell"]
    if cell:
        title = (f"Cell per region: {', '.join(regions)}" if pattern.get("scale_unit") == "cell"
                 else "Primary region")
        L += [f'    subgraph cell["{title}"]', "        direction LR"] + [f"        {node(c)}" for c in cell] + ["    end"]
    for src, dst, what in pattern.get("connections", []):
        if src not in names or dst not in names:
            issues.append(f"connection {src} → {dst} names a component the pattern does not define")
            continue
        L.append(f"    {_node(src)} -->|{what.replace('|', '/')}| {_node(dst)}")
    shown = sorted({i for v in nfrs_at.values() for i in v})
    return Diagram(pattern["id"], "\n".join(L), names, shown, issues)
