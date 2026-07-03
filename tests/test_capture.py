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
