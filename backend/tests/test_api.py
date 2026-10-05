from fastapi.testclient import TestClient


def test_api_verify(index, monkeypatch, tmp_path):
    index.save(tmp_path)
    from app import config

    monkeypatch.setattr(config.settings, "index_dir", tmp_path)
    from app.main import app

    with TestClient(app) as client:
        assert client.get("/health").json()["status"] == "ok"
        r = client.post("/verify", json={"text": "حب الوطن من الإيمان"})
        assert r.status_code == 200
        body = r.json()
        assert body["claims"][0]["verdict"] == {"code": "NOT_AUTHENTIC", "label_ar": "ضعيف أو موضوع بحسب الدرر السنية"}
        assert body["summary"]["NOT_AUTHENTIC"] == 1
        assert client.post("/verify", json={"text": "ا" * 5000}).status_code == 413
        assert client.post("/verify", json={"text": "   \n  "}).status_code == 422
        assert client.post("/verify", json={"text": "  ا  "}).status_code == 422


def test_health_accepts_head(index, monkeypatch, tmp_path):
    """Uptime monitors probe with HEAD; a 405 would be reported as downtime."""
    index.save(tmp_path)
    from app import config

    monkeypatch.setattr(config.settings, "index_dir", tmp_path)
    from app.main import app

    with TestClient(app) as client:
        assert client.head("/health").status_code == 200
        assert client.head("/").status_code == 200
