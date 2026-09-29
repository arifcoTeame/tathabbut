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
        assert body["claims"][0]["verdict"] == {"code": "NOT_AUTHENTIC", "label_ar": "لا يصح"}
        assert body["summary"]["NOT_AUTHENTIC"] == 1
        assert client.post("/verify", json={"text": "ا" * 5000}).status_code == 413
