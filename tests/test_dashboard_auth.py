import os

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture(autouse=True)
def _clear_dashboard_cookie():
    # Ensure no cross-test cookie bleed.
    yield


def test_dashboard_fail_closed_when_token_missing(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("DASHBOARD_TOKEN", raising=False)
    client = TestClient(app)

    resp = client.get("/dashboard")
    assert resp.status_code == 503

    resp = client.get("/central")
    assert resp.status_code == 503

    resp = client.get("/api/analytics/ip-geo")
    assert resp.status_code == 503

    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 503

    resp = client.get("/api/analytics/requests")
    assert resp.status_code == 503

    resp = client.get("/api/analytics/errors")
    assert resp.status_code == 503


def test_dashboard_requires_token_when_configured(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    client = TestClient(app)

    # Without token: 401
    resp = client.get("/dashboard")
    assert resp.status_code == 401

    resp = client.get("/central")
    assert resp.status_code == 401

    resp = client.get("/api/analytics/ip-geo")
    assert resp.status_code == 401

    resp = client.get("/api/analytics/summary")
    assert resp.status_code == 401

    resp = client.get("/api/analytics/requests")
    assert resp.status_code == 401

    resp = client.get("/api/analytics/errors")
    assert resp.status_code == 401


def test_dashboard_token_query_sets_cookie(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    client = TestClient(app)

    resp = client.get("/dashboard?token=secret", follow_redirects=False)
    assert resp.status_code == 303
    assert "set-cookie" in resp.headers

    # Cookie should allow access without query/header.
    resp2 = client.get("/dashboard")
    assert resp2.status_code == 200


def test_dashboard_token_header_allows_api(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DASHBOARD_TOKEN", "secret")
    client = TestClient(app)

    resp = client.get("/api/analytics/ip-geo", headers={"x-dashboard-token": "secret"})
    assert resp.status_code == 200
    payload = resp.json()
    assert "ip_geo" in payload

    resp = client.get("/api/analytics/summary", headers={"x-dashboard-token": "secret"})
    assert resp.status_code == 200

    resp = client.get("/api/analytics/requests", headers={"x-dashboard-token": "secret"})
    assert resp.status_code == 200

    resp = client.get("/api/analytics/errors", headers={"x-dashboard-token": "secret"})
    assert resp.status_code == 200
