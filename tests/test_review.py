from app.models import Source, Card

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

from app.models import Review

def test_answer_grades_and_reschedules(client, db):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    r = client.post(f"/review/{card_id}/answer", json={"answer": "my spoken answer"})
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == "good"
    assert "feedback" in body and "next_due" in body
    assert db.query(Review).count() == 1

def test_good_grade_pushes_due_to_future(client, db):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    client.post(f"/review/{card_id}/answer", json={"answer": "x"})
    remaining = [c["id"] for c in client.get("/review/due").json()]
    assert card_id not in remaining

def test_invalid_llm_grade_returns_502_and_changes_nothing(client, db, fake_llm):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    card = db.get(Card, card_id)
    due_before, state_before = card.due_at, card.fsrs_state
    fake_llm.grade_value = "ok"
    r = client.post(f"/review/{card_id}/answer", json={"answer": "x"})
    assert r.status_code == 502
    db.expire_all()
    card = db.get(Card, card_id)
    assert card.due_at == due_before
    assert card.fsrs_state == state_before
    assert db.query(Review).count() == 0

def test_capitalized_grade_is_normalized(client, db, fake_llm):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    fake_llm.grade_value = "Good"
    r = client.post(f"/review/{card_id}/answer", json={"answer": "x"})
    assert r.status_code == 200
    assert r.json()["grade"] == "good"

def test_cannot_answer_suspended_card(client, db):
    src = _approved_source(client, db)
    card = src.cards[0]
    card.suspended = True
    db.commit()
    r = client.post(f"/review/{card.id}/answer", json={"answer": "x"})
    assert r.status_code == 404
