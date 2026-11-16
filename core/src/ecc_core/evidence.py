# Author: Pradeep Sahoo
"""The evidence record every use case cites.

Each use case numbers its own records (E1… incidents, K1… knowledge, A1…
architecture). The summary is always written by code, never by the model, and
every claim the model makes is checked against these IDs in code.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Evidence:
    id: str              # E1, K1, A1, ... stable within one run
    kind: str            # what the record is, e.g. deployment, runbook, nfr, assessment
    source: str          # which read-only source produced it
    summary: str         # computed in code; never written by the model
    flags: list[str] = field(default_factory=list)   # e.g. "possible_prompt_injection", "secret_redacted"
