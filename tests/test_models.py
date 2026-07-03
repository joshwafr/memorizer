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
