# Author: Pradeep Sahoo
"""Read-only sources shared by more than one use case.

Runbooks are read by incident investigation (to cite them) and by knowledge &
runbooks (to check them). The location comes from `[sources]` in the product
configuration. In production this is the runbook wiki behind read-only
credentials; there is no write method.
"""
from __future__ import annotations

import json
from pathlib import Path


def load_runbooks(path: Path) -> list[dict]:
    """Read runbooks.json ({"_meta": ..., "runbooks": [...]}; a bare list is also accepted)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return data["runbooks"] if isinstance(data, dict) else data
