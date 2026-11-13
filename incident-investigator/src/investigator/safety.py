# Author: Pradeep Sahoo
"""Treat operational text as untrusted data.

Two jobs, both done in code before anything reaches a model:
1. Redact secrets so they are never sent to a provider or written to reports.
2. Flag text that looks like instructions (prompt injection). Flagged text is
   still shown as evidence, but it is marked, and the model is told it is data.
"""
from __future__ import annotations

import re

_SECRET_PATTERNS = [
    # key=value or key: value where the key name suggests a secret
    re.compile(r"(?i)\b([a-z0-9_.-]*(password|passwd|secret|token|api[_-]?key|access[_-]?key)[a-z0-9_.-]*)\s*[=:]\s*([^\s,;]+)"),
    # common credential shapes
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),                         # AWS access key id
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),                     # generic sk- style API keys
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
]

_INJECTION_PATTERNS = [
    re.compile(r"(?i)ignore (all |any )?(previous|prior|above) (instructions|prompts?)"),
    re.compile(r"(?i)disregard (the )?(system|previous) (prompt|instructions)"),
    re.compile(r"(?i)\byou are now\b"),
    re.compile(r"(?i)\b(system|assistant)\s*:\s"),
    re.compile(r"(?i)\b(mark|close) (this|the) incident\b"),
    re.compile(r"(?i)\brestart all\b"),
]


def redact(text: str) -> tuple[str, bool]:
    """Return (redacted_text, was_anything_redacted)."""
    changed = False

    def _kv(m: re.Match) -> str:
        nonlocal changed
        changed = True
        return f"{m.group(1)}=[REDACTED]"

    out = _SECRET_PATTERNS[0].sub(_kv, text)
    for pat in _SECRET_PATTERNS[1:]:
        out, n = pat.subn("[REDACTED]", out)
        changed = changed or n > 0
    return out, changed


def looks_like_injection(text: str) -> bool:
    return any(p.search(text) for p in _INJECTION_PATTERNS)


def clean(text: str) -> tuple[str, list[str]]:
    """Redact and flag in one step. Returns (text, flags)."""
    flags: list[str] = []
    text, redacted = redact(text)
    if redacted:
        flags.append("secret_redacted")
    if looks_like_injection(text):
        flags.append("possible_prompt_injection")
    return text, flags
