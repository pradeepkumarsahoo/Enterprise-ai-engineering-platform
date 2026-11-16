# Author: Pradeep Sahoo
"""Tests for use case 3: architecture & ADLC."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from ecc_core.cli import main as ecc
from ecc_core.llm import ClaudeClient
from ecc_core.plugin import context_for

from ecc_architecture import ArchitectureInputs, ClaudeArchitect, MockDrafter, Rules, assess, trace
from ecc_architecture.drafting import draft_input, figures, validate_drafts
from ecc_architecture.review import evaluate, record_feedback, report, run

REPO = Path(__file__).resolve().parents[3]
CONFIG = str(REPO / "config" / "product.toml")
CTX = context_for("architecture", CONFIG)
ADIR = CTX.path("arch_dir")
LABELS = json.loads((ADIR / "labels.json").read_text(encoding="utf-8"))
GATES = CTX.gates


def cli_main(argv):
    """The ecc command, with the use case's arguments placed after the product config."""
    return ecc(["--config", CONFIG, *argv])


@pytest.fixture(scope="module")
def inp():
    return ArchitectureInputs.load(ADIR)


@pytest.fixture(scope="module")
def a(inp):
    return assess(inp)


def _mock(inp, a):
    di = draft_input(inp, a)
    return MockDrafter().draft_architecture(di), di


# ------------------------------------------------------------------ deterministic assessment

def test_assessment_matches_labels(a):
    assert {(c.pattern_id, c.nfr_id): c.status for c in a.cells} == \
           {(p, n): s for p, row in LABELS["assessment"].items() for n, s in row.items()}
    assert {o.pattern_id: o.status for o in a.options} == LABELS["option_status"]
    assert {o.pattern_id: o.adr_conflicts for o in a.options if o.adr_conflicts} == LABELS["adr_conflicts"]
    assert a.preferred == "PAT-A" and a.next_adr_id == LABELS["next_adr_id"]
    assert sorted(q.id for q in a.open_questions) == sorted(LABELS["open_questions"])


def test_figures_are_computed_in_code_and_cited(a):
    throughput = a.cell("PAT-A", "NFR-03")
    assert "1500/s per cell × 3 regions = 4500/s" in throughput.detail
    known = {e.id for e in a.evidence}
    assert all(set(o.evidence) <= known for o in a.options)
    assert all(q.evidence in known for q in a.open_questions)


def test_superseded_adr_is_not_a_conflict(a):
    pat_a = next(o for o in a.options if o.pattern_id == "PAT-A")
    assert pat_a.adr_conflicts == []          # PAT-A contradicts ADR-003, which is superseded


def test_rejected_option_condition(a):
    b = next(o for o in a.options if o.pattern_id == "PAT-B")
    assert b.fails_must == ["NFR-05"] and b.condition == "Viable only for a single-region launch"


def test_injection_flagged_and_secret_redacted(a):
    note = next(e for e in a.evidence if e.id in a.flagged_notes)
    assert "possible_prompt_injection" in note.flags and "secret_redacted" in note.flags
    assert not any("sk-test" in e.summary for e in a.evidence)


def test_no_option_meets_must_nfrs(inp):
    only_bad = copy.deepcopy(inp)
    only_bad.patterns = [p for p in only_bad.patterns if p["id"] in ("PAT-B", "PAT-C")]
    a = assess(only_bad)
    assert a.preferred is None and "NO-OPTION" in {q.id for q in a.open_questions}
    assert all(t.status == "gap" for t in trace(only_bad, a, []))


# ------------------------------------------------------------------ drafts and validation

def test_mock_drafts_pass_validation_and_trace(inp, a):
    raw, di = _mock(inp, a)
    adr, stories, rejected = validate_drafts(raw, di)
    assert not rejected and adr.id == "ADR-007" and adr.chosen_option == "PAT-A" and not adr.disagrees_with_ranking
    assert {alt["option_id"] for alt in adr.alternatives} == {"PAT-B", "PAT-C", "PAT-D"}
    traces = trace(inp, a, stories)
    assert sorted(t.nfr_id for t in traces if t.status == "traced") == LABELS["traced_nfrs"]
    assert sorted(t.nfr_id for t in traces if t.status == "gap") == LABELS["gaps"]
    assert {c for s in stories for c in s.capability_ids} == {c["id"] for c in inp.requirement["capabilities"]}
    assert adr.status.startswith("proposed") and all(s.status.startswith("draft") for s in stories)


def test_figures_ignores_ids_and_normalises():
    assert figures("NFR-05, ADR-007, A12 and p99 under 300 ms; 2,000/s at 99.90%") == {"300", "2000", "99.9"}


@pytest.mark.parametrize("change, reason", [
    (lambda r: r["adr"].update(chosen_option="PAT-C"), "fails a must-have NFR"),
    (lambda r: r["adr"].update(chosen_option="PAT-Z"), "unknown option"),
    (lambda r: r["adr"]["alternatives"].pop(), "does not address alternative"),
    (lambda r: r["adr"].update(decision=r["adr"]["decision"] + " Cost is about 450000 per year."), "not in the evidence"),
    (lambda r: r["adr"].update(evidence=["A999"]), "no valid evidence"),
])
def test_validation_rejects_bad_adr(inp, a, change, reason):
    raw, di = _mock(inp, a)
    raw = copy.deepcopy(raw)
    change(raw)
    adr, _, rejected = validate_drafts(raw, di)
    assert adr is None and any(reason in r.reason for r in rejected)


def test_adr_citing_only_flagged_note_is_rejected(inp, a):
    raw, di = _mock(inp, a)
    raw = copy.deepcopy(raw)
    raw["adr"]["evidence"] = list(a.flagged_notes)
    adr, _, rejected = validate_drafts(raw, di)
    assert adr is None and "flagged" in rejected[0].reason


def test_choosing_a_viable_non_preferred_option_is_flagged_not_rejected(inp, a):
    raw, di = _mock(inp, a)
    raw = copy.deepcopy(raw)
    raw["adr"]["chosen_option"] = "PAT-D"
    raw["adr"]["alternatives"] = [{"option_id": p, "why_not": "Weaker fit.", "evidence": ["A13"]} for p in ("PAT-A", "PAT-B", "PAT-C")]
    adr, _, rejected = validate_drafts(raw, di)
    assert not rejected and adr.disagrees_with_ranking


def test_validation_rejects_bad_stories(inp, a):
    raw, di = _mock(inp, a)
    good = raw["stories"][1]                                        # points accrual, quotes 4 numeric targets
    bad = [dict(good, nfr_ids=["NFR-99"]),                          # unknown NFR
           dict(good, acceptance_criteria=["Accrual is fast"]),     # targets not stated
           dict(good, acceptance_criteria=good["acceptance_criteria"] + ["Handles 9000 accruals per second"]),  # invented
           dict(good, acceptance_criteria=[]),                      # no criteria
           dict(good, capability_ids=[], nfr_ids=[]),               # traces to nothing
           good, dict(good)]                                        # duplicate
    _, stories, rejected = validate_drafts({"adr": None, "stories": bad}, di)
    assert len(stories) == 1 and len(rejected) == 6
    assert any(r.invented_figures == ["9000"] for r in rejected)


# ------------------------------------------------------------------ run, review, evaluate

def test_run_feedback_report_and_evaluate(inp, tmp_path):
    result = run(inp, MockDrafter(), tmp_path)
    pack = (tmp_path / "proposal" / "REQ-LOY-001.md").read_text(encoding="utf-8")
    assert "Nothing has been written to the ADR repository or the backlog" in pack and "9 of 11" in pack
    record_feedback(tmp_path, "ADR-007", True, "arb.chair")
    record_feedback(tmp_path, "STORY-01", False, "po.loyalty")
    rep = report(tmp_path)
    assert rep["adr_decision"] == "approved" and rep["story_acceptance_rate"] == 0.0 and rep["decisions_made_by_agent"] == 0
    with pytest.raises(ValueError):
        record_feedback(tmp_path, "STORY-99", True, "po.loyalty")
    ev = evaluate(result, LABELS, GATES)
    assert ev["passed"] and ev["metrics"]["assessment_accuracy"] == 1.0 and ev["metrics"]["invented_figures"] == 0


def test_claude_drafter_request_shape(inp, a):
    raw, di = _mock(inp, a)
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(raw))], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="claude-opus-5-5")

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert ClaudeArchitect(ClaudeClient(client=client)).draft_architecture(di) == raw
    assert calls["model"] == "claude-opus-5-5" and calls["output_config"]["format"]["type"] == "json_schema"
    assert "architecture decision record" in calls["system"].lower()
    assert "possible_prompt_injection" in calls["messages"][0]["content"]      # the model is told the note is flagged
    assert "<evidence_records>" in calls["messages"][0]["content"] and "sk-test" not in calls["messages"][0]["content"]


def test_cli_architecture(tmp_path, capsys):
    w = str(tmp_path / "arch")
    assert cli_main(["architecture", "--workdir", w, "evaluate"]) == 0
    assert cli_main(["architecture", "--workdir", w, "feedback", "ADR-007", "--accept", "yes", "--by", "arb.chair"]) == 0
    assert cli_main(["architecture", "--workdir", w, "feedback", "ADR-001", "--accept", "yes", "--by", "x"]) == 2
    assert "Architecture evaluation" in capsys.readouterr().out


# ------------------------------------------------------------------ container diagram

def _traces(inp, a):
    raw, di = _mock(inp, a)
    _, stories, _ = validate_drafts(raw, di)
    return trace(inp, a, stories)


def test_container_diagram_from_pattern(inp, a):
    from ecc_architecture import container_diagram
    traces = _traces(inp, a)
    d = container_diagram(inp.pattern("PAT-A"), inp.requirement["regions"], traces)
    assert d.components == LABELS["diagram_components"] and not d.issues
    assert d.nfrs_shown == LABELS["traced_nfrs"]                      # picture and traceability agree
    assert d.mermaid.startswith("flowchart TB")
    assert 'subgraph cell["Cell per region: EU, US, APAC"]' in d.mermaid
    assert "loyalty_ledger -->|ledger events| event_bus" in d.mermaid
    assert "NFR-03 · NFR-04 · NFR-08" in d.mermaid                    # ledger carries throughput, RPO, idempotency


def test_container_diagram_reports_inconsistencies(inp, a):
    from ecc_architecture import container_diagram
    p = copy.deepcopy(inp.pattern("PAT-A"))
    p["connections"].append(["API gateway", "Mainframe", "batch"])
    d = container_diagram(p, inp.requirement["regions"], _traces(inp, a))
    assert any("Mainframe" in i for i in d.issues) and "mainframe" not in d.mermaid
    assert container_diagram(inp.pattern("PAT-B"), ["EU"], []) is None    # no components defined


# ------------------------------------------------------------------ requirement document intake

DOC = ADIR / "requirement-document.md"


def test_document_extracts_to_the_structured_requirement():
    from ecc_architecture.intake import MockExtractor, extract
    ex = extract(DOC, MockExtractor())
    want = json.loads((ADIR / "requirement.json").read_text(encoding="utf-8"))
    got = ex.requirement
    assert not ex.rejected and got["source"]["status"].startswith("extracted")
    for key in ("id", "title", "sponsor", "as_of", "regions", "capabilities", "nfrs", "open_decisions"):
        assert got[key] == want[key], key
    assert "sk-test" not in json.dumps(got)                           # redacted before extraction
    assert {"secret_redacted", "possible_prompt_injection"} <= set(ex.flags)


@pytest.mark.parametrize("category, text, expected", [
    ("availability", "99.95%", (99.95, "%")),
    ("latency_p99", "0.3 s", (300, "ms")),
    ("rpo", "5 minutes", (300, "s")),
    ("throughput", "2,000 orders/s", (2000, "orders/s")),
    ("residency", "EU and Thailand", (["EU", "Thailand"], "")),
    ("audit", "Required", (True, "")),
    ("cost", "TBD", (None, "USD/month")),
])
def test_parse_target(category, text, expected):
    from ecc_architecture.intake import parse_target
    assert parse_target(category, text) == expected


def test_extraction_validation_rejects_unsupported_items():
    from ecc_architecture.intake import MockExtractor, read_document, validate_extraction
    inp = read_document(DOC)
    raw = MockExtractor().extract_requirement(inp)
    raw["nfrs"][0]["target_text"] = "99.99%"                           # not what the document says
    raw["nfrs"][1]["quote"] = "| p99 latency | Must | 150 ms |"        # quote not in the document
    raw["nfrs"][2]["category"] = "vibes"                              # not a known category
    raw["capabilities"].append({"name": "Crypto rewards", "related_nfrs": [], "quote": "Crypto rewards"})
    ex = validate_extraction(raw, inp)
    assert len(ex.rejected) >= 4
    assert [n["name"] for n in ex.requirement["nfrs"]][:2] == ["Ledger recovery point (RPO)", "Data residency"]
    assert "Crypto rewards" not in {c["name"] for c in ex.requirement["capabilities"]}


def test_unsupported_document_type(tmp_path):
    from ecc_architecture.intake import read_document
    (tmp_path / "req.docx").write_bytes(b"PK")
    with pytest.raises(ValueError, match="Markdown or plain-text"):
        read_document(tmp_path / "req.docx")


def test_claude_extractor_request_shape():
    from ecc_architecture.intake import MockExtractor, read_document
    inp = read_document(DOC)
    raw = MockExtractor().extract_requirement(inp)
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(raw))], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="claude-opus-5-5")

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    assert ClaudeArchitect(ClaudeClient(client=client)).extract_requirement(inp) == raw
    user = calls["messages"][0]["content"]
    assert calls["output_config"]["format"]["schema"]["required"][0] == "id"
    assert "<document" in user and "possible_prompt_injection" in user and "sk-test" not in user


def test_cli_from_requirement_document(tmp_path, capsys):
    w = str(tmp_path / "doc")
    assert cli_main(["architecture", "--workdir", w, "ingest", str(DOC)]) == 0
    assert cli_main(["architecture", "--workdir", w, "evaluate", "--requirement-doc", str(DOC)]) == 0
    pack = (tmp_path / "doc" / "proposal" / "REQ-LOY-001.md").read_text(encoding="utf-8")
    assert "Requirement extracted from **requirement-document.md**" in pack and "```mermaid" in pack
    assert (tmp_path / "doc" / "proposal" / "REQ-LOY-001-container.mmd").exists()
    assert "Gates: **PASS**" in capsys.readouterr().out


# ------------------------------------------------------------------ proposal page

def test_proposal_page_is_written_and_escaped(inp, tmp_path):
    from ecc_architecture.html import proposal_html
    result = run(inp, MockDrafter(), tmp_path)
    page = (tmp_path / "proposal" / "REQ-LOY-001.html").read_text(encoding="utf-8")
    assert page.startswith("<!doctype html>") and '<pre class="mermaid">flowchart TB' in page
    assert "mermaid@10.9.1" in page and "Container view · PAT-A" in page and "9 of 11 NFRs traced" in page
    assert "&lt;br/&gt;" in page                                     # diagram source escaped, decoded by the renderer
    hostile = copy.deepcopy(inp.requirement)
    hostile["title"] = "<script>alert(1)</script>"
    assert "<script>alert(1)</script>" not in proposal_html(result, hostile)


# ------------------------------------------------------------------ configuration

def test_margins_come_from_the_product_configuration(inp):
    s = CTX.settings
    assert Rules(s["availability_margin"], s["latency_margin"], s["throughput_margin"]) == Rules()
    strict = assess(inp, Rules(availability_margin=0.0, latency_margin=1.0, throughput_margin=1.0))
    assert strict.cell("PAT-B", "NFR-01").status == "fails"       # 99.9 vs 99.95 is no longer "at risk"
    assert strict.cell("PAT-D", "NFR-03").status == "fails"       # 1800/s vs 2000/s likewise
