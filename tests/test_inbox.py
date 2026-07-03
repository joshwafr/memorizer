from datetime import datetime, timezone
from app.models import Source, Card

def _seed_inbox(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    return db.query(Source).one()

def test_inbox_lists_pending(client, db):
    _seed_inbox(client, db)
    r = client.get("/inbox")
    assert len(r.json()) == 1
    assert len(r.json()[0]["cards"]) == 2

def test_approve_initializes_fsrs(client, db):
    src = _seed_inbox(client, db)
    r = client.post(f"/sources/{src.id}/approve")
    assert r.status_code == 200
    db.refresh(src)
    assert src.status == "approved"
    for card in src.cards:
        assert card.fsrs_state is not None
        assert card.due_at is not None
        assert card.due_at <= datetime.now(timezone.utc)  # new cards immediately due

def test_reject_discards(client, db):
    src = _seed_inbox(client, db)
    client.post(f"/sources/{src.id}/reject")
    db.refresh(src)
    assert src.status == "rejected"
