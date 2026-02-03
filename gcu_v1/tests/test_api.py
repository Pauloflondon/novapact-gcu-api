import re
import sys
import types
import pytest
import pytest_asyncio
import httpx

import gcu_v1.api.server as srv


def _install_fake_run_module(monkeypatch, *, run_id: str, confidence: float, status: str = "ok"):
    m = types.ModuleType("gcu_v1.api.run")

    def run_capability(*, capability, payload, manifest):
        return {
            "status": status,
            "run_id": run_id,
            "confidence": confidence,
            "classification": "non-risk",
        }

    m.run_capability = run_capability
    monkeypatch.setitem(sys.modules, "gcu_v1.api.run", m)


def _metrics_value(metrics_text: str, metric_name: str, labels: dict) -> float:
    label_str = ",".join([f'{k}="{v}"' for k, v in labels.items()])
    pattern = rf"^{re.escape(metric_name)}\{{{re.escape(label_str)}\}}\s+([0-9]+(?:\.[0-9]+)?)\s*$"
    for line in metrics_text.splitlines():
        m = re.match(pattern, line.strip())
        if m:
            return float(m.group(1))
    raise AssertionError(f"Metric not found: {metric_name}{{{label_str}}}")


def _normalize_outcome_label(status_value: str) -> str:
    s = (status_value or "").strip().lower()
    if "needs_review" in s:
        return "needs_review"
    if "approved" in s:
        return "approved"
    if "rejected" in s:
        return "rejected"
    if "error" in s:
        return "error"
    if "ok" in s:
        return "ok"
    return s or "unknown"


@pytest_asyncio.fixture
async def client(tmp_path, monkeypatch):
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"ok": true}', encoding="utf-8")
    monkeypatch.setenv("NP_MANIFEST_PATH", str(manifest))
    monkeypatch.setenv("NP_CAPABILITY", "np_document_triage")

    transport = httpx.ASGITransport(app=srv.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_run_ok_path_increments_outcome_ok(client, monkeypatch):
    monkeypatch.setenv("NP_CONFIDENCE_THRESHOLD", "0.75")

    run_id = "api-ok-1"
    _install_fake_run_module(monkeypatch, run_id=run_id, confidence=0.95, status="ok")

    r = await client.post("/run", json={
        "capability": "np_document_triage",
        "payload": {"text": "hello"},
        "actor": "system",
        "role": "auto",
        "auth_type": "api_key",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id

    m = await client.get("/metrics")
    assert m.status_code == 200
    outcome = _normalize_outcome_label(str(data["status"]))
    v = _metrics_value(m.text, "gcu_governance_outcome_total", {"outcome": outcome})
    assert v >= 1.0


@pytest.mark.asyncio
async def test_run_needs_review_path_increments_outcome_needs_review(client, monkeypatch):
    monkeypatch.setenv("NP_CONFIDENCE_THRESHOLD", "0.75")

    run_id = "api-review-1"
    _install_fake_run_module(monkeypatch, run_id=run_id, confidence=0.10, status="ok")

    r = await client.post("/run", json={
        "capability": "np_document_triage",
        "payload": {"text": "low confidence"},
        "actor": "system",
        "role": "auto",
        "auth_type": "api_key",
    })
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == run_id
    assert data.get("needs_review") is True

    m = await client.get("/metrics")
    assert m.status_code == 200
    outcome = _normalize_outcome_label(str(data["status"]))
    v = _metrics_value(m.text, "gcu_governance_outcome_total", {"outcome": outcome})
    assert v >= 1.0


@pytest.mark.asyncio
async def test_run_invalid_capability_returns_400(client):
    r = await client.post("/run", json={
        "capability": "wrong_capability",
        "payload": {"text": "x"},
        "actor": "system",
        "role": "auto",
        "auth_type": "api_key",
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_debug_audit_smoke(client, monkeypatch):
    monkeypatch.setenv("NP_CONFIDENCE_THRESHOLD", "0.75")

    run_id = "api-audit-1"
    _install_fake_run_module(monkeypatch, run_id=run_id, confidence=0.95, status="ok")

    r = await client.post("/run", json={
        "capability": "np_document_triage",
        "payload": {"text": "audit"},
        "actor": "system",
        "role": "auto",
        "auth_type": "api_key",
    })
    assert r.status_code == 200

    a = await client.get(f"/debug/audit/{run_id}")
    assert a.status_code == 200
    j = a.json()
    assert j["run_id"] == run_id
    assert j["count"] >= 1