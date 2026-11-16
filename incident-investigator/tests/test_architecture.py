# Author: Pradeep Sahoo
"""Tests for use case 3: architecture & ADLC."""
import copy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from investigator.architecture import ArchitectureInputs, MockDrafter, assess, trace
from investigator.architecture.drafting import draft_input, figures, validate_drafts
from investigator.architecture.review import evaluate, record_feedback, report, run
from investigator.cli import main as cli_main
from investigator.providers.claude import ClaudeProvider

HOME = Path(__file__).resolve().parents[1]
ADIR = HOME / "data" / "synthetic" / "architecture"
LABELS = json.loads((ADIR / "labels.json").read_text(encoding="utf-8"))
GATES = json.loads((HOME / "config" / "pilot_gates.json").read_text(encoding="utf-8"))["architecture"]


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
    assert ClaudeProvider(client=client).draft_architecture(di) == raw
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
