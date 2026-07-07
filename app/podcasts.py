"""Podcast transcript pipeline: iTunes feed lookup -> RSS episode match ->
audio download -> Whisper transcription (chunked with ffmpeg when >24MB)."""
import difflib
import glob
import logging
import os
import re
import subprocess
import tempfile

import httpx

logger = logging.getLogger(__name__)

MAX_WHISPER_BYTES = 24 * 1024 * 1024
MAX_AUDIO_BYTES = 500 * 1024 * 1024  # refuse absurd downloads


class PodcastError(Exception):
    pass


def find_feed_url(show_name: str) -> str | None:
    r = httpx.get("https://itunes.apple.com/search",
                  params={"media": "podcast", "term": show_name, "limit": 5}, timeout=30)
    r.raise_for_status()
    results = r.json().get("results", [])
    return results[0].get("feedUrl") if results else None


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", s.lower()).strip()


def find_episode_audio(feed_xml: str, episode_title: str) -> str | None:
    """Best-match the episode title against RSS <item><title>, return enclosure url."""
    items = re.findall(r"<item>(.*?)</item>", feed_xml, re.DOTALL)
    target = _normalize(episode_title)
    best_url, best_score = None, 0.0
    for item in items:
        m_title = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", item, re.DOTALL)
        m_enc = re.search(r'<enclosure[^>]*url="([^"]+)"', item)
        if not m_title or not m_enc:
            continue
        score = difflib.SequenceMatcher(None, target, _normalize(m_title.group(1))).ratio()
        if score > best_score:
            best_score, best_url = score, m_enc.group(1)
    return best_url if best_score >= 0.6 else None


def _download_audio(url: str) -> str:
    suffix = ".mp3"
    fd, path = tempfile.mkstemp(suffix=suffix)
    written = 0
    with os.fdopen(fd, "wb") as f, httpx.stream("GET", url, timeout=120,
                                                 follow_redirects=True) as r:
        r.raise_for_status()
        for chunk in r.iter_bytes():
            written += len(chunk)
            if written > MAX_AUDIO_BYTES:
                raise PodcastError("audio file too large")
            f.write(chunk)
    return path


def _split_audio(path: str) -> list[str]:
    if os.path.getsize(path) <= MAX_WHISPER_BYTES:
        return [path]
    out_dir = tempfile.mkdtemp()
    subprocess.run(["ffmpeg", "-y", "-i", path, "-f", "segment", "-segment_time", "1200",
                    "-c", "copy", os.path.join(out_dir, "chunk%03d.mp3")],
                   check=True, capture_output=True)
    chunks = sorted(glob.glob(os.path.join(out_dir, "chunk*.mp3")))
    if not chunks:
        raise PodcastError("ffmpeg produced no chunks")
    return chunks


def _whisper(path: str) -> str:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise PodcastError("OPENAI_API_KEY not set — cannot transcribe podcasts")
    with open(path, "rb") as f:
        r = httpx.post("https://api.openai.com/v1/audio/transcriptions",
                       headers={"Authorization": f"Bearer {key}"},
                       files={"file": (os.path.basename(path), f, "audio/mpeg")},
                       data={"model": "whisper-1"}, timeout=900)
    if r.status_code != 200:
        raise PodcastError(f"whisper error {r.status_code}: {r.text[:200]}")
    return r.json()["text"]


def fetch_transcript(show_name: str, episode_title: str) -> str:
    feed_url = find_feed_url(show_name)
    if not feed_url:
        raise PodcastError(f"no public feed found for show {show_name!r}")
    feed_xml = httpx.get(feed_url, timeout=60, follow_redirects=True).text
    audio_url = find_episode_audio(feed_xml, episode_title)
    if not audio_url:
        raise PodcastError(f"episode {episode_title!r} not found in feed")
    audio_path = _download_audio(audio_url)
    try:
        return " ".join(_whisper(c) for c in _split_audio(audio_path))
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass
