# Author: Pradeep Sahoo
"""Read-only sources shared by more than one use case.

Runbooks are read by incident investigation (to cite them) and by knowledge &
runbooks (to check them). `read_data` reads any data file that carries a `_meta`
block (author, generator), which readers ignore. The location comes from `[sources]` in the product
configuration. In production this is the runbook wiki behind read-only
credentials; there is no write method.
"""
from __future__ import annotations

import json
from pathlib import Path


def read_data(path: Path) -> dict:
    """A JSON data file without its `_meta` block."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data.pop("_meta", None)
    return data


def load_runbooks(path: Path) -> list[dict]:
    """Read runbooks.json ({"_meta": ..., "runbooks": [...]}; a bare list is also accepted)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["runbooks"] if isinstance(data, dict) else data
