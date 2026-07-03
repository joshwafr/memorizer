from fastapi import FastAPI

from app.db import init_db

app = FastAPI(title="Memorizer")

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/health")
def health():
    return {"status": "ok"}
