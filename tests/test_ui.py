def test_ui_serves_index(client):
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "Memorizer" in r.text
