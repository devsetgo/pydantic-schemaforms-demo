import pytest
from fastapi.testclient import TestClient

from src.main import app


client = TestClient(app)

DASHBOARD_RELATED_PATHS = [
    "/dashboard",
    "/central",
    "/api/analytics/ip-geo",
    "/api/analytics/summary",
    "/api/analytics/requests",
    "/api/analytics/errors",
    "/dashboard/ip-modal/00000000-0000-0000-0000-000000000000",
]


@pytest.mark.parametrize("path", DASHBOARD_RELATED_PATHS)
def test_dashboard_and_analytics_routes_not_exposed(path: str):
    """The synced v26.2.3 demo app currently does not expose dashboard/analytics routes."""
    resp = client.get(path)
    assert resp.status_code == 404


def test_dashboard_and_analytics_post_routes_not_exposed():
    resp = client.post("/api/analytics/purge")
    assert resp.status_code == 404
