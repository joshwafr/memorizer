# Memorizer Phase 1 Implementation Plan

**Goal:** A running FastAPI backend that ingests a pasted URL (YouTube or article), generates 2–5 insight cards with Claude, schedules them with FSRS, and lets Josh review by typing in a bare web page.

**Architecture:** Single FastAPI service + SQLAlchemy (SQLite in dev, Postgres in prod via `DATABASE_URL`). Capture creates a `Source`; a background pipeline fetches content, triages it against the interest profile, and generates cards into an inbox. Approving a source initializes FSRS state on its cards. Review = LLM grades a typed answer → FSRS reschedule. All LLM and network fetchers are injected so tests run with fakes — no API keys or network in the test suite.

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, `fsrs` (py-fsrs), `anthropic`, `youtube-transcript-api`, `trafilatura`, pytest, uv.

**Conventions for every task:** run tests with `uv run pytest -q`; commit after each green task with the trailer `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`. TDD: never write implementation before the failing test.

**Reference — final layout:**

```
Memorizer/
  pyproject.toml
  app/
    __init__.py  main.py  db.py  models.py  schemas.py
    capture.py  fetchers.py  llm.py  pipeline.py  fsrs_service.py
    static/index.html
  tests/
    conftest.py  test_health.py  test_capture.py  test_fetchers.py
    test_llm.py  test_pipeline.py  test_profile.py  test_inbox.py  test_review.py
```

---

## Task 1: Project scaffold + health endpoint

**Files:** Create `pyproject.toml`, `app/__init__.py`, `app/main.py`, `tests/test_health.py`, `.gitignore`

**Step 1: Initialize project**

```bash
cd /Users/josh/Desktop/Memorizer
git init
uv init --no-readme --python 3.12
uv add fastapi "uvicorn[standard]" sqlalchemy anthropic fsrs youtube-transcript-api trafilatura httpx
uv add --dev pytest
```

Delete the `main.py` that `uv init` creates at the root (`rm main.py`). Create `.gitignore`:

```
.venv/
__pycache__/
*.db
.env
```

**Step 2: Write the failing test** — `tests/test_health.py`:

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health():
    client = TestClient(app)
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

**Step 3: Run it, verify it fails** — `uv run pytest -q` → `ModuleNotFoundError: No module named 'app'`.

**Step 4: Minimal implementation** — create empty `app/__init__.py` and `app/main.py`:

```python
from fastapi import FastAPI

app = FastAPI(title="Memorizer")

@app.get("/health")
def health():
    return {"status": "ok"}
```

**Step 5: Run tests, verify pass** — `uv run pytest -q` → `1 passed`.

**Step 6: Commit** — `git add -A && git commit -m "Scaffold FastAPI app with health endpoint"`

---

## Task 2: Database layer and models

**Files:** Create `app/db.py`, `app/models.py`, `tests/conftest.py`, `tests/test_models.py`

**Step 1: Write the failing test** — `tests/test_models.py`:

```python
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
```

And `tests/conftest.py` (fixtures used by all later tests — includes fakes wired in Task 6/7, add them now):

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient

from app.db import Base, get_db
from app.main import app

@pytest.fixture()
def engine():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return engine

@pytest.fixture()
def db(engine):
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()

@pytest.fixture()
def client(engine, db):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
```

**Step 2: Run, verify failure** — `uv run pytest -q` → `ModuleNotFoundError: No module named 'app.db'`.

**Step 3: Implement** — `app/db.py`:

```python
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///memorizer.db")

class Base(DeclarativeBase):
    pass

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app import models  # noqa: F401  (register models)
    Base.metadata.create_all(engine)
```

`app/models.py`:

```python
from datetime import datetime, timezone
from sqlalchemy import String, Text, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db import Base

def utcnow():
    return datetime.now(timezone.utc)

class Source(Base):
    __tablename__ = "sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    source_type: Mapped[str] = mapped_column(String(20))          # youtube | article
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending -> fetched -> inbox | discarded | failed ; inbox -> approved | rejected
    triage_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    cards: Mapped[list["Card"]] = relationship(back_populates="source")

class Card(Base):
    __tablename__ = "cards"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    question: Mapped[str] = mapped_column(Text)
    answer: Mapped[str] = mapped_column(Text)
    key_points: Mapped[list] = mapped_column(JSON, default=list)
    fsrs_state: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped["Source"] = relationship(back_populates="cards")

class Review(Base):
    __tablename__ = "reviews"
    id: Mapped[int] = mapped_column(primary_key=True)
    card_id: Mapped[int] = mapped_column(ForeignKey("cards.id"))
    grade: Mapped[str] = mapped_column(String(10))                 # again|hard|good|easy
    mode: Mapped[str] = mapped_column(String(10), default="text")
    user_answer: Mapped[str] = mapped_column(Text)
    feedback: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class InterestProfile(Base):
    __tablename__ = "interest_profile"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
```

Also in `app/main.py`, add startup table creation:

```python
from app.db import init_db

@app.on_event("startup")
def _startup():
    init_db()
```

**Step 4: Run tests** — `uv run pytest -q` → `2 passed`.

**Step 5: Commit** — `git add -A && git commit -m "Add SQLAlchemy models and test fixtures"`

---

## Task 3: URL type detection

**Files:** Create `app/capture.py`, `tests/test_capture.py`

**Step 1: Failing test** — `tests/test_capture.py`:

```python
import pytest
from app.capture import detect_source_type, extract_youtube_id

@pytest.mark.parametrize("url,expected", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "youtube"),
    ("https://www.ft.com/content/abc-123", "article"),
    ("https://www.nytimes.com/2026/07/01/business/chips.html", "article"),
])
def test_detect_source_type(url, expected):
    assert detect_source_type(url) == expected

def test_extract_youtube_id():
    assert extract_youtube_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert extract_youtube_id("https://youtu.be/dQw4w9WgXcQ?t=30") == "dQw4w9WgXcQ"
```

**Step 2: Run, verify failure** — `ModuleNotFoundError: No module named 'app.capture'`.

**Step 3: Implement** — `app/capture.py`:

```python
from urllib.parse import urlparse, parse_qs

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

def detect_source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return "youtube" if host in YOUTUBE_HOSTS else "article"

def extract_youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.lstrip("/").split("/")[0] or None
    return parse_qs(parsed.query).get("v", [None])[0]
```

**Step 4: Run tests** — `uv run pytest -q` → all pass.

**Step 5: Commit** — `git add -A && git commit -m "Add URL source-type detection"`

---

## Task 4: POST /capture endpoint

**Files:** Modify `app/main.py`; create `app/schemas.py`; add to `tests/test_capture.py`

**Step 1: Failing test** — append to `tests/test_capture.py`:

```python
def test_capture_creates_source(client, db):
    r = client.post("/capture", json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"})
    assert r.status_code == 201
    body = r.json()
    assert body["source_type"] == "youtube"
    assert body["status"] in ("pending", "inbox")  # background pipeline may already have run

def test_capture_duplicate_url_returns_existing(client, db):
    url = "https://www.ft.com/content/abc-123"
    first = client.post("/capture", json={"url": url}).json()
    second = client.post("/capture", json={"url": url})
    assert second.status_code == 200
    assert second.json()["id"] == first["id"]
```

**Step 2: Run, verify failure** — `404 != 201`.

**Step 3: Implement** — `app/schemas.py`:

```python
from pydantic import BaseModel

class CaptureRequest(BaseModel):
    url: str

class AnswerRequest(BaseModel):
    answer: str

class ProfileUpdate(BaseModel):
    text: str
```

In `app/main.py` add:

```python
from fastapi import Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Source
from app.capture import detect_source_type
from app.schemas import CaptureRequest

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
```

**Step 4: Run tests** — all pass. **Step 5: Commit** — `git commit -am "Add capture endpoint"`

---

## Task 5: Content fetchers (YouTube transcript + article extraction)

**Files:** Create `app/fetchers.py`, `tests/test_fetchers.py`

**Step 1: Failing test** — `tests/test_fetchers.py` (mock the third-party libs; never hit the network in tests):

```python
from unittest.mock import patch, MagicMock
from app.fetchers import ContentFetcher

def test_fetch_youtube_joins_snippets():
    fetcher = ContentFetcher()
    snippet1, snippet2 = MagicMock(text="hello"), MagicMock(text="world")
    with patch("app.fetchers.YouTubeTranscriptApi") as api_cls:
        api_cls.return_value.fetch.return_value = [snippet1, snippet2]
        text = fetcher.fetch("https://www.youtube.com/watch?v=abc12345678", "youtube")
    assert text == "hello world"

def test_fetch_article_uses_trafilatura():
    fetcher = ContentFetcher()
    with patch("app.fetchers.trafilatura") as traf:
        traf.fetch_url.return_value = "<html>raw</html>"
        traf.extract.return_value = "Clean article text"
        text = fetcher.fetch("https://www.ft.com/content/x", "article")
    assert text == "Clean article text"
```

**Step 2: Run, verify failure** — `ModuleNotFoundError: No module named 'app.fetchers'`.

**Step 3: Implement** — `app/fetchers.py`:

```python
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi
from app.capture import extract_youtube_id

class FetchError(Exception):
    pass

class ContentFetcher:
    def fetch(self, url: str, source_type: str) -> str:
        if source_type == "youtube":
            return self._fetch_youtube(url)
        return self._fetch_article(url)

    def _fetch_youtube(self, url: str) -> str:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise FetchError(f"No video id in {url}")
        snippets = YouTubeTranscriptApi().fetch(video_id)
        return " ".join(s.text for s in snippets)

    def _fetch_article(self, url: str) -> str:
        html = trafilatura.fetch_url(url)
        text = trafilatura.extract(html) if html else None
        if not text:
            raise FetchError(f"Could not extract article text from {url}")
        return text
```

*(Note: FT/NYT paywalls will often defeat plain `fetch_url`. That's acceptable in Phase 1 — capture fails visibly with status `failed`. Cookie-based fetching is a Phase 4 item.)*

**Step 4: Run tests** — pass. **Step 5: Commit** — `git commit -am "Add YouTube and article content fetchers"`

---

## Task 6: LLM wrapper (Claude) with injectable fake

**Files:** Create `app/llm.py`, `tests/test_llm.py`; modify `tests/conftest.py`

**Step 1: Failing test** — `tests/test_llm.py` (tests the JSON-extraction helper — the only logic worth unit-testing; real API calls are not tested):

```python
from app.llm import extract_json

def test_extract_json_plain():
    assert extract_json('{"keep": true}') == {"keep": True}

def test_extract_json_fenced():
    text = 'Here you go:\n```json\n{"grade": "good", "feedback": "nice"}\n```'
    assert extract_json(text) == {"grade": "good", "feedback": "nice"}
```

**Step 2: Run, verify failure.**

**Step 3: Implement** — `app/llm.py`:

```python
import json
import os
import re
from anthropic import Anthropic

MODEL = os.environ.get("MEMORIZER_MODEL", "claude-sonnet-4-6")

def extract_json(text: str):
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    payload = match.group(1) if match else text
    start = payload.find("{") if "{" in payload else payload.find("[")
    end = max(payload.rfind("}"), payload.rfind("]")) + 1
    return json.loads(payload[start:end])

TRIAGE_PROMPT = """You triage content for a personal spaced-repetition learning app.
INTEREST PROFILE:\n{profile}\n
CONTENT (title: {title}):\n{content}\n
Should this become learning material? Respond with JSON only:
{{"keep": true/false, "reason": "<one sentence>", "title": "<inferred title if missing>"}}"""

CARDS_PROMPT = """Distill this content into 2-5 rich insight cards for spaced repetition.
Each card: a substantial, self-contained question (include enough source context to make
sense weeks later, e.g. "From the FT piece on TSMC: ..."), a thorough answer, and 2-4
key_points a correct answer must mention. Respond with JSON only:
[{{"question": "...", "answer": "...", "key_points": ["..."]}}]\n
CONTENT (title: {title}):\n{content}"""

GRADE_PROMPT = """Grade this spaced-repetition answer. QUESTION: {question}
EXPECTED ANSWER: {answer}\nKEY POINTS: {key_points}\nUSER'S ANSWER: {user_answer}\n
Map to FSRS: "again" (didn't know), "hard" (partial, struggled), "good" (got the substance),
"easy" (complete and confident). Respond with JSON only:
{{"grade": "again|hard|good|easy", "feedback": "<2-3 sentences: what they got right and what they missed>"}}"""

class ClaudeLLM:
    def __init__(self):
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY

    def _ask(self, prompt: str):
        resp = self.client.messages.create(model=MODEL, max_tokens=2000,
                                           messages=[{"role": "user", "content": prompt}])
        return extract_json(resp.content[0].text)

    def triage(self, title: str | None, content: str, profile: str) -> dict:
        return self._ask(TRIAGE_PROMPT.format(profile=profile, title=title or "unknown", content=content[:12000]))

    def generate_cards(self, title: str | None, content: str) -> list[dict]:
        return self._ask(CARDS_PROMPT.format(title=title or "unknown", content=content[:24000]))

    def grade(self, question: str, answer: str, key_points: list, user_answer: str) -> dict:
        return self._ask(GRADE_PROMPT.format(question=question, answer=answer,
                                             key_points=key_points, user_answer=user_answer))
```

Add fakes to `tests/conftest.py`:

```python
class FakeLLM:
    def __init__(self, keep=True, grade="good"):
        self.keep, self.grade_value = keep, grade
    def triage(self, title, content, profile):
        return {"keep": self.keep, "reason": "fake", "title": title or "Fake Title"}
    def generate_cards(self, title, content):
        return [{"question": "Q1?", "answer": "A1", "key_points": ["k1"]},
                {"question": "Q2?", "answer": "A2", "key_points": ["k2"]}]
    def grade(self, question, answer, key_points, user_answer):
        return {"grade": self.grade_value, "feedback": "fake feedback"}

class FakeFetcher:
    def fetch(self, url, source_type):
        return "fake transcript content"

@pytest.fixture()
def fake_llm():
    return FakeLLM()
```

And extend the `client` fixture to install fakes (Task 7 wires `app.state`):

```python
@pytest.fixture()
def client(engine, db, fake_llm):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    app.state.llm = fake_llm
    app.state.fetcher = FakeFetcher()
    yield TestClient(app)
    app.dependency_overrides.clear()
```

**Step 4: Run tests** — pass. **Step 5: Commit** — `git commit -am "Add Claude LLM wrapper with prompts and test fakes"`

---

## Task 7: Ingestion pipeline wired into capture

**Files:** Create `app/pipeline.py`, `tests/test_pipeline.py`; modify `app/main.py`

**Step 1: Failing test** — `tests/test_pipeline.py`:

```python
from app.models import Source
from tests.conftest import FakeLLM

def test_capture_runs_pipeline_to_inbox(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    src = db.query(Source).one()
    assert src.status == "inbox"
    assert src.content_text == "fake transcript content"
    assert len(src.cards) == 2

def test_triage_discard(client, db, fake_llm):
    fake_llm.keep = False
    client.post("/capture", json={"url": "https://youtu.be/sports123456"})
    src = db.query(Source).one()
    assert src.status == "discarded"
    assert len(src.cards) == 0
```

**Step 2: Run, verify failure** — status is `"pending"`, not `"inbox"`.

**Step 3: Implement** — `app/pipeline.py`:

```python
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
```

Wire into `app/main.py` — replace the capture endpoint's ending and add real services at startup:

```python
from fastapi import BackgroundTasks
from app.pipeline import process_source

@app.on_event("startup")
def _services():
    if not hasattr(app.state, "llm"):
        from app.llm import ClaudeLLM
        from app.fetchers import ContentFetcher
        app.state.llm = ClaudeLLM()
        app.state.fetcher = ContentFetcher()

# in capture(), add background_tasks: BackgroundTasks param, and before returning:
#     background_tasks.add_task(process_source, src.id, db, app.state.llm, app.state.fetcher)
```

Full updated signature:

```python
@app.post("/capture")
def capture(req: CaptureRequest, response: Response, background_tasks: BackgroundTasks,
            db: Session = Depends(get_db)):
    existing = db.scalar(select(Source).where(Source.url == req.url))
    if existing:
        return source_to_dict(existing)
    src = Source(url=req.url, source_type=detect_source_type(req.url), status="pending")
    db.add(src)
    db.commit()
    background_tasks.add_task(process_source, src.id, db, app.state.llm, app.state.fetcher)
    response.status_code = 201
    return source_to_dict(src)
```

*(TestClient executes background tasks synchronously after the response, so the tests can assert the final state. Guarding startup with `hasattr` keeps test fakes from being overwritten. Note: `ClaudeLLM()` is only constructed at startup when no fake is installed — running the real server requires `ANTHROPIC_API_KEY` set.)*

**Step 4: Run tests** — all pass. **Step 5: Commit** — `git commit -am "Wire ingestion pipeline: fetch, triage, generate cards"`

---

## Task 8: Interest profile endpoints

**Files:** Modify `app/main.py`; create `tests/test_profile.py`

**Step 1: Failing test** — `tests/test_profile.py`:

```python
def test_get_profile_seeds_default(client):
    r = client.get("/profile")
    assert r.status_code == 200
    assert "EXCLUDE" in r.json()["text"]

def test_update_profile_bumps_version(client):
    client.get("/profile")
    r = client.put("/profile", json={"text": "Only semiconductors."})
    assert r.json()["version"] == 2
    assert client.get("/profile").json()["text"] == "Only semiconductors."
```

**Step 2: Run, verify failure** — 404.

**Step 3: Implement** — in `app/main.py`:

```python
from app.pipeline import get_profile
from app.models import InterestProfile
from app.schemas import ProfileUpdate

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
```

**Step 4: Run tests** — pass. **Step 5: Commit** — `git commit -am "Add interest profile endpoints"`

---

## Task 9: Inbox — list, approve (FSRS init), reject

**Files:** Create `app/fsrs_service.py`, `tests/test_inbox.py`; modify `app/main.py`

**Step 1: Failing test** — `tests/test_inbox.py`:

```python
from datetime import datetime, timezone
from app.models import Source, Card

def _seed_inbox(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    return db.query(Source).one()

def test_inbox_lists_pending(client, db):
    _seed_inbox(client, db)
    r = client.get("/inbox")
    assert len(r.json()) == 1
    assert len(r.json()[0]["cards"]) == 2

def test_approve_initializes_fsrs(client, db):
    src = _seed_inbox(client, db)
    r = client.post(f"/sources/{src.id}/approve")
    assert r.status_code == 200
    db.refresh(src)
    assert src.status == "approved"
    for card in src.cards:
        assert card.fsrs_state is not None
        assert card.due_at is not None
        assert card.due_at <= datetime.now(timezone.utc)  # new cards immediately due

def test_reject_discards(client, db):
    src = _seed_inbox(client, db)
    client.post(f"/sources/{src.id}/reject")
    db.refresh(src)
    assert src.status == "rejected"
```

**Step 2: Run, verify failure** — 404.

**Step 3: Implement** — `app/fsrs_service.py`:

```python
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
```

In `app/main.py`:

```python
from fastapi import HTTPException
from app import fsrs_service
from app.models import Card

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
```

**Step 4: Run tests.** Note: SQLite drops timezone info on DateTime columns — if the `due_at <= now` comparison raises a naive/aware `TypeError`, normalize in the test: `card.due_at.replace(tzinfo=timezone.utc) <= datetime.now(timezone.utc)`. **Step 5: Commit** — `git commit -am "Add inbox approve/reject with FSRS initialization"`

---

## Task 10: Due queue endpoint

**Files:** Modify `app/main.py`; create `tests/test_review.py`

**Step 1: Failing test** — `tests/test_review.py`:

```python
from app.models import Source

def _approved_source(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    src = db.query(Source).one()
    client.post(f"/sources/{src.id}/approve")
    return src

def test_due_queue_returns_approved_cards(client, db):
    _approved_source(client, db)
    r = client.get("/review/due")
    assert r.status_code == 200
    assert len(r.json()) == 2
    assert "question" in r.json()[0]
    assert "answer" not in r.json()[0]  # never leak the answer to the quiz client

def test_suspended_cards_excluded(client, db):
    src = _approved_source(client, db)
    src.cards[0].suspended = True
    db.commit()
    assert len(client.get("/review/due").json()) == 1
```

**Step 2: Run, verify failure** — 404.

**Step 3: Implement** — in `app/main.py`:

```python
from datetime import datetime, timezone

@app.get("/review/due")
def due_cards(db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    cards = db.scalars(select(Card).where(Card.suspended == False,  # noqa: E712
                                          Card.due_at != None,       # noqa: E711
                                          Card.due_at <= now)
                       .order_by(Card.due_at)).all()
    return [{"id": c.id, "question": c.question, "source_title": c.source.title,
             "due_at": c.due_at.isoformat()} for c in cards]
```

*(SQLite naive-datetime note from Task 9 applies: if the comparison misbehaves, store/compare with `datetime.utcnow()`-style naive UTC consistently — simplest is to make `utcnow()` in `models.py` return naive UTC via `datetime.now(timezone.utc).replace(tzinfo=None)` and use the same in this query. Pick one convention and apply it everywhere.)*

**Step 4: Run tests** — pass. **Step 5: Commit** — `git commit -am "Add due-cards queue endpoint"`

---

## Task 11: Answer + grading endpoint (the core loop)

**Files:** Modify `app/main.py`; add to `tests/test_review.py`

**Step 1: Failing test** — append to `tests/test_review.py`:

```python
from app.models import Review

def test_answer_grades_and_reschedules(client, db):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    r = client.post(f"/review/{card_id}/answer", json={"answer": "my spoken answer"})
    assert r.status_code == 200
    body = r.json()
    assert body["grade"] == "good"
    assert "feedback" in body and "next_due" in body
    assert db.query(Review).count() == 1

def test_good_grade_pushes_due_to_future(client, db):
    _approved_source(client, db)
    card_id = client.get("/review/due").json()[0]["id"]
    client.post(f"/review/{card_id}/answer", json={"answer": "x"})
    remaining = [c["id"] for c in client.get("/review/due").json()]
    assert card_id not in remaining
```

**Step 2: Run, verify failure** — 404.

**Step 3: Implement** — in `app/main.py`:

```python
from app.schemas import AnswerRequest
from app.models import Review

@app.post("/review/{card_id}/answer")
def answer_card(card_id: int, req: AnswerRequest, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if not card or card.fsrs_state is None:
        raise HTTPException(404, "No reviewable card with that id")
    result = app.state.llm.grade(card.question, card.answer, card.key_points, req.answer)
    grade = result["grade"]
    card.fsrs_state, card.due_at = fsrs_service.review(card.fsrs_state, grade)
    db.add(Review(card_id=card.id, grade=grade, mode="text",
                  user_answer=req.answer, feedback=result["feedback"]))
    db.commit()
    return {"grade": grade, "feedback": result["feedback"],
            "correct_answer": card.answer, "next_due": card.due_at.isoformat()}
```

**Step 4: Run tests** — all pass. **Step 5: Commit** — `git commit -am "Add answer grading with FSRS rescheduling"`

---

## Task 12: Bare web UI

**Files:** Create `app/static/index.html`; modify `app/main.py`

No unit test — verify manually in Step 3. Single HTML page, vanilla JS, three panels: capture form, inbox (approve/reject buttons per source with its cards listed), review loop (shows question → textarea → submit → shows grade/feedback → next).

**Step 1: Serve static** — in `app/main.py`:

```python
from fastapi.staticfiles import StaticFiles
app.mount("/ui", StaticFiles(directory="app/static", html=True), name="ui")
```

**Step 2: Create `app/static/index.html`** — implement with: a URL input POSTing to `/capture`; an inbox section rendering `GET /inbox` with per-source Approve/Reject buttons; a review section that fetches `/review/due`, shows one question at a time, POSTs the typed answer to `/review/{id}/answer`, displays grade + feedback + correct answer, then advances. Keep it ugly and functional (~150 lines). No framework.

**Step 3: Manual verification (requires `ANTHROPIC_API_KEY`):**

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run uvicorn app.main:app --reload
# open http://127.0.0.1:8000/ui
# paste a real YouTube URL with captions -> wait -> inbox shows cards -> approve -> review by typing
```

Expected: full loop works end-to-end — capture → cards in inbox → approve → answer → grade + feedback + card disappears from due queue.

**Step 4: Commit** — `git commit -am "Add bare web UI for capture, inbox, and review"`

---

## Task 13: Deploy

**Files:** Create `Dockerfile`; deploy to Railway or Fly.io

1. `Dockerfile`: `FROM python:3.12-slim`, install uv, copy project, `uv sync --frozen`, `CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]`.
2. Create Railway project (or `fly launch`), add Postgres addon, set env vars: `DATABASE_URL` (from addon — note SQLAlchemy needs the `postgresql://` scheme, not `postgres://`; add `uv add psycopg2-binary`), `ANTHROPIC_API_KEY`, optionally `MEMORIZER_MODEL`.
3. Add basic auth so the API isn't public: simplest is a single `MEMORIZER_TOKEN` env var checked by a FastAPI dependency on every route except `/health` (`Authorization: Bearer <token>`); the web UI prompts once and stores it in `localStorage`. Write one test: request without token → 401, with token → 200.
4. Smoke test from the phone's browser: capture a URL, approve, review. **This is the Phase 1 exit criterion.**
5. Commit + tag: `git tag phase-1`.

---

# Phases 2–5 (milestone level — plan in detail when reached)

## Phase 2: iOS app (SwiftUI)

- **M2.1** Xcode project, API client hitting the deployed backend (token auth), Library + Inbox screens (swipe approve/reject).
- **M2.2** Share extension: receives URLs from YouTube/FT/NYT/Safari → `POST /capture`. This is the capture backbone.
- **M2.3** Text review screen (same loop as web UI). Exit criterion: daily use happens on the phone, web UI retired.

## Phase 3: Voice sessions

- **M3.1** Session orchestration endpoint (`POST /session/start`, conversational turns that wrap the due queue — digression handling via Claude with transcript context).
- **M3.2** iOS audio: `AVAudioSession` (background + AirPods), Apple `SFSpeechRecognizer` on-device STT, OpenAI TTS playback with `AVSpeechSynthesizer` offline fallback.
- **M3.3** Lock-screen/Control-Center transport controls; voice override of grades ("actually I knew that"). Exit criterion: full review session completed on an actual run.

## Phase 4: Capture automation

- **M4.1** Spotify: OAuth app, poll `GET /me/player?additional_types=episode` every ~3 min (APScheduler job), listen-threshold logic, episode → RSS audio lookup (iTunes Search/PodcastIndex) → Whisper transcription → existing pipeline. Audiobooks: book-knowledge cards, flagged.
- **M4.2** FT/NYT cookie-based fetching + Shortcuts paste-text fallback endpoint.
- **M4.3** YouTube history scraper (cookies + yt-dlp/Playwright, scheduled, dedup against `sources`). Built last; share sheet remains the backbone when it breaks.

## Phase 5: Relevance feedback loop

- **M5.1** `feedback_events` table + reject-reason capture in inbox + "not interested" voice/UI action on cards.
- **M5.2** Nightly job: Claude reads profile + recent feedback → proposes updated profile version (with EXCLUDE rules) → auto-applies, visible/editable in app.
- **M5.3** Suspension gate: newly excluded topics auto-suspend matching cards (undoable list in app).
