"""Poller logic: track what's playing, mark episodes consumed at >=80% listened,
triage on metadata (before paying for transcription), then transcribe + generate cards."""
import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, Card, ListenProgress, Source, utcnow
from app.pipeline import get_profile
from app.spotify import REFRESH_TOKEN_KEY, SpotifyClient
from app import podcasts

logger = logging.getLogger(__name__)

CONSUMED_THRESHOLD = 0.8  # Josh's rule: >=80% listened counts as consumed


def get_setting(db: Session, key: str) -> str | None:
    row = db.get(AppSetting, key)
    return row.value if row else None


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(AppSetting, key)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()


def record_playback(db: Session, playing: dict | None) -> ListenProgress | None:
    if not playing or playing.get("currently_playing_type") != "episode":
        return None
    item = playing.get("item") or {}
    if not item.get("id"):
        return None
    row = db.scalar(select(ListenProgress).where(ListenProgress.episode_id == item["id"]))
    if not row:
        row = ListenProgress(
            episode_id=item["id"],
            title=item.get("name") or "Untitled episode",
            show_name=(item.get("show") or {}).get("name"),
            description=item.get("description"),
            duration_ms=item.get("duration_ms") or 0,
        )
        db.add(row)
    row.max_position_ms = max(row.max_position_ms or 0, playing.get("progress_ms") or 0)
    row.updated_at = utcnow()
    db.commit()
    return row


def listen_ratio(row: ListenProgress) -> float:
    return row.max_position_ms / row.duration_ms if row.duration_ms else 0.0


def check_consumed(db: Session, row: ListenProgress, llm) -> Source | None:
    """At >=80%: triage on metadata; keepers become a pending podcast source."""
    if row.consumed or listen_ratio(row) < CONSUMED_THRESHOLD:
        return None
    row.consumed = True
    db.commit()

    url = f"https://open.spotify.com/episode/{row.episode_id}"
    if db.scalar(select(Source).where(Source.url == url)):
        return None
    title = f"{row.show_name}: {row.title}" if row.show_name else row.title
    meta = f"Podcast episode.\nShow: {row.show_name}\nEpisode: {row.title}\n{row.description or ''}"
    verdict = llm.triage(title, meta, get_profile(db).text)
    src = Source(url=url, source_type="podcast", title=title,
                 triage_reason=verdict.get("reason"),
                 status="pending" if verdict.get("keep") else "discarded")
    db.add(src)
    db.commit()
    return src if src.status == "pending" else None


def process_podcast_source(source_id: int, session_factory, llm,
                           show_name: str | None, episode_title: str) -> None:
    """Transcribe and generate cards. Mirrors pipeline.process_source semantics."""
    with session_factory() as db:
        src = db.get(Source, source_id)
        if src is None or src.status not in ("pending", "failed"):
            return
        try:
            src.content_text = podcasts.fetch_transcript(show_name or "", episode_title)
            src.status = "fetched"
            db.commit()
            for c in llm.generate_cards(src.title, src.content_text):
                db.add(Card(source_id=src.id, question=c["question"], answer=c["answer"],
                            key_points=c.get("key_points", [])))
            src.status = "inbox"
            db.commit()
        except Exception:
            logger.exception("podcast pipeline failed for source %s", source_id)
            db.rollback()
            src.status = "failed"
            db.commit()


_client: SpotifyClient | None = None


def poll_once(session_factory, llm, scheduler=None) -> None:
    """One poll tick. Runs in APScheduler's threadpool."""
    global _client
    with session_factory() as db:
        token = get_setting(db, REFRESH_TOKEN_KEY)
        if not token:
            return
        if _client is None or _client.refresh_token != token:
            _client = SpotifyClient(token)
        try:
            playing = _client.currently_playing()
        except Exception:
            logger.exception("spotify poll failed")
            return
        row = record_playback(db, playing)
        if row is None:
            return
        src = check_consumed(db, row, llm)
        if src is not None:
            args = (src.id, session_factory, llm, row.show_name, row.title)
            if scheduler is not None:
                # long transcription runs as its own one-shot job, not inside the poll tick
                scheduler.add_job(process_podcast_source, args=args,
                                  misfire_grace_time=3600)
            else:
                process_podcast_source(*args)
