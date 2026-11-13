# Author: Pradeep Sahoo
"""Tests for use case 2: knowledge and runbooks."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from investigator.cli import main as cli_main
from investigator.knowledge import KnowledgeBase, MockDrafter, analyse
from investigator.knowledge.drafting import FIXABLE, EditInput, validate_edits
from investigator.knowledge.review import evaluate, record_feedback, report, run
from investigator.providers.claude import ClaudeProvider

HOME = Path(__file__).resolve().parents[1]
DATA = HOME / "data" / "synthetic"
KDIR = DATA / "knowledge"
LABELS = json.loads((KDIR / "labels.json").read_text(encoding="utf-8"))
GATES = json.loads((HOME / "config" / "pilot_gates.json").read_text(encoding="utf-8"))["knowledge"]


@pytest.fixture(scope="module")
def kb():
    return KnowledgeBase.load(DATA / "runbooks.json", KDIR)


# ------------------------------------------------------------------ deterministic checks

def test_findings_match_labels(kb):
    found = {(f.subject, f.kind) for f in analyse(kb).findings}
    assert found == {tuple(x) for x in LABELS["findings"]}


def test_every_finding_cites_existing_evidence(kb):
    a = analyse(kb)
    known = {e.id for e in a.evidence}
    assert all(f.evidence and set(f.evidence) <= known for f in a.findings)


def test_broken_reference_points_at_the_right_step(kb):
    f = next(f for f in analyse(kb).findings if f.subject == "RB-017" and f.kind == "broken_reference")
    assert f.step == 3 and f.data["removed"] == "MAX_POOL"


def test_repeat_cluster_and_overdue_actions(kb):
    a = analyse(kb)
    assert {r.cause_key: r.incidents for r in a.repeats} == LABELS["repeat_clusters"]
    assert sorted(o.id for o in a.overdue) == sorted(LABELS["overdue_actions"])
    assert sorted(o.id for o in a.overdue if o.on_repeat_cause) == sorted(LABELS["overdue_on_repeat"])
    assert a.overdue[0].on_repeat_cause            # recurring causes are listed first


def test_retired_team_work_routes_to_successor(kb):
    a = analyse(kb)
    assert all(f.owner_team != "Ledger Core" for f in a.findings)
    unowned = next(f for f in a.findings if f.kind == "unowned")
    assert unowned.data["proposed_owner"] == "Loyalty"


def test_recommendations_need_approval_for_ownership_and_new_runbooks(kb):
    recs = analyse(kb).recommendations
    assert all(r.requires_approval for r in recs if r.action_type in ("ownership.assign", "knowledge.create"))
    assert any(r.action_type == "escalate" and "PIA-311" in r.description for r in recs)


# ------------------------------------------------------------------ drafted edits

def _edit_input(kb):
    a = analyse(kb)
    fixable = [f for f in a.findings if f.kind in FIXABLE]
    books = [rb for rb in kb.runbooks if rb["id"] in {f.subject for f in fixable}]
    removed = {rb["id"]: {i["name"] for s in rb["services"] for i in kb.config_inventory.get(s, {}).get("removed", [])}
               for rb in books}
    return EditInput(fixable, a.evidence, books), removed


def test_mock_edits_all_pass_validation(kb):
    inp, removed = _edit_input(kb)
    edits, rejected = validate_edits(MockDrafter().draft_runbook_edits(inp), inp, removed, {})
    assert not rejected and len(edits) == 3
    assert all("MAX_POOL" not in e.proposed_text and "backup-vault-eu1" not in e.proposed_text for e in edits)
    assert all(e.status.startswith("draft") for e in edits)


def test_validation_rejects_bad_edits(kb):
    inp, removed = _edit_input(kb)
    step3 = "Raise MAX_POOL in the service environment and restart"
    bad = {"edits": [
        {"runbook_id": "RB-017", "step_number": 3, "change_type": "replace", "current_text": "Something else",
         "proposed_text": "x", "rationale": "", "evidence": ["K1"]},                       # misquoted
        {"runbook_id": "RB-017", "step_number": 3, "change_type": "replace", "current_text": step3,
         "proposed_text": "Raise MAX_POOL to 50", "rationale": "", "evidence": ["K1"]},     # still removed setting
        {"runbook_id": "RB-017", "step_number": 9, "change_type": "replace", "current_text": step3,
         "proposed_text": "y", "rationale": "", "evidence": ["K1"]},                       # no such step
        {"runbook_id": "RB-023", "step_number": 1, "change_type": "replace", "current_text": "Find the slowest statements",
         "proposed_text": "z", "rationale": "", "evidence": ["K1"]},                       # not part of findings
        {"runbook_id": "RB-017", "step_number": 3, "change_type": "replace", "current_text": step3,
         "proposed_text": "Raise hikari.maximum-pool-size", "rationale": "", "evidence": ["K999"]},  # no evidence
    ]}
    edits, rejected = validate_edits(bad, inp, removed, {})
    assert edits == [] and len(rejected) == 5


# ------------------------------------------------------------------ run, review, evaluate

def test_run_review_queue_feedback_and_report(kb, tmp_path):
    result = run(kb, MockDrafter(), tmp_path)
    files = {p.name for p in (tmp_path / "review-queue").glob("*.md")}
    assert files == {"membership-identity.md", "loyalty.md", "commerce.md", "platform.md"}
    assert "Nothing has been changed in the runbook wiki" in (tmp_path / "review-queue" / "loyalty.md").read_text(encoding="utf-8")
    edit_id = result["edits"][0]["id"]
    record_feedback(tmp_path, edit_id, True, "ria.owner")
    rep = report(tmp_path)
    assert rep["edits_reviewed"] == 1 and rep["acceptance_rate"] == 1.0 and rep["edits_published_by_agent"] == 0
    with pytest.raises(ValueError):
        record_feedback(tmp_path, "EDIT-NOPE", True, "ria.owner")


def test_evaluate_passes_gates(kb, tmp_path):
    ev = evaluate(run(kb, MockDrafter(), tmp_path), LABELS, GATES)
    assert ev["passed"] and ev["metrics"]["recall"] == 1.0 and ev["metrics"]["precision"] == 1.0


def test_claude_drafter_request_shape(kb):
    inp, removed = _edit_input(kb)
    payload = MockDrafter().draft_runbook_edits(inp)
    calls = {}

    def create(**kwargs):
        calls.update(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=json.dumps(payload))], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1), model="claude-opus-5-5")

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=create)))
    out = ClaudeProvider(client=client).draft_runbook_edits(inp)
    assert out == payload
    assert calls["model"] == "claude-opus-5-5" and calls["output_config"]["format"]["type"] == "json_schema"
    assert "runbook" in calls["system"].lower() and "<evidence_records>" in calls["messages"][0]["content"]


# ------------------------------------------------------------------ CLI smoke tests (both use cases)

def test_cli_end_to_end(tmp_path, capsys):
    assert cli_main(["replay", "--out", str(tmp_path / "replay")]) == 0
    assert cli_main(["knowledge", "--workdir", str(tmp_path / "k"), "evaluate"]) == 0
    assert cli_main(["shadow", "--workdir", str(tmp_path / "s"), "run"]) == 0
    assert cli_main(["shadow", "--workdir", str(tmp_path / "s"), "feedback", "INC-9999", "--useful", "yes", "--by", "x"]) == 2
    out = capsys.readouterr().out
    assert "Replay report" in out and "Knowledge evaluation" in out
