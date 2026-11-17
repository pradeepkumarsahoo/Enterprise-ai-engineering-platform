# Author: Pradeep Sahoo
"""Tests for use case 4: change risk."""
import copy
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ecc_core.cli import main as ecc
from ecc_core.llm import ClaudeClient, fake_anthropic
from ecc_core.plugin import context_for

from ecc_change import ClaudeDrafter, MockDrafter, Rules, assess
from ecc_change.drafting import validate_conditions
from ecc_change.factors import similar_changes
from ecc_change.gate import decide, status
from ecc_change.review import assess_changes, backtest
from ecc_change.sources import ChangeInputs

REPO = Path(__file__).resolve().parents[3]
CONFIG = str(REPO / "config" / "product.toml")
CTX = context_for("change", CONFIG)
LABELS = json.loads((CTX.path("changesets_dir").parent / "labels.json").read_text(encoding="utf-8"))
RULES = Rules.from_settings(CTX.settings)


@pytest.fixture(scope="module")
def inp():
    return ChangeInputs.load(CTX.servicenow(), CTX.path("changesets_dir"), CTX.path("calendar"),
                             CTX.source("catalogue"), CTX.source("runbooks"))


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ factors and score

def test_rules_come_from_the_product_configuration():
    assert RULES == Rules()                         # the file matches the documented defaults
    assert CTX.settings["high_min"] == 7.0 and CTX.gates["recall_min"] == 0.8


def test_bands_match_labels(inp):
    assert {n: assess(inp, n, RULES).band for n in inp.changesets} == LABELS["bands"]


def test_v38_release_is_high_with_every_expected_factor(inp):
    a = assess(inp, "CHG0030601", RULES)
    assert a.score == 9.3 and a.band == "high"
    assert a.fired() == {"sensitive_config", "repeat_pattern", "migration_blocking", "contract_change", "coverage_gap",
                         "deploy_window", "recent_instability", "change_size"}
    assert {s.change for s in a.similar} == {"CHG0030411", "CHG0030488", "CHG0030502"}
    assert any("partner-gateway" in u for u in a.could_not_establish)          # no contract tests
    assert a.kpis["consumers"] == 4 and a.kpis["coverage_pct"] == 61 and a.kpis["files_changed"] == 23
    known = {e.id for e in a.evidence}
    assert all(f.evidence and set(f.evidence) <= known for f in a.factors)


def test_score_is_capped_and_weights_are_configurable(inp):
    heavy = replace(RULES, weight_sensitive_config=9.0)
    assert assess(inp, "CHG0030601", heavy).score == 10.0
    assert assess(inp, "CHG0030603", replace(RULES, weight_sensitive_config=0.0)).band == "low"


def test_capacity_cut_needs_a_large_cut(inp):
    assert "capacity_cut" in assess(inp, "CHG0030411", RULES).fired()           # 50 -> 10
    assert "capacity_cut" not in assess(inp, "CHG0030601", RULES).fired()       # 40 -> 25 is 38%
    assert "capacity_cut" not in assess(inp, "CHG0030415", RULES).fired()       # an increase


def test_freeze_and_runbook_rules(inp):
    frozen = copy.deepcopy(inp)
    frozen.changes["CHG0030602"]["start_date"] = "2026-11-27 07:00:00"          # inside the Black Friday freeze
    a = assess(frozen, "CHG0030602", RULES)
    assert {"freeze", "deploy_window"} <= a.fired()                               # also a Friday
    no_book = copy.deepcopy(inp)
    no_book.runbooks = [b for b in no_book.runbooks if "promotion-engine" not in b["services"]]
    assert "no_rollback" in assess(no_book, "CHG0030602", RULES).fired()
    stale = replace(RULES, runbook_stale_days=30)
    assert "no_rollback" in assess(inp, "CHG0030602", stale).fired()


def test_backtest_cannot_see_the_future(inp):
    # CHG0030411's incident opened after it started, so its own assessment knows nothing of it,
    a = assess(inp, "CHG0030411", RULES)
    assert not a.similar and "recent_instability" not in a.fired()
    # and a change assessed before INC0010987 opened cannot be matched to it.
    assert not similar_changes(inp, "CHG0030415", RULES, at("2026-08-04 09:10:00"))
    assert [s.incident for s in similar_changes(inp, "CHG0030415", RULES, at("2026-08-04 10:05:00"))] == ["INC0010987"]


def test_unknown_runbook_state_in_the_past_is_not_guessed(inp):
    # partner-gateway's runbooks were only validated in October, after this September change:
    # their state on the day is unknown, so the factor neither fires nor passes silently.
    early = assess(inp, "CHG0030520", RULES)                                     # 2026-09-02
    assert any("only later validation dates" in u for u in early.could_not_establish)
    assert "no_rollback" not in early.fired()


def test_assessment_id_changes_when_the_change_changes(inp):
    edited = copy.deepcopy(inp)
    edited.changesets["CHG0030603"]["coverage"]["changed_lines_pct"] = 95
    assert assess(inp, "CHG0030603", RULES).assessment_id != assess(edited, "CHG0030603", RULES).assessment_id


# ------------------------------------------------------------------ drafting

def test_mock_conditions_all_pass_validation(inp):
    for n in ("CHG0030601", "CHG0030602", "CHG0030603"):
        a = assess(inp, n, RULES)
        summary, conditions, rejected = validate_conditions(MockDrafter().draft_conditions(a), a)
        assert not rejected and summary
        assert {c.factor for c in conditions} <= a.fired() | {"release_policy"}
    canary = [c for c in conditions if c.factor == "release_policy"]
    assert canary and "300 ms" in canary[0].text                                 # membership-api SLO


def test_validation_rejects_bad_conditions(inp):
    a = assess(inp, "CHG0030601", RULES)
    raw = {"summary": "Risk is 9.3.", "conditions": [
        {"text": "Canary 35% for 45 min", "factor": "release_policy", "evidence": ["C15"]},     # invented figures
        {"text": "Freeze all deploys", "factor": "freeze", "evidence": ["C1"]},                 # factor did not fire
        {"text": "Ship the pool change alone", "factor": "sensitive_config", "evidence": ["C99"]},  # no evidence
        {"text": "Ship the pool change alone", "factor": "sensitive_config", "evidence": ["C4"]},
        {"text": "ship the pool change alone", "factor": "sensitive_config", "evidence": ["C4"]},  # duplicate
    ]}
    summary, conditions, rejected = validate_conditions(raw, a)
    assert summary == "Risk is 9.3." and len(conditions) == 1 and len(rejected) == 4
    assert rejected[0]["invented_figures"] == ["35", "45"]
    low = assess(inp, "CHG0030602", RULES)
    _, _, rej = validate_conditions({"summary": "", "conditions": [
        {"text": "Canary 5% for 30 min", "factor": "release_policy", "evidence": ["C1"]}]}, low)
    assert "did not fire" in rej[0]["reason"]                                    # no canary demand for a low score


def test_claude_drafter_request_shape(inp):
    a = assess(inp, "CHG0030601", RULES)
    calls = {}
    payload = MockDrafter().draft_conditions(a)
    assert ClaudeDrafter(ClaudeClient(client=fake_anthropic(payload, calls))).draft_conditions(a) == payload
    user = calls["messages"][0]["content"]
    assert '"score": 9.3' in user and "<evidence_records>" in user
    assert "never changes" not in calls["system"] and "do not set, change or argue" in calls["system"]


# ------------------------------------------------------------------ release gate

@pytest.fixture()
def assessed_dir(inp, tmp_path):
    assess_changes(inp, ["CHG0030601", "CHG0030603"], RULES, MockDrafter(), tmp_path)
    return tmp_path


def _a(workdir, n):
    return json.loads((workdir / "results.json").read_text(encoding="utf-8"))["assessments"][n]


def test_gate_rules(assessed_dir):
    high = _a(assessed_dir, "CHG0030601")
    with pytest.raises(ValueError, match="cannot approve it"):
        decide(high, assessed_dir, "dana.dev", "release-manager", True)            # the requester
    with pytest.raises(ValueError, match="agent"):
        decide(high, assessed_dir, "agent:change-risk-assessor", "release-manager", True)
    with pytest.raises(ValueError, match="cannot approve releases"):
        decide(high, assessed_dir, "kai.dev", "developer", True)
    assert decide(high, assessed_dir, "lee.lead", "release-manager", True)["gate"]["state"] == "awaiting 1 approver(s)"
    with pytest.raises(ValueError, match="already decided"):
        decide(high, assessed_dir, "lee.lead", "release-manager", True)
    assert decide(high, assessed_dir, "priya.sre", "sre-lead", True)["gate"]["state"] == "approved"
    medium = _a(assessed_dir, "CHG0030603")
    assert decide(medium, assessed_dir, "lee.lead", "engineering-lead", False)["gate"]["state"] == "rejected"


def test_reassessment_resets_approvals(inp, assessed_dir):
    decide(_a(assessed_dir, "CHG0030603"), assessed_dir, "lee.lead", "release-manager", True)
    assert status(_a(assessed_dir, "CHG0030603"), assessed_dir)["state"] == "approved"
    edited = copy.deepcopy(inp)
    edited.changesets["CHG0030603"]["coverage"]["changed_lines_pct"] = 95
    assess_changes(edited, ["CHG0030603"], RULES, MockDrafter(), assessed_dir)
    assert status(_a(assessed_dir, "CHG0030603"), assessed_dir)["state"] == "awaiting 1 approver(s)"


def test_reports_are_written(assessed_dir):
    html = (assessed_dir / "reports" / "CHG0030601.html").read_text(encoding="utf-8")
    md = (assessed_dir / "reports" / "CHG0030601.md").read_text(encoding="utf-8")
    assert "9.3 / 10" in html and "Similar past changes" in html and "partner-gateway" in html
    assert "## Score: 9.3 / 10 · high" in md and "requester cannot approve" in md


# ------------------------------------------------------------------ backtest and CLI

def test_backtest_matches_labels_and_reports_the_miss(inp):
    r = backtest(inp, RULES, CTX.gates, LABELS)
    m = r["metrics"]
    assert m["band_match"] and m["outcome_match"]
    assert m["changes"] == 7 and m["recall"] == 0.75 and m["false_alarm_rate"] == 0.25
    assert m["missed"] == ["CHG0030530"] and m["false_alarms"] == ["CHG0030415"]
    assert not r["passed"] and "Missed: CHG0030530" in r["report_md"]


def test_cli_change(tmp_path, capsys):
    w = str(tmp_path / "c")
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "assess"]) == 0
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "approve", "CHG0030601", "--by", "lee.lead",
                "--role", "release-manager"]) == 0
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "approve", "CHG0030601", "--by", "dana.dev",
                "--role", "release-manager"]) == 2
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "approve", "CHG0099999", "--by", "x",
                "--role", "sre-lead"]) == 2
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "status"]) == 0
    assert ecc(["--config", CONFIG, "change", "--workdir", w, "backtest"]) == 1     # 3 of 4 < 80% gate
    out = capsys.readouterr().out
    assert "CHG0030601   loyalty-ledger       9.3  high" in out and "awaiting 1 approver(s)" in out
