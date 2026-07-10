import os

import httpx
import trafilatura
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.proxies import WebshareProxyConfig

from app.capture import extract_youtube_id

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
STUB_THRESHOLD = 600  # extracted text shorter than this is treated as a paywall stub


class FetchError(Exception):
    pass


class NeedsTextError(FetchError):
    """All fetch rungs produced only a stub — user must supply the text."""


def _proxy_config():
    # Residential proxy so YouTube doesn't block requests from cloud IPs.
    user = os.environ.get("WEBSHARE_PROXY_USERNAME")
    password = os.environ.get("WEBSHARE_PROXY_PASSWORD")
    if user and password:
        return WebshareProxyConfig(proxy_username=user, proxy_password=password)
    return None


class ContentFetcher:
    def fetch(self, url: str, source_type: str, cookies: str | None = None) -> str:
        if source_type == "youtube":
            return self._fetch_youtube(url)
        return self._fetch_article(url, cookies)

    def _fetch_youtube(self, url: str) -> str:
        video_id = extract_youtube_id(url)
        if not video_id:
            raise FetchError(f"No video id in {url}")
        snippets = YouTubeTranscriptApi(proxy_config=_proxy_config()).fetch(video_id)
        return " ".join(s.text for s in snippets)

    def _fetch_article(self, url: str, cookies: str | None = None) -> str:
        """Fallback ladder: plain fetch -> fetch with stored site cookies -> give up
        with NeedsTextError so the user can paste the text."""
        rungs: list[str | None] = [None]
        if cookies:
            rungs.append(cookies)
        best = ""
        for rung in rungs:
            headers = {"User-Agent": USER_AGENT}
            if rung:
                headers["Cookie"] = rung
            try:
                r = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
                text = trafilatura.extract(r.text) if r.status_code == 200 else None
            except httpx.HTTPError:
                text = None
            if text and len(text) >= STUB_THRESHOLD:
                return text
            if text and len(text) > len(best):
                best = text
        raise NeedsTextError(
            f"Could only extract {len(best)} characters from {url} — "
            "likely a paywall; paste the article text instead.")
