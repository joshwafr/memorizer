from app.models import Source, Review


def _seed(client, db):
    client.post("/capture", json={"url": "https://youtu.be/cardmgmt1234"})
    return db.query(Source).one()


def test_list_cards_statuses(client, db):
    src = _seed(client, db)
    r = client.get("/cards")
    assert r.status_code == 200
    cards = r.json()
    assert len(cards) == 2
    assert all(c["status"] == "inbox" for c in cards)
    client.post(f"/sources/{src.id}/approve")
    cards = client.get("/cards").json()
    assert all(c["status"] == "learning" and c["due_at"] for c in cards)


def test_edit_card(client, db):
    _seed(client, db)
    cid = client.get("/cards").json()[0]["id"]
    r = client.patch(f"/cards/{cid}", json={"question": "New Q?", "answer": "New A"})
    assert r.status_code == 200
    assert r.json()["question"] == "New Q?"
    assert client.get("/cards").json()[0]["answer"] == "New A"


def test_suspend_and_resume_card(client, db):
    src = _seed(client, db)
    client.post(f"/sources/{src.id}/approve")
    cid = client.get("/cards").json()[0]["id"]
    assert client.patch(f"/cards/{cid}", json={"suspended": True}).json()["status"] == "suspended"
    assert cid not in [c["id"] for c in client.get("/review/due").json()]
    assert client.patch(f"/cards/{cid}", json={"suspended": False}).json()["status"] == "learning"


def test_delete_card_with_reviews(client, db):
    src = _seed(client, db)
    client.post(f"/sources/{src.id}/approve")
    cid = client.get("/review/due").json()[0]["id"]
    client.post(f"/review/{cid}/answer", json={"answer": "x"})
    assert db.query(Review).count() == 1
    r = client.delete(f"/cards/{cid}")
    assert r.status_code == 200
    assert db.query(Review).count() == 0
    assert cid not in [c["id"] for c in client.get("/cards").json()]


def test_edit_missing_card_404(client):
    assert client.patch("/cards/9999", json={"question": "x"}).status_code == 404
    assert client.delete("/cards/9999").status_code == 404
