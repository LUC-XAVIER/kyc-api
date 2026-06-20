"""Smoke tests for the health endpoint."""

from fastapi.testclient import TestClient


def test_health_ok(client: TestClient) -> None:
    """The health endpoint returns 200 and an ok status."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "KYC-API"
