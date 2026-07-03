from datetime import datetime, timezone
from fsrs import Scheduler, Card as FsrsCard, Rating

scheduler = Scheduler()
RATINGS = {"again": Rating.Again, "hard": Rating.Hard, "good": Rating.Good, "easy": Rating.Easy}

def new_card_state() -> tuple[dict, datetime]:
    card = FsrsCard()
    return card.to_dict(), card.due

def review(state: dict, grade: str) -> tuple[dict, datetime]:
    card = FsrsCard.from_dict(state)
    card, _log = scheduler.review_card(card, RATINGS[grade], review_datetime=datetime.now(timezone.utc))
    return card.to_dict(), card.due
