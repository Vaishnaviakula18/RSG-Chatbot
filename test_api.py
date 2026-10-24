"""HTTP-level tests. Skipped automatically if FastAPI/httpx are not installed."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import db
    path = tmp_path / "api.db"
    db.build_database(db.CSV_PATH, path)
    monkeypatch.setattr(db, "DB_PATH", path)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_ask_ok(client):
    r = client.post("/ask", json={"question": "What is the total revenue?"})
    assert r.status_code == 200 and r.json()["rows"][0]["revenue"] == 1439200


def test_ask_empty_is_400(client):
    assert client.post("/ask", json={"question": "  "}).status_code == 400


def test_ask_missing_field_is_422(client):
    assert client.post("/ask", json={}).status_code == 422


def test_meta(client):
    assert len(client.get("/api/meta").json()["rejected_records"]) == 3
