from datetime import datetime, timezone

from app.models import Source, Card

def test_create_source_and_card(db):
    src = Source(url="https://youtube.com/watch?v=abc", source_type="youtube", status="pending")
    db.add(src)
    db.flush()
    card = Card(source_id=src.id, question="Q?", answer="A", key_points=["k1", "k2"])
    db.add(card)
    db.commit()
    assert card.id is not None
    assert card.suspended is False
    assert card.fsrs_state is None

def test_due_at_roundtrips_timezone_aware(db):
    src = Source(url="https://example.com/a", source_type="article", status="pending")
    db.add(src)
    db.flush()
    card = Card(
        source_id=src.id,
        question="Q?",
        answer="A",
        due_at=datetime.now(timezone.utc),
    )
    db.add(card)
    db.commit()
    db.expire_all()
    card = db.get(Card, card.id)
    assert card.due_at.tzinfo is not None
    # Comparing to an aware datetime must not raise
    assert (card.due_at <= datetime.now(timezone.utc)) in (True, False)
