from unittest.mock import patch, MagicMock

import pytest

from app.fetchers import ContentFetcher, NeedsTextError
from app.models import Source

LONG = "Real article text. " * 60          # > 600 chars
STUB = "Subscribe to read this article."   # paywall stub


def _resp(text):
    return MagicMock(status_code=200, text=f"<html>{text}</html>")


def test_ladder_plain_fetch_wins():
    fetcher = ContentFetcher()
    with patch("app.fetchers.httpx.get", return_value=_resp(LONG)) as get, \
         patch("app.fetchers.trafilatura.extract", return_value=LONG):
        assert fetcher.fetch("https://ft.com/content/x", "article") == LONG
    assert get.call_count == 1


def test_ladder_falls_back_to_cookies():
    fetcher = ContentFetcher()
    with patch("app.fetchers.httpx.get", side_effect=[_resp(STUB), _resp(LONG)]) as get, \
         patch("app.fetchers.trafilatura.extract", side_effect=[STUB, LONG]):
        text = fetcher.fetch("https://ft.com/content/x", "article", cookies="sess=abc")
    assert text == LONG
    assert get.call_count == 2
    assert get.call_args_list[1].kwargs["headers"]["Cookie"] == "sess=abc"


def test_ladder_exhausted_raises_needs_text():
    fetcher = ContentFetcher()
    with patch("app.fetchers.httpx.get", return_value=_resp(STUB)), \
         patch("app.fetchers.trafilatura.extract", return_value=STUB):
        with pytest.raises(NeedsTextError):
            fetcher.fetch("https://ft.com/content/x", "article", cookies="sess=abc")


def test_needs_text_status_and_paste_flow(client, db):
    class StubFetcher:
        def fetch(self, url, source_type, cookies=None):
            raise NeedsTextError("paywall")
    from app.main import app as fastapi_app
    fastapi_app.state.fetcher = StubFetcher()
    client.post("/capture", json={"url": "https://www.ft.com/content/abc"})
    src = db.query(Source).one()
    assert src.status == "needs_text"
    # paste the text -> cards generated even though FakeLLM might discard
    r = client.post(f"/sources/{src.id}/text", json={"text": "Real article body. " * 20})
    assert r.status_code == 200
    db.expire_all()
    assert src.status == "inbox"
    assert len(src.cards) == 2


def test_paste_rejects_tiny_text(client, db):
    class StubFetcher:
        def fetch(self, url, source_type, cookies=None):
            raise NeedsTextError("paywall")
    from app.main import app as fastapi_app
    fastapi_app.state.fetcher = StubFetcher()
    client.post("/capture", json={"url": "https://www.ft.com/content/tiny"})
    src = db.query(Source).one()
    assert client.post(f"/sources/{src.id}/text", json={"text": "too short"}).status_code == 422


def test_rescue_discarded_source_skips_triage(client, db, fake_llm):
    fake_llm.keep = False
    client.post("/capture", json={"url": "https://youtu.be/history12345"})
    src = db.query(Source).one()
    assert src.status == "discarded"
    r = client.post(f"/sources/{src.id}/rescue")
    assert r.status_code == 200
    db.expire_all()
    assert src.status == "inbox"       # force_keep overrode keep=False
    assert len(src.cards) == 2


def test_sources_listing_filters(client, db, fake_llm):
    fake_llm.keep = False
    client.post("/capture", json={"url": "https://youtu.be/discard12345"})
    rows = client.get("/sources?status=discarded").json()
    assert len(rows) == 1
    assert rows[0]["status"] == "discarded"
    assert client.get("/sources?status=failed").json() == []


def test_site_cookies_roundtrip(client):
    r = client.put("/sites/WWW.FT.com", json={"cookies": "FTSession=xyz"})
    assert r.json()["domain"] == "ft.com"
    domains = [s["domain"] for s in client.get("/sites").json()]
    assert domains == ["ft.com"]
