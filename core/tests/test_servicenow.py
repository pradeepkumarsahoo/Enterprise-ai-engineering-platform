# Author: Pradeep Sahoo
"""Tests for the read-only ServiceNow connector: both transports, query subset, safety limits, config."""
import json
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from ecc_core.config import ConfigError, load_config
from ecc_core.servicenow import (ServiceNowClient, ServiceNowError, ServiceNowSettings, matches, parse_query)

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "shared-data" / "synthetic" / "servicenow"
CONFIG = REPO / "config" / "product.toml"


def fixture_client(**kw) -> ServiceNowClient:
    return ServiceNowClient(ServiceNowSettings(fixture_dir=FIXTURES, **kw))


# ------------------------------------------------------------------ queries and fixture transport

def test_query_subset():
    rec = {"priority": "2", "active": "false", "opened_at": "2026-08-04 09:14:00", "cmdb_ci": "membership-api"}
    assert matches(rec, parse_query("active=false^priorityIN1,2"))
    assert matches(rec, parse_query("opened_at>=2026-08-01 00:00:00^cmdb_ciSTARTSWITHmember"))
    assert not matches(rec, parse_query("priority=1"))
    with pytest.raises(ServiceNowError):
        parse_query("priority=1^ORpriority=2")              # OR is outside the supported subset


def test_fixture_reads_with_query_and_fields():
    rows = fixture_client().get("incident", "active=false^priorityIN1,2", ("number", "priority"))
    assert len(rows) == 8 and all(set(r) == {"number", "priority"} for r in rows)
    assert "INC0011002" not in {r["number"] for r in rows}  # the P3 vendor ticket is filtered out


def test_read_only_and_capped():
    client = fixture_client(max_records=3)
    assert len(client.get("incident")) == 3
    with pytest.raises(PermissionError):
        client.get("sys_user")                              # not on the read allow-list
    assert not any(hasattr(client, m) for m in ("post", "put", "patch", "delete", "create", "update", "insert"))


# ------------------------------------------------------------------ HTTP transport against a local Table API stub

class _TableAPI(BaseHTTPRequestHandler):
    requests: list = []

    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        type(self).requests.append({"path": url.path, "query": q, "auth": self.headers.get("Authorization")})
        table = url.path.rsplit("/", 1)[-1]
        rows = fixture_client(max_records=10_000).get(table, q.get("sysparm_query", ""))
        off, lim = int(q.get("sysparm_offset", 0)), int(q.get("sysparm_limit", 100))
        body = json.dumps({"result": rows[off: off + lim]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture()
def table_api():
    _TableAPI.requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _TableAPI)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def test_http_transport_pages_and_authenticates(table_api, monkeypatch):
    monkeypatch.setenv("ECC_SERVICENOW_USER", "ecc.reader")
    monkeypatch.setenv("ECC_SERVICENOW_PASSWORD", "s3cret")
    client = ServiceNowClient(ServiceNowSettings(url=table_api, transport="http", page_size=3))
    rows = client.get("incident", "active=false^priorityIN1,2", ("number", "cmdb_ci"))
    assert len(rows) == 8 and len(_TableAPI.requests) == 3        # 3 + 3 + 2
    first = _TableAPI.requests[0]
    assert first["path"] == "/api/now/table/incident" and first["auth"].startswith("Basic ")
    assert first["query"]["sysparm_fields"] == "number,cmdb_ci" and first["query"]["sysparm_display_value"] == "true"
    assert [r["query"]["sysparm_offset"] for r in _TableAPI.requests] == ["0", "3", "6"]


def test_http_prefers_token_and_needs_credentials(table_api, monkeypatch):
    for k in ("ECC_SERVICENOW_USER", "ECC_SERVICENOW_PASSWORD", "ECC_SERVICENOW_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    client = ServiceNowClient(ServiceNowSettings(url=table_api, transport="http"))
    with pytest.raises(ServiceNowError, match="No ServiceNow credentials"):
        client.get("incident")
    monkeypatch.setenv("ECC_SERVICENOW_TOKEN", "tok")
    client.get("problem")
    assert _TableAPI.requests[-1]["auth"] == "Bearer tok"


def test_http_failure_is_reported(monkeypatch):
    monkeypatch.setenv("ECC_SERVICENOW_TOKEN", "tok")
    client = ServiceNowClient(ServiceNowSettings(url="http://127.0.0.1:9", transport="http", timeout_s=2))
    with pytest.raises(ServiceNowError, match="failed"):
        client.get("incident")


# ------------------------------------------------------------------ configuration

def test_connector_comes_from_the_product_configuration():
    sn = load_config(CONFIG).servicenow
    assert sn.url == "https://dev00000.service-now.com" and sn.transport == "fixture" and sn.fixture_dir == FIXTURES


@pytest.mark.parametrize("edit, problem", [
    (lambda t: t.replace('transport = "fixture"', 'transport = "soap"'), "transport: not one of"),
    (lambda t: t.replace('url = "https://dev00000', 'url = "http://dev00000'), "must start with https://"),
    (lambda t: t.replace("max_records = 500", 'max_records = "all"'), "expected int"),
    (lambda t: t.replace("[connectors.servicenow]", "[connectors.jira]"), "unknown connector"),
])
def test_connector_config_errors(tmp_path, edit, problem):
    text = CONFIG.read_text(encoding="utf-8").replace('root = ".."', f'root = "{REPO.as_posix()}"')
    path = tmp_path / "product.toml"
    path.write_text(edit(text), encoding="utf-8")
    with pytest.raises(ConfigError, match=problem):
        load_config(path)
