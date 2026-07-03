import logging
from sqlalchemy.orm import Session
from app.models import Source, Card, InterestProfile

logger = logging.getLogger(__name__)

DEFAULT_PROFILE = ("Interested in: finance, markets, technology, semiconductors, AI, "
                   "science, business strategy, economics.\nEXCLUDE: music videos, "
                   "sports highlights, entertainment.")

def get_profile(db: Session) -> InterestProfile:
    profile = db.query(InterestProfile).order_by(InterestProfile.version.desc()).first()
    if not profile:
        profile = InterestProfile(text=DEFAULT_PROFILE, version=1)
        db.add(profile)
        db.commit()
    return profile

def process_source(source_id: int, db: Session, llm, fetcher) -> None:
    src = db.get(Source, source_id)
    try:
        src.content_text = fetcher.fetch(src.url, src.source_type)
        src.status = "fetched"
        db.commit()

        verdict = llm.triage(src.title, src.content_text, get_profile(db).text)
        src.title = src.title or verdict.get("title")
        src.triage_reason = verdict.get("reason")
        if not verdict.get("keep"):
            src.status = "discarded"
            db.commit()
            return

        for c in llm.generate_cards(src.title, src.content_text):
            db.add(Card(source_id=src.id, question=c["question"], answer=c["answer"],
                        key_points=c.get("key_points", [])))
        src.status = "inbox"
        db.commit()
    except Exception:
        logger.exception("pipeline failed for source %s", source_id)
        src.status = "failed"
        db.commit()
