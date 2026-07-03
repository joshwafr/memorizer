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

@pytest.fixture()
def client(engine, db, fake_llm):
    def override_get_db():
        yield db
    app.dependency_overrides[get_db] = override_get_db
    app.state.llm = fake_llm
    app.state.fetcher = FakeFetcher()
    app.state.session_factory = sessionmaker(bind=engine)
    yield TestClient(app)
    app.dependency_overrides.clear()
