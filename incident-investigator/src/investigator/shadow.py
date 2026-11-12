"""Shadow mode: investigate live incidents alongside on-call engineers, without affecting them.

- New incidents arrive in an inbox directory (in production: a webhook from the
  incident tool writes them there, or an adapter polls it).
- Each one is investigated once. The result goes to a review queue (outbox)
  that the SRE lead reads. On-call is not paged and the ticket is not changed.
- Engineers record whether the investigation was useful and what the confirmed
  cause turned out to be. The shadow report compares the two.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import median

from .audit import AuditLog
from .investigator import investigate
from .policy import MODES
from .providers import Provider
from .render import investigation_md
from .replay import predicted_cause

BANNER = ("SHADOW MODE: for review only. On-call has not been notified and the incident ticket "
          "has not been changed. Record feedback with `investigator shadow feedback`.")


class ShadowRunner:
    def __init__(self, inbox: Path, workdir: Path, runbooks_path: Path):
        assert MODES["shadow"]["notify_on_call"] is False and MODES["shadow"]["write_ticket"] is False
        self.inbox, self.workdir, self.runbooks = Path(inbox), Path(workdir), runbooks_path
        self.outbox = self.workdir / "review-queue"
        self.state_path = self.workdir / "state.json"
        self.feedback_path = self.workdir / "feedback.jsonl"
        self.audit = AuditLog(self.workdir / "audit.jsonl")
        self.outbox.mkdir(parents=True, exist_ok=True)

    def _state(self) -> dict:
        return json.loads(self.state_path.read_text(encoding="utf-8")) if self.state_path.exists() else {"processed": {}}

    def process_new(self, provider: Provider) -> list[str]:
        state = self._state()
        done = []
        for path in sorted(self.inbox.glob("*.json")):
            inc_id = json.loads(path.read_text(encoding="utf-8"))["incident"]["id"]
            if inc_id in state["processed"]:
                continue
            inv = investigate(path, provider, "shadow", self.audit, self.runbooks)
            pred, conf = predicted_cause(inv)
            (self.outbox / f"{inc_id}.md").write_text(investigation_md(inv, BANNER), encoding="utf-8")
            (self.outbox / f"{inc_id}.json").write_text(json.dumps(inv.to_dict(), indent=2), encoding="utf-8")
            self.audit.record("agent:incident-investigator", "shadow.queued_for_review", inc_id, inv.correlation_id,
                              destination="review-queue", notified_on_call=False)
            state["processed"][inc_id] = {"predicted": pred, "confidence": conf, "agent_seconds": inv.duration_s,
                                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            done.append(inc_id)
        self.state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        return done

    def record_feedback(self, incident_id: str, useful: bool, confirmed_cause: str | None, by: str,
                        engineer_minutes: int | None = None, note: str = "") -> dict:
        if incident_id not in self._state()["processed"]:
            raise ValueError(f"{incident_id} has not been investigated in shadow mode")
        entry = {"incident_id": incident_id, "useful": useful, "confirmed_cause": confirmed_cause, "by": by,
                 "engineer_minutes_to_first_hypothesis": engineer_minutes, "note": note,
                 "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        with self.feedback_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        self.audit.record(by, "shadow.feedback", incident_id, "-", useful=useful, confirmed_cause=confirmed_cause)
        return entry

    def report(self) -> dict:
        state = self._state()["processed"]
        fb = {}
        if self.feedback_path.exists():
            for line in self.feedback_path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    e = json.loads(line)
                    fb[e["incident_id"]] = e      # latest feedback wins
        rated = [i for i in state if i in fb]
        confirmed = [i for i in rated if fb[i]["confirmed_cause"]]
        eng = [fb[i]["engineer_minutes_to_first_hypothesis"] for i in rated
               if fb[i].get("engineer_minutes_to_first_hypothesis") is not None]
        executed = [e for e in self.audit.entries() if e["action"].startswith("action.execute")]
        notified = [e for e in self.audit.entries() if e.get("detail", {}).get("notified_on_call")]
        return {
            "investigated": len(state),
            "with_feedback": len(rated),
            "useful_rate": round(sum(fb[i]["useful"] for i in rated) / len(rated), 3) if rated else None,
            "agreement_with_confirmed_cause": (round(sum(state[i]["predicted"] == fb[i]["confirmed_cause"] for i in confirmed)
                                                     / len(confirmed), 3) if confirmed else None),
            "median_agent_seconds": round(median(s["agent_seconds"] for s in state.values()), 3) if state else None,
            "median_engineer_minutes": median(eng) if eng else None,
            "actions_executed": len(executed),
            "on_call_notifications": len(notified),
            "incidents": {i: {**state[i], "feedback": fb.get(i)} for i in state},
        }
