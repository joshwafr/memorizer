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
    long_text = "Clean article text. " * 40  # above the paywall-stub threshold
    with patch("app.fetchers.httpx.get",
               return_value=MagicMock(status_code=200, text="<html>raw</html>")), \
         patch("app.fetchers.trafilatura") as traf:
        traf.extract.return_value = long_text
        text = fetcher.fetch("https://www.ft.com/content/x", "article")
    assert text == long_text


def test_youtube_uses_proxy_when_env_set(monkeypatch):
    monkeypatch.setenv("WEBSHARE_PROXY_USERNAME", "u")
    monkeypatch.setenv("WEBSHARE_PROXY_PASSWORD", "p")
    fetcher = ContentFetcher()
    with patch("app.fetchers.YouTubeTranscriptApi") as api_cls:
        api_cls.return_value.fetch.return_value = [MagicMock(text="hi")]
        fetcher.fetch("https://youtu.be/abc12345678", "youtube")
    proxy = api_cls.call_args.kwargs["proxy_config"]
    assert proxy is not None


def test_youtube_no_proxy_by_default(monkeypatch):
    monkeypatch.delenv("WEBSHARE_PROXY_USERNAME", raising=False)
    fetcher = ContentFetcher()
    with patch("app.fetchers.YouTubeTranscriptApi") as api_cls:
        api_cls.return_value.fetch.return_value = [MagicMock(text="hi")]
        fetcher.fetch("https://youtu.be/abc12345678", "youtube")
    assert api_cls.call_args.kwargs["proxy_config"] is None
