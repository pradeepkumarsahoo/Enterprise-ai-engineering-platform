"""Read-only data adapters.

The investigator only talks to sources through `IncidentSource`. Every method is
a read. There is deliberately no write, restart, rollback or notify method on
this interface, so no code path in the investigator can change a system.

`FixtureSource` reads the synthetic JSON files. A production deployment would
add adapters for the real tools (deploy pipeline, Prometheus, log search, the
runbook wiki) behind the same interface, using read-only credentials.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol


class IncidentSource(Protocol):
    def incident(self) -> dict: ...
    def deploys(self) -> list[dict]: ...
    def metrics(self) -> dict[str, dict]: ...
    def logs(self) -> list[dict]: ...
    def flag_changes(self) -> list[dict]: ...
    def dependency_status(self) -> list[dict]: ...


class Runbooks(Protocol):
    def search(self, service: str, text: str) -> list[dict]: ...


READ_ONLY_TOOLS = frozenset({
    "incident.read", "deploys.list", "metrics.query", "logs.search",
    "flags.history", "dependencies.status", "runbooks.search",
})


class FixtureSource:
    """One incident file. Labels (ground truth) live in a separate file and are never read here."""

    def __init__(self, path: Path, on_call=None):
        self._data = json.loads(Path(path).read_text(encoding="utf-8"))
        self._src = self._data.get("sources", {})
        self._on_call = on_call or (lambda tool: None)

    def _use(self, tool: str):
        if tool not in READ_ONLY_TOOLS:      # defensive: the allow-list is the policy
            raise PermissionError(f"tool not allow-listed: {tool}")
        self._on_call(tool)

    def incident(self) -> dict:
        self._use("incident.read")
        return self._data["incident"]

    def deploys(self) -> list[dict]:
        self._use("deploys.list")
        return list(self._src.get("deploys", []))

    def metrics(self) -> dict[str, dict]:
        self._use("metrics.query")
        return dict(self._src.get("metrics", {}))

    def logs(self) -> list[dict]:
        self._use("logs.search")
        return list(self._src.get("logs", []))

    def flag_changes(self) -> list[dict]:
        self._use("flags.history")
        return list(self._src.get("flag_changes", []))

    def dependency_status(self) -> list[dict]:
        self._use("dependencies.status")
        return list(self._src.get("dependency_status", []))


class FixtureRunbooks:
    def __init__(self, path: Path):
        self._books = json.loads(Path(path).read_text(encoding="utf-8"))

    def search(self, service: str, text: str) -> list[dict]:
        text = text.lower()
        hits = []
        for rb in self._books:
            kw = sum(1 for k in rb["keywords"] if k in text)
            if kw and (service in rb["services"] or kw >= 2):
                hits.append((kw, rb))
        return [rb for _, rb in sorted(hits, key=lambda x: -x[0])][:2]
