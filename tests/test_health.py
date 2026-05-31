from fastapi.testclient import TestClient

from app.main import create_app


def test_health_check_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "AI Literature Review Assistant API",
        "version": "0.1.0",
    }
