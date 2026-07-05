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


def test_source_status_progress(client, db):
    from app.models import Source
    src = Source(url="https://youtu.be/progress1234", source_type="youtube", status="pending")
    db.add(src)
    db.commit()
    r = client.get(f"/sources/{src.id}")
    assert r.status_code == 200
    assert r.json()["progress"] == 15
    src.status = "fetched"
    db.commit()
    assert client.get(f"/sources/{src.id}").json()["progress"] == 60
    src.status = "inbox"
    db.commit()
    body = client.get(f"/sources/{src.id}").json()
    assert body["progress"] == 100
    assert body["status"] == "inbox"


def test_source_status_missing(client):
    assert client.get("/sources/9999").status_code == 404
