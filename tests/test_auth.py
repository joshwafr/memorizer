TOKEN = "test-secret-token"


def test_no_token_env_all_routes_open(client, monkeypatch):
    monkeypatch.delenv("MEMORIZER_TOKEN", raising=False)
    assert client.get("/inbox").status_code == 200
    assert client.get("/review/due").status_code == 200
    assert client.get("/profile").status_code == 200


def test_missing_header_returns_401(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", TOKEN)
    r = client.get("/inbox")
    assert r.status_code == 401


def test_wrong_token_returns_401(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", TOKEN)
    r = client.get("/inbox", headers={"Authorization": "Bearer wrong"})
    assert r.status_code == 401


def test_correct_token_returns_200(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", TOKEN)
    r = client.get("/inbox", headers={"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200


def test_health_open_without_token(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", TOKEN)
    assert client.get("/health").status_code == 200


def test_ui_open_without_token(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", TOKEN)
    assert client.get("/ui/").status_code == 200
