from app.models import Source

def _approved_source(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    src = db.query(Source).one()
    client.post(f"/sources/{src.id}/approve")
    return src

def test_due_queue_returns_approved_cards(client, db):
    _approved_source(client, db)
    r = client.get("/review/due")
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert "question" in r.json()[0]
    assert "answer" not in r.json()[0]  # never leak the answer to the quiz client

def test_suspended_cards_excluded(client, db):
    src = _approved_source(client, db)
    src.cards[0].suspended = True
    db.commit()
    assert len(client.get("/review/due").json()) == 1
