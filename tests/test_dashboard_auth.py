import pytest
from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)

DASHBOARD_GET_PATHS = [
    '/dashboard',
    '/central',
    '/api/analytics/ip-geo',
    '/api/analytics/summary',
    '/api/analytics/requests',
    '/api/analytics/errors',
    '/dashboard/ip-modal/00000000-0000-0000-0000-000000000000',
]


@pytest.fixture
def dashboard_token(monkeypatch):
    token = 'test-dashboard-token'
    monkeypatch.setenv('DASHBOARD_TOKEN', token)
    return token


@pytest.mark.parametrize('path', DASHBOARD_GET_PATHS)
def test_dashboard_routes_require_auth(path: str, dashboard_token):
    """Dashboard/analytics routes are exposed but reject unauthenticated requests."""
    resp = client.get(path)
    assert resp.status_code == 401


def test_dashboard_post_routes_require_auth(dashboard_token):
    resp = client.post('/api/analytics/purge')
    assert resp.status_code == 401


@pytest.mark.parametrize('path', DASHBOARD_GET_PATHS)
def test_dashboard_routes_fail_closed_without_token_configured(path: str, monkeypatch):
    """If DASHBOARD_TOKEN isn't configured, dashboards/APIs must not be public."""
    monkeypatch.delenv('DASHBOARD_TOKEN', raising=False)
    resp = client.get(path)
    assert resp.status_code == 503


def test_dashboard_summary_accessible_with_valid_token(dashboard_token):
    resp = client.get('/api/analytics/summary', headers={'X-Dashboard-Token': dashboard_token})
    assert resp.status_code == 200
    body = resp.json()
    assert 'total_requests' in body


def test_dashboard_page_accessible_with_valid_token(dashboard_token):
    # The HTML dashboard uses the query-token-to-cookie flow (redirects to a
    # clean URL after setting a cookie), not header auth like the JSON API.
    resp = client.get(f'/dashboard?token={dashboard_token}')
    assert resp.status_code == 200
