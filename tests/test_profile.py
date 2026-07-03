def test_get_profile_seeds_default(client):
    r = client.get("/profile")
    assert r.status_code == 200
    assert "EXCLUDE" in r.json()["text"]

def test_update_profile_bumps_version(client):
    client.get("/profile")
    r = client.put("/profile", json={"text": "Only semiconductors."})
    assert r.json()["version"] == 2
    assert client.get("/profile").json()["text"] == "Only semiconductors."
