import logging
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.fetchers import NeedsTextError
from app.models import Source, Card, InterestProfile, SiteCookie

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

def cookies_for(db: Session, url: str) -> str | None:
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    row = db.get(SiteCookie, host)
    return row.cookies if row else None

def run_triage_and_cards(db: Session, src: Source, llm, force_keep: bool = False) -> None:
    """Shared tail of every ingestion path. force_keep skips the discard decision —
    used when the user explicitly rescued or pasted the content."""
    verdict = llm.triage(src.title, src.content_text, get_profile(db).text)
    src.title = src.title or verdict.get("title")
    if not force_keep:
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

def process_source(source_id: int, session_factory, llm, fetcher,
                   force_keep: bool = False) -> None:
    with session_factory() as db:
        src = db.get(Source, source_id)
        if src is None:
            logger.warning("source %s not found, skipping pipeline", source_id)
            return
        if src.status not in ("pending", "failed"):
            logger.warning("source %s has status %r, skipping pipeline", source_id, src.status)
            return
        try:
            if not src.content_text:  # rescued sources may already have their text
                src.content_text = fetcher.fetch(src.url, src.source_type,
                                                 cookies=cookies_for(db, src.url))
                src.status = "fetched"
                db.commit()
            run_triage_and_cards(db, src, llm, force_keep=force_keep)
        except NeedsTextError as e:
            db.rollback()
            logger.info("source %s needs manual text: %s", source_id, e)
            src.status = "needs_text"
            src.triage_reason = str(e)
            db.commit()
        except Exception:
            db.rollback()
            logger.exception("pipeline failed for source %s", source_id)
            src.status = "failed"
            db.commit()
