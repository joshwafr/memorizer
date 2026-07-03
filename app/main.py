import os
import secrets
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Request, Response, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import fsrs_service
from app.db import init_db, get_db
from app.models import Source, Card, Review, InterestProfile
from app.capture import detect_source_type
from app.pipeline import process_source, get_profile
from app.schemas import CaptureRequest, AnswerRequest, ProfileUpdate

app = FastAPI(title="Memorizer")

app.mount("/ui", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="ui")

@app.middleware("http")
async def require_bearer_token(request: Request, call_next):
    token = os.environ.get("MEMORIZER_TOKEN")  # read at request time, not import time
    if token:
        path = request.url.path
        if path != "/health" and not (path == "/ui" or path.startswith("/ui/")):
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
        app.state.llm = ClaudeLLM()
        app.state.fetcher = ContentFetcher()
    if not hasattr(app.state, "session_factory"):
        from app.db import SessionLocal
        app.state.session_factory = SessionLocal

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
        return source_to_dict(existing)
    src = Source(url=req.url, source_type=detect_source_type(req.url), status="pending")
    db.add(src)
    db.commit()
    background_tasks.add_task(process_source, src.id, app.state.session_factory,
                              app.state.llm, app.state.fetcher)
    response.status_code = 201
    return source_to_dict(src)

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
    feedback = result.get("feedback", "")
    card.fsrs_state, card.due_at = fsrs_service.review(card.fsrs_state, grade)
    db.add(Review(card_id=card.id, grade=grade, mode="text",
                  user_answer=req.answer, feedback=feedback))
    db.commit()
    return {"grade": grade, "feedback": feedback,
            "correct_answer": card.answer, "next_due": card.due_at.isoformat()}

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
