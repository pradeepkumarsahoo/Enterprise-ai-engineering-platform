# Author: Pradeep Sahoo
"""Read-only ServiceNow connector (REST Table API), shared by any use case.

Two transports behind one `get(table, query, fields)` method:
- "http":    GET https://<instance>/api/now/table/<table> with basic auth or a bearer token from
             environment variables. Pages through results up to max_records.
- "fixture": the same records from JSON files shaped like Table API responses
             ({"result": [...]}), with the same encoded-query subset applied locally. Used with
             the dummy instance URL in the product configuration, in tests and in demos.

Read-only by construction: the class has no create, update or delete method, sends GET only,
and refuses tables outside READ_TABLES. Credentials come from environment variables named in
[connectors.servicenow]; they are never stored in the configuration file.

Values are requested with sysparm_display_value=true, so reference fields (cmdb_ci,
assignment_group) arrive as names. Date-times are "YYYY-MM-DD HH:MM:SS"; set the integration
user's time zone to UTC so they can be read as UTC.
"""
from __future__ import annotations

import base64
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

READ_TABLES = frozenset({"incident", "change_request", "problem", "cmdb_rel_ci", "kb_knowledge"})
TRANSPORTS = ("fixture", "http")
SCHEMA = {"url": str, "transport": str, "fixture_dir": str, "user_env": str, "password_env": str,
          "token_env": str, "timeout_s": int, "page_size": int, "max_records": int}


class ServiceNowError(RuntimeError):
    pass


@dataclass(frozen=True)
class ServiceNowSettings:
    url: str = "https://dev00000.service-now.com"     # dummy instance
    transport: str = "fixture"
    fixture_dir: Path | None = None
    user_env: str = "ECC_SERVICENOW_USER"
    password_env: str = "ECC_SERVICENOW_PASSWORD"
    token_env: str = "ECC_SERVICENOW_TOKEN"
    timeout_s: int = 30
    page_size: int = 100
    max_records: int = 500


# ------------------------------------------------------------------ encoded queries

_TERM = re.compile(r"^(?P<field>[a-z_][a-z0-9_.]*)(?P<op>>=|<=|!=|=|>|<|IN|STARTSWITH|LIKE)(?P<value>.*)$")


def parse_query(query: str) -> list[tuple[str, str, str]]:
    """The subset of ServiceNow encoded queries used here: terms joined by ^ (AND)."""
    terms = []
    for raw in filter(None, (query or "").split("^")):
        m = _TERM.match(raw.strip())
        if not m:
            raise ServiceNowError(f"Unsupported query term: {raw!r} (use field=value, !=, >=, <=, >, <, IN, "
                                  "STARTSWITH or LIKE joined by ^)")
        terms.append((m["field"], m["op"], m["value"]))
    return terms


def matches(record: dict, terms: list[tuple[str, str, str]]) -> bool:
    for field, op, value in terms:
        v = str(record.get(field, ""))
        ok = {"=": v == value, "!=": v != value, ">=": v >= value, "<=": v <= value, ">": v > value, "<": v < value,
              "IN": v in value.split(","), "STARTSWITH": v.startswith(value), "LIKE": value.lower() in v.lower()}[op]
        if not ok:
            return False
    return True


# ------------------------------------------------------------------ client

class ServiceNowClient:
    """Read-only. get() is the only data method."""

    def __init__(self, settings: ServiceNowSettings, opener=None):
        if settings.transport not in TRANSPORTS:
            raise ServiceNowError(f"transport must be one of {', '.join(TRANSPORTS)}")
        if settings.transport == "fixture" and not settings.fixture_dir:
            raise ServiceNowError("transport 'fixture' needs fixture_dir")
        self.settings = settings
        self._open = opener or urllib.request.urlopen
        self.calls: list[str] = []          # tables read, for the audit log

    @property
    def instance(self) -> str:
        return urllib.parse.urlparse(self.settings.url).netloc or self.settings.url

    def get(self, table: str, query: str = "", fields: tuple[str, ...] = ()) -> list[dict]:
        if table not in READ_TABLES:
            raise PermissionError(f"table not allow-listed for reading: {table}")
        terms = parse_query(query)          # validate before any call
        self.calls.append(table)
        rows = self._fixture(table, terms) if self.settings.transport == "fixture" else self._http(table, query, fields)
        rows = rows[: self.settings.max_records]
        return [{f: r.get(f, "") for f in fields} for r in rows] if fields else rows

    def _fixture(self, table: str, terms) -> list[dict]:
        path = Path(self.settings.fixture_dir) / f"{table}.json"
        if not path.exists():
            return []
        return [r for r in json.loads(path.read_text(encoding="utf-8"))["result"] if matches(r, terms)]

    def _headers(self) -> dict:
        s = self.settings
        headers = {"Accept": "application/json", "User-Agent": "engineering-command-centre/0.2"}
        token = os.environ.get(s.token_env)
        user, password = os.environ.get(s.user_env), os.environ.get(s.password_env)
        if token:
            headers["Authorization"] = f"Bearer {token}"
        elif user and password:
            headers["Authorization"] = "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()
        else:
            raise ServiceNowError(f"No ServiceNow credentials: set {s.token_env}, or {s.user_env} and {s.password_env}")
        return headers

    def _http(self, table: str, query: str, fields: tuple[str, ...]) -> list[dict]:
        s, out, offset = self.settings, [], 0
        headers = self._headers()
        while len(out) < s.max_records:
            params = {"sysparm_query": query, "sysparm_limit": str(min(s.page_size, s.max_records - len(out))),
                      "sysparm_offset": str(offset), "sysparm_display_value": "true",
                      "sysparm_exclude_reference_link": "true"}
            if fields:
                params["sysparm_fields"] = ",".join(fields)
            url = f"{s.url.rstrip('/')}/api/now/table/{table}?{urllib.parse.urlencode(params)}"
            req = urllib.request.Request(url, headers=headers, method="GET")
            try:
                with self._open(req, timeout=s.timeout_s) as resp:
                    page = json.loads(resp.read().decode("utf-8")).get("result", [])
            except OSError as exc:            # URLError, HTTPError, timeouts
                raise ServiceNowError(f"ServiceNow request to {self.instance} failed: {exc}") from exc
            out += page
            if len(page) < int(params["sysparm_limit"]):
                break
            offset += len(page)
        return out
