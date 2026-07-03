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
