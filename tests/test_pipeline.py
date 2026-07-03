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
