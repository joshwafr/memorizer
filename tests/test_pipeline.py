from app.main import app
from app.models import Source
from tests.conftest import FakeFetcher, FakeLLM

class FailingFetcher:
    def fetch(self, url, source_type):
        raise RuntimeError("network down")

def test_capture_runs_pipeline_to_inbox(client, db):
    client.post("/capture", json={"url": "https://youtu.be/abc12345678"})
    src = db.query(Source).one()
    assert src.status == "inbox"
    assert src.content_text == "fake transcript content"
    assert len(src.cards) == 2

def test_recapture_retries_failed_source(client, db):
    app.state.fetcher = FailingFetcher()
    client.post("/capture", json={"url": "https://youtu.be/retry1234567"})
    src = db.query(Source).one()
    assert src.status == "failed"

    app.state.fetcher = FakeFetcher()
    r = client.post("/capture", json={"url": "https://youtu.be/retry1234567"})
    assert r.status_code == 200
    db.refresh(src)
    assert src.status == "inbox"
    assert len(src.cards) == 2

def test_triage_discard(client, db, fake_llm):
    fake_llm.keep = False
    client.post("/capture", json={"url": "https://youtu.be/sports123456"})
    src = db.query(Source).one()
    assert src.status == "discarded"
    assert len(src.cards) == 0
