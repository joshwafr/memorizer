from urllib.parse import urlparse, parse_qs

YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be"}

def detect_source_type(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return "youtube" if host in YOUTUBE_HOSTS else "article"

def extract_youtube_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc.endswith("youtu.be"):
        return parsed.path.lstrip("/").split("/")[0] or None
    return parse_qs(parsed.query).get("v", [None])[0]
