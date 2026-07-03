from fastapi import FastAPI, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import init_db, get_db
from app.models import Source
from app.capture import detect_source_type
from app.schemas import CaptureRequest

app = FastAPI(title="Memorizer")

@app.on_event("startup")
def _startup():
    init_db()

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
def capture(req: CaptureRequest, response: Response, db: Session = Depends(get_db)):
    existing = db.scalar(select(Source).where(Source.url == req.url))
    if existing:
        return source_to_dict(existing)
    src = Source(url=req.url, source_type=detect_source_type(req.url), status="pending")
    db.add(src)
    db.commit()
    response.status_code = 201
    return source_to_dict(src)
