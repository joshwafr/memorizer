def test_ui_serves_index(client):
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "Memorizer" in r.text

def test_root_redirects_to_ui(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/ui/"

def test_root_redirect_exempt_from_auth(client, monkeypatch):
    monkeypatch.setenv("MEMORIZER_TOKEN", "sekret")
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (307, 308)
