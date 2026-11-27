# Author: Pradeep Sahoo
"""Months and money as every FinOps text shows them (evidence, reports, the page).

One formatter matters for validation: a figure the model repeats must match the evidence exactly,
so evidence and drafts both go through `money` and `pct`.
"""
from __future__ import annotations

import calendar


def money(x: float) -> str:
    """Whole dollars: $22,900 or -$2,500."""
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def pct(x: float) -> str:
    """A ratio as a whole percentage: 0.33 -> 33%."""
    return f"{x * 100:.0f}%"


def month_label(m: str) -> str:
    """2026-10 -> Oct 2026."""
    return f"{calendar.month_abbr[int(m[5:])]} {m[:4]}"


def month_add(m: str, k: int) -> str:
    """2026-12 + 1 -> 2027-01."""
    y, mo = int(m[:4]), int(m[5:]) - 1 + k
    return f"{y + mo // 12}-{mo % 12 + 1:02d}"


def days_in(m: str) -> int:
    return calendar.monthrange(int(m[:4]), int(m[5:]))[1]


def day_label(d: str) -> str:
    """2026-10-03 -> 3 Oct 2026."""
    return f"{int(d[8:10])} {calendar.month_abbr[int(d[5:7])]} {d[:4]}"
