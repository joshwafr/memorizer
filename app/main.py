from fastapi import FastAPI, Depends, Response, BackgroundTasks
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import init_db, get_db
from app.models import Source, InterestProfile
from app.capture import detect_source_type
from app.pipeline import process_source, get_profile
from app.schemas import CaptureRequest, ProfileUpdate

app = FastAPI(title="Memorizer")

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
