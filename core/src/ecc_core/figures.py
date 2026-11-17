# Author: Pradeep Sahoo
"""The invented-figures check, shared by every use case that lets a model draft text.

A figure in drafted text must appear in the evidence the model was given. IDs such as NFR-05,
ADR-007, A12, C3 or p99 are not figures. Numbers are normalised: 2,000 -> 2000, 99.90 -> 99.9.
"""
from __future__ import annotations

import re

_IDS = re.compile(r"\b[A-Z]{1,5}-\d+\b|\b[A-Z]\d+\b|\bp\d+\b")      # NFR-05, ADR-007, A12, p99
_NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*")


def figures(text: str) -> set[str]:
    """Numbers in text, ignoring IDs. 2,000 -> 2000; 99.90 -> 99.9."""
    out = set()
    for n in _NUM.findall(_IDS.sub(" ", text)):
        n = n.replace(",", "")
        if "." in n:
            n = n.rstrip("0").rstrip(".")
        out.add(n)
    return out


def invented(text: str, allowed: set[str]) -> list[str]:
    """Figures in text that are not in allowed, smallest first."""
    return sorted(figures(text) - allowed, key=float)
