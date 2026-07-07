import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import fsrs_service
from app.db import init_db, get_db
from app.models import Source, Card, Review, InterestProfile
from app.capture import detect_source_type
from app.pipeline import process_source, get_profile
from app.schemas import CaptureRequest, AnswerRequest, ProfileUpdate, CardUpdate, TTSRequest

logger = logging.getLogger(__name__)

app = FastAPI(title="Memorizer")

app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

@app.middleware("http")
async def require_bearer_token(request: Request, call_next):
    token = os.environ.get("MEMORIZER_TOKEN")  # read at request time, not import time
    if token:
        path = request.url.path
        open_paths = ("/", "/health", "/spotify/login", "/spotify/callback")
        if path not in open_paths and not (path == "/ui" or path.startswith("/ui/")):
            provided = request.headers.get("authorization", "")
            expected = f"Bearer {token}"
            if not secrets.compare_digest(provided.encode(), expected.encode()):
                return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)

@app.on_event("startup")
def _startup():
    init_db()

@app.on_event("startup")
def _services():
    if not hasattr(app.state, "llm"):
        from app.llm import ClaudeLLM
        from app.fetchers import ContentFetcher
        if not os.environ.get("ANTHROPIC_API_KEY"):
            logger.warning("=" * 60)
            logger.warning("ANTHROPIC_API_KEY not set — captures and reviews will fail")
            logger.warning("=" * 60)
        app.state.llm = ClaudeLLM()
        app.state.fetcher = ContentFetcher()
    if not hasattr(app.state, "session_factory"):
        from app.db import SessionLocal
        app.state.session_factory = SessionLocal

@app.on_event("startup")
def _spotify_poller():
    if os.environ.get("SPOTIFY_CLIENT_ID") and not hasattr(app.state, "scheduler"):
        from apscheduler.schedulers.background import BackgroundScheduler
        from app.spotify_sync import poll_once
        scheduler = BackgroundScheduler()
        scheduler.add_job(lambda: poll_once(app.state.session_factory, app.state.llm, scheduler),
                          "interval", minutes=2, max_instances=1, coalesce=True)
        scheduler.start()
        app.state.scheduler = scheduler
        logger.info("Spotify poller started (every 2 min)")

@app.get("/")
def root():
    return RedirectResponse("/ui/")

@app.get("/health")
def health():
    return {"status": "ok"}

def source_to_dict(s: Source) -> dict:
    return {"id": s.id, "url": s.url, "source_type": s.source_type, "title": s.title,
            "status": s.status, "triage_reason": s.triage_reason,
            "cards": [{"id": c.id, "question": c.question, "answer": c.answer,
                       "key_points": c.key_points, "due_at": c.due_at.isoformat() if c.due_at else None,
                       "suspended": c.suspended} for c in s.cards]}

@app.post("/capture")
def capture(req: CaptureRequest, response: Response, background_tasks: BackgroundTasks,
            db: Session = Depends(get_db)):
    existing = db.scalar(select(Source).where(Source.url == req.url))
    if existing:
        if existing.status in ("pending", "failed"):
            background_tasks.add_task(process_source, existing.id, app.state.session_factory,
                                      app.state.llm, app.state.fetcher)
        return source_to_dict(existing)
    src = Source(url=req.url, source_type=detect_source_type(req.url), status="pending")
    db.add(src)
    db.commit()
    background_tasks.add_task(process_source, src.id, app.state.session_factory,
                              app.state.llm, app.state.fetcher)
    response.status_code = 201
    return source_to_dict(src)

# How far through the pipeline each status is, for the UI progress bar.
PROGRESS = {"pending": 15, "fetched": 60, "inbox": 100, "approved": 100,
            "rejected": 100, "discarded": 100, "failed": 100}

@app.get("/sources/{source_id}")
def source_status(source_id: int, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src:
        raise HTTPException(404, "No source with that id")
    return {"id": src.id, "status": src.status, "progress": PROGRESS.get(src.status, 0),
            "title": src.title, "triage_reason": src.triage_reason,
            "card_count": len(src.cards)}

@app.get("/inbox")
def inbox(db: Session = Depends(get_db)):
    sources = db.scalars(select(Source).where(Source.status == "inbox")).all()
    return [source_to_dict(s) for s in sources]

@app.post("/sources/{source_id}/approve")
def approve(source_id: int, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src or src.status != "inbox":
        raise HTTPException(404, "No inbox source with that id")
    for card in src.cards:
        card.fsrs_state, card.due_at = fsrs_service.new_card_state()
    src.status = "approved"
    db.commit()
    return source_to_dict(src)

@app.post("/sources/{source_id}/reject")
def reject(source_id: int, db: Session = Depends(get_db)):
    src = db.get(Source, source_id)
    if not src or src.status != "inbox":
        raise HTTPException(404, "No inbox source with that id")
    src.status = "rejected"
    db.commit()
    return source_to_dict(src)

def card_status(c: Card) -> str:
    if c.suspended:
        return "suspended"
    if c.fsrs_state is not None:
        return "learning"
    return "inbox" if c.source.status == "inbox" else "inactive"

@app.get("/cards")
def list_cards(db: Session = Depends(get_db)):
    cards = db.scalars(select(Card).order_by(Card.created_at.desc())).all()
    return [{"id": c.id, "question": c.question, "answer": c.answer,
             "status": card_status(c), "suspended": c.suspended,
             "due_at": c.due_at.isoformat() if c.due_at else None,
             "source_title": c.source.title, "source_type": c.source.source_type}
            for c in cards]

@app.patch("/cards/{card_id}")
def update_card(card_id: int, req: CardUpdate, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(404, "No card with that id")
    if req.question is not None:
        card.question = req.question
    if req.answer is not None:
        card.answer = req.answer
    if req.suspended is not None:
        card.suspended = req.suspended
    db.commit()
    return {"id": card.id, "question": card.question, "answer": card.answer,
            "status": card_status(card), "suspended": card.suspended}

@app.delete("/cards/{card_id}")
def delete_card(card_id: int, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card:
        raise HTTPException(404, "No card with that id")
    for review in db.scalars(select(Review).where(Review.card_id == card_id)):
        db.delete(review)
    db.delete(card)
    db.commit()
    return {"deleted": card_id}

@app.get("/review/due")
def due_cards(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    cards = db.scalars(select(Card).where(Card.suspended == False,  # noqa: E712
                                          Card.due_at != None,       # noqa: E711
                                          Card.due_at <= now)
                       .order_by(Card.due_at)).all()
    return [{"id": c.id, "question": c.question, "source_title": c.source.title,
             "due_at": c.due_at.isoformat()} for c in cards]

@app.post("/review/{card_id}/answer")
def answer_card(card_id: int, req: AnswerRequest, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card or card.fsrs_state is None or card.suspended:
        raise HTTPException(404, "No reviewable card with that id")
    result = app.state.llm.grade(card.question, card.answer, card.key_points, req.answer)
    grade = str(result.get("grade", "")).strip().lower()
    if grade not in fsrs_service.RATINGS:
        raise HTTPException(502, "LLM returned an invalid grade")
    feedback = result.get("feedback") or ""
    card.fsrs_state, card.due_at = fsrs_service.review(card.fsrs_state, grade)
    db.add(Review(card_id=card.id, grade=grade, mode="text",
                  user_answer=req.answer, feedback=feedback))
    db.commit()
    return {"grade": grade, "feedback": feedback,
            "correct_answer": card.answer, "next_due": card.due_at.isoformat()}

@app.get("/spotify/login")
def spotify_login():
    from app.spotify import authorize_url, client_creds
    if not all(client_creds()):
        raise HTTPException(503, "Spotify not configured — set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET")
    return RedirectResponse(authorize_url())

@app.get("/spotify/callback")
def spotify_callback(code: str, db: Session = Depends(get_db)):
    from fastapi.responses import HTMLResponse
    from app.spotify import exchange_code, REFRESH_TOKEN_KEY
    from app.spotify_sync import set_setting
    tokens = exchange_code(code)
    refresh = tokens.get("refresh_token")
    if not refresh:
        raise HTTPException(502, "Spotify did not return a refresh token")
    set_setting(db, REFRESH_TOKEN_KEY, refresh)
    return HTMLResponse("<h2>✅ Spotify connected</h2><p>Memorizer now tracks podcasts you "
                        "listen to at least 80% of. You can close this tab.</p>")

@app.get("/spotify/status")
def spotify_status(db: Session = Depends(get_db)):
    from app.spotify import REFRESH_TOKEN_KEY
    from app.spotify_sync import get_setting, listen_ratio
    from app.models import ListenProgress
    rows = db.scalars(select(ListenProgress)
                      .order_by(ListenProgress.updated_at.desc()).limit(10)).all()
    return {"connected": get_setting(db, REFRESH_TOKEN_KEY) is not None,
            "recent": [{"show": r.show_name, "title": r.title,
                        "listened_pct": round(listen_ratio(r) * 100),
                        "consumed": r.consumed} for r in rows]}

@app.post("/tts")
def tts(req: TTSRequest):
    import httpx
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise HTTPException(503, "TTS not configured — set OPENAI_API_KEY")
    r = httpx.post("https://api.openai.com/v1/audio/speech",
                   headers={"Authorization": f"Bearer {key}"},
                   json={"model": "gpt-4o-mini-tts", "voice": "alloy",
                         "input": req.text[:4000]},
                   timeout=60)
    if r.status_code != 200:
        raise HTTPException(502, f"TTS provider error {r.status_code}")
    return Response(content=r.content, media_type="audio/mpeg")

@app.get("/profile")
def read_profile(db: Session = Depends(get_db)):
    p = get_profile(db)
    return {"text": p.text, "version": p.version}

@app.put("/profile")
def update_profile(req: ProfileUpdate, db: Session = Depends(get_db)):
    current = get_profile(db)
    p = InterestProfile(text=req.text, version=current.version + 1)
    db.add(p)
    db.commit()
    return {"text": p.text, "version": p.version}
