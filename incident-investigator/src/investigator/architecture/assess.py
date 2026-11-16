# Author: Pradeep Sahoo
"""Deterministic architecture assessment (use case 3).

Everything that decides *which option fits* runs here, in code:
- every reference pattern is scored against every NFR with a fixed rule per
  NFR category (meets / at risk / fails / unknown);
- an option that fails a "must" NFR is rejected; the rest are ranked;
- conflicts with accepted ADRs are flagged;
- NFRs with no agreed target and undecided business questions become open
  questions instead of guesses;
- after drafting, each NFR is traced to a component, a mechanism, ADRs and
  stories, or reported as a gap.

The model is only asked to word the ADR and the user stories afterwards.
Every fact cites evidence records (A1, A2, ...), as use cases 1 and 2 cite
E1... and K1...
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..models import Evidence
from ..safety import clean
from .sources import ArchitectureInputs

STATUSES = ("meets", "at_risk", "fails", "unknown")
AVAILABILITY_MARGIN = 0.05     # within this many points below target = at risk
LATENCY_MARGIN = 1.2           # up to 20% over the latency target = at risk
THROUGHPUT_MARGIN = 0.8        # at least 80% of the throughput target = at risk
COST_RANK = {"low": 0, "medium": 1, "high": 2, "very high": 3}


@dataclass
class Cell:
    pattern_id: str
    nfr_id: str
    status: str                  # meets | at_risk | fails | unknown
    detail: str                  # computed in code
    evidence: str                # A-id of this assessment


@dataclass
class OptionResult:
    pattern_id: str
    name: str
    status: str                  # preferred | viable | rejected
    fails_must: list[str]
    at_risk: list[str]
    adr_conflicts: list[str]     # accepted ADRs the option would contradict
    relative_cost: str
    condition: str               # when a rejected option would become viable
    evidence: list[str]


@dataclass
class OpenQuestion:
    id: str                      # NFR id or open decision id
    question: str
    affects: list[str]
    evidence: str


@dataclass
class Assessment:
    requirement_id: str
    as_of: str
    evidence: list[Evidence]
    cells: list[Cell]
    options: list[OptionResult]  # preferred first, rejected last
    preferred: str | None
    next_adr_id: str
    open_questions: list[OpenQuestion]
    flagged_notes: list[str] = field(default_factory=list)   # evidence ids of notes flagged as instructions

    def cell(self, pattern_id: str, nfr_id: str) -> Cell:
        return next(c for c in self.cells if c.pattern_id == pattern_id and c.nfr_id == nfr_id)


@dataclass
class Trace:
    nfr_id: str
    name: str
    target: str
    status: str                  # traced | gap
    component: str
    mechanism: str
    adrs: list[str]
    stories: list[str]
    reason: str                  # why it is a gap


def fmt(v) -> str:
    """Numbers as people write them: 2000, 99.95, 0."""
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v)


def target_text(nfr: dict) -> str:
    t = nfr["target"]
    if t is None:
        return "not set"
    if isinstance(t, bool):
        return "required" if t else "not required"
    if isinstance(t, list):
        return ", ".join(t)
    return f"{fmt(t)}%" if nfr["unit"] == "%" else f"{fmt(t)} {nfr['unit']}"


def _assess(p: dict, nfr: dict, regions: list[str]) -> tuple[str, str]:
    """One rule per NFR category. Returns (status, detail); the detail holds every figure used."""
    t, cat = nfr["target"], nfr["category"]
    if t is None:
        return "unknown", "no agreed target, so it cannot be assessed"
    if cat == "availability":
        e = p["availability"]
        s = "meets" if e >= t else "at_risk" if e >= round(t - AVAILABILITY_MARGIN, 4) else "fails"
        return s, f"estimate {fmt(e)}% vs target {fmt(t)}%"
    if cat == "latency_p99":
        e = p["latency_p99_ms"]
        s = "meets" if e <= t else "at_risk" if e <= t * LATENCY_MARGIN else "fails"
        return s, f"estimate {fmt(e)} ms vs target {fmt(t)} ms"
    if cat == "throughput":
        per = p["throughput_per_unit"]
        if p["scale_unit"] == "cell":
            cap = per * len(regions)
            how = f"{fmt(per)}/s per cell × {len(regions)} regions = {fmt(cap)}/s"
        else:
            cap, how = per, f"{fmt(per)}/s for the deployment"
        s = "meets" if cap >= t else "at_risk" if cap >= t * THROUGHPUT_MARGIN else "fails"
        return s, f"capacity {how} vs target {fmt(t)}/s"
    if cat == "rpo":
        e = p["rpo_s"]
        return ("meets" if e <= t else "fails"), f"estimate {fmt(e)} s vs target {fmt(t)} s"
    if cat == "residency":
        r = p["residency"]
        if r == "per_region":
            return "meets", f"data kept per region; required in {', '.join(t)}"
        if r == "single_region":
            return ("meets" if len(t) == 1 else "fails"), f"all data in one region; required in {', '.join(t)}"
        return "fails", f"data replicated to every region; required to stay in {', '.join(t)}"
    if cat == "encryption":
        return ("meets" if p["pii_encryption"] else "fails"), \
            "pattern encrypts PII" if p["pii_encryption"] else "pattern does not encrypt PII"
    if cat in ("audit", "idempotency"):
        v = p[cat]
        return {"native": "meets", "addable": "at_risk"}.get(v, "fails"), \
            {"native": "built into the pattern", "addable": "must be built separately"}.get(v, "not supported")
    if cat == "scale_out":
        v = p["scale_out"]
        return ("meets" if v == "horizontal" else "at_risk"), f"{v} scaling"
    return "unknown", f"no assessment rule for category {cat}"


class _EvidenceBook:
    def __init__(self):
        self.items: list[Evidence] = []
        self._keys: dict[str, str] = {}

    def add(self, key: str, kind: str, source: str, summary: str, flags: list[str] | None = None) -> str:
        if key not in self._keys:
            eid = f"A{len(self.items) + 1}"
            self.items.append(Evidence(eid, kind, source, summary, flags or []))
            self._keys[key] = eid
        return self._keys[key]

    def id(self, key: str) -> str:
        return self._keys[key]


def assess(inp: ArchitectureInputs) -> Assessment:
    req, ev = inp.requirement, _EvidenceBook()
    regions = req["regions"]
    ev.add("req", "requirement", "requirements tool",
           f"{req['id']} “{req['title']}” · sponsor {req['sponsor']} · regions {', '.join(regions)} · capabilities "
           + "; ".join(f"{c['id']} {c['name']}" for c in req["capabilities"]))
    for n in req["nfrs"]:
        ev.add(f"nfr:{n['id']}", "nfr", "requirements tool",
               f"{n['id']} {n['name']} ({n['priority']}): target {target_text(n)}")
    for p in inp.patterns:
        ev.add(f"pat:{p['id']}", "pattern", "pattern library",
               f"{p['id']} {p['name']}: {p['summary']} Relative cost {p['relative_cost']}. Trade-offs: "
               + "; ".join(p["tradeoffs"]))
    for a in inp.adrs:
        ev.add(f"adr:{a['id']}", "adr", "ADR repository",
               f"{a['id']} “{a['title']}” · {a['status']}"
               + (f" (superseded by {a['superseded_by']})" if a.get("superseded_by") else "") + f" · {a['date']}")
    flagged = []
    for i, note in enumerate(req.get("stakeholder_notes", []), start=1):
        text, flags = clean(note["text"])
        eid = ev.add(f"note:{i}", "stakeholder_note", "requirements tool", f"Note from {note['from']}: {text}", flags)
        if "possible_prompt_injection" in flags:
            flagged.append(eid)

    # ---- every pattern against every NFR
    cells: list[Cell] = []
    for p in inp.patterns:
        for n in req["nfrs"]:
            status, detail = _assess(p, n, regions)
            eid = ev.add(f"cell:{p['id']}:{n['id']}", "assessment", "assessment rules",
                         f"{p['id']} vs {n['id']} {n['name']}: {detail} → {status.replace('_', ' ')}")
            cells.append(Cell(p["id"], n["id"], status, detail, eid))

    # ---- option status and ranking
    accepted = {a["id"] for a in inp.adrs if a["status"] == "accepted"}
    nfr_by_id = {n["id"]: n for n in req["nfrs"]}
    options: list[OptionResult] = []
    for p in inp.patterns:
        mine = [c for c in cells if c.pattern_id == p["id"]]
        fails = [c.nfr_id for c in mine if c.status == "fails" and nfr_by_id[c.nfr_id]["priority"] == "must"]
        risky = [c.nfr_id for c in mine if c.status == "at_risk"
                 or (c.status == "fails" and nfr_by_id[c.nfr_id]["priority"] != "must")]
        conflicts = [a for a in p.get("contradicts", []) if a in accepted]
        evidence = [ev.id(f"pat:{p['id']}")] + [c.evidence for c in mine if c.nfr_id in fails + risky] \
            + [ev.id(f"adr:{a}") for a in conflicts]
        condition = ""
        if fails:
            if all(nfr_by_id[f]["category"] == "residency" for f in fails):
                condition = "Viable only for a single-region launch"
            else:
                condition = "Would need " + ", ".join(f"{f} {nfr_by_id[f]['name']}" for f in fails) + " relaxed"
        options.append(OptionResult(p["id"], p["name"], "rejected" if fails else "viable", fails, risky, conflicts,
                                    p["relative_cost"], condition, evidence))
    options.sort(key=lambda o: (o.status == "rejected", len(o.fails_must), len(o.at_risk), len(o.adr_conflicts),
                                COST_RANK.get(o.relative_cost, 9), o.pattern_id))
    preferred = None
    if options and options[0].status == "viable":
        options[0].status = "preferred"
        preferred = options[0].pattern_id

    # ---- open questions: missing targets and undecided business questions
    questions: list[OpenQuestion] = []
    for n in req["nfrs"]:
        if n["target"] is None:
            questions.append(OpenQuestion(n["id"], f"What is the target for {n['id']} {n['name']} ({n['unit']})? "
                                          "No option can be assessed against it until it is agreed.",
                                          [n["id"]], ev.id(f"nfr:{n['id']}")))
    for d in req.get("open_decisions", []):
        eid = ev.add(f"od:{d['id']}", "open_decision", "requirements tool",
                     f"{d['id']} undecided: {d['question']} Affects {', '.join(d['affects'])}")
        questions.append(OpenQuestion(d["id"], d["question"], d["affects"], eid))
    if preferred is None:
        questions.append(OpenQuestion("NO-OPTION", "No reference pattern meets every must-have NFR. Which NFR can be "
                                      "relaxed, or should a new pattern be designed?", [], ev.id("req")))

    numbers = [int(a["id"].split("-")[1]) for a in inp.adrs if a["id"].startswith("ADR-")]
    next_adr = f"ADR-{(max(numbers) + 1 if numbers else 1):03d}"
    return Assessment(req["id"], req["as_of"], ev.items, cells, options, preferred, next_adr, questions, flagged)


def trace(inp: ArchitectureInputs, a: Assessment, stories: list) -> list[Trace]:
    """Trace each NFR to the preferred option's mechanism, ADRs and validated stories."""
    pattern = inp.pattern(a.preferred) if a.preferred else None
    out: list[Trace] = []
    for n in inp.requirement["nfrs"]:
        mech = (pattern or {}).get("mechanisms", {}).get(n["category"])
        covering = [s.id for s in stories if n["id"] in s.nfr_ids]
        component, mechanism, adrs = (mech[0], mech[1], list(mech[2])) if mech else ("", "", [])
        if n["target"] is None:
            reason = "no agreed target"
        elif pattern is None:
            reason = "no option meets every must-have NFR"
        elif a.cell(pattern["id"], n["id"]).status != "meets":
            reason = f"preferred option is {a.cell(pattern['id'], n['id']).status.replace('_', ' ')}"
        elif not mech:
            reason = "preferred pattern names no mechanism for it"
        elif not covering:
            reason = "no validated story covers it"
        else:
            reason = ""
        out.append(Trace(n["id"], n["name"], target_text(n), "gap" if reason else "traced", component, mechanism,
                         adrs, covering, reason))
    return out
