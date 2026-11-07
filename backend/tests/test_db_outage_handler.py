"""数据库连不上时的统一错误：Neon 额度用尽 → 503 + 明确原因；普通异常仍是 500。"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.main import _database_outage_message, app

QUOTA_TEXT = (
    'connection is bad: connection to server at "35.175.165.141", port 5432 failed: '
    "ERROR:  Your account or project has exceeded the quota. Upgrade your plan to increase limits."
)


def test_database_outage_message_classifies_errors() -> None:
    quota = OperationalError("SELECT 1", {}, Exception(QUOTA_TEXT))
    assert "额度" in (_database_outage_message(quota) or "")
    refused = OperationalError("SELECT 1", {}, Exception("connection to server at \"1.2.3.4\", port 5432 failed: Connection refused"))
    assert "暂时无法连接" in (_database_outage_message(refused) or "")
    assert _database_outage_message(RuntimeError("boom")) is None
    assert _database_outage_message(OperationalError("INSERT", {}, Exception("duplicate key value violates unique constraint"))) is None


def test_quota_error_becomes_503_envelope() -> None:
    @app.get("/_test/db-quota")
    async def _quota() -> None:
        raise OperationalError("SELECT 1", {}, Exception(QUOTA_TEXT))

    @app.get("/_test/plain-error")
    async def _plain() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    res = client.get("/_test/db-quota")
    assert res.status_code == 503
    body = res.json()
    assert body["code"] == 503 and "Database quota exceeded" in body["message"] and body["data"] is None
    res = client.get("/_test/plain-error")
    assert res.status_code == 500 and res.json()["message"] == "Internal server error"
