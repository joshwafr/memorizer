import os

import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.capture import extract_youtube_id

class FetchError(Exception):
    pass

def _proxy_config():
    # Residential proxy so YouTube doesn't block requests from cloud IPs.
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if user and password:
        return WebshareProxyConfig(proxy_username=user, proxy_password=password)
    return None

class ContentFetcher:
    def fetch(self, url: str, source_type: str) -> str:
        if source_type == "youtube":
            return self._fetch_youtube(url)
        return self._fetch_article(url)

    def _fetch_youtube(self, url: str) -> str:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise FetchError(f"No video id in {url}")
        snippets = YouTubeTranscriptApi(proxy_config=_proxy_config()).fetch(video_id)
        return " ".join(s.text for s in snippets)

    def _fetch_article(self, url: str) -> str:
        html = trafilatura.fetch_url(url)
        text = trafilatura.extract(html) if html else None
        if not text:
            raise FetchError(f"Could not extract article text from {url}")
        return text
