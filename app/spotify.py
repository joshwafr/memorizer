"""Spotify OAuth + playback client. Configured entirely via env vars:
SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, optional SPOTIFY_REDIRECT_URI."""
import os
import time
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
SCOPES = "user-read-playback-state user-read-currently-playing"
REFRESH_TOKEN_KEY = "spotify_refresh_token"  # app_settings key


def client_creds() -> tuple[str | None, str | None]:
    return os.environ.get("SPOTIFY_CLIENT_ID"), os.environ.get("SPOTIFY_CLIENT_SECRET")


def redirect_uri() -> str:
    return os.environ.get("SPOTIFY_REDIRECT_URI",
                          "https://app-production-1e43.up.railway.app/spotify/callback")


def authorize_url() -> str:
    cid, _ = client_creds()
    return AUTH_URL + "?" + urlencode({
        "client_id": cid, "response_type": "code",
        "redirect_uri": redirect_uri(), "scope": SCOPES,
    })


def exchange_code(code: str) -> dict:
    cid, secret = client_creds()
    r = httpx.post(TOKEN_URL, data={"grant_type": "authorization_code", "code": code,
                                    "redirect_uri": redirect_uri()},
                   auth=(cid, secret), timeout=30)
    r.raise_for_status()
    return r.json()


class SpotifyClient:
    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token
        self._access: str | None = None
        self._expires: float = 0

    def _token(self) -> str:
        if not self._access or time.time() > self._expires - 60:
            cid, secret = client_creds()
            r = httpx.post(TOKEN_URL, data={"grant_type": "refresh_token",
                                            "refresh_token": self.refresh_token},
                           auth=(cid, secret), timeout=30)
            r.raise_for_status()
            d = r.json()
            self._access = d["access_token"]
            self._expires = time.time() + d.get("expires_in", 3600)
        return self._access

    def currently_playing(self) -> dict | None:
        r = httpx.get("https://api.spotify.com/v1/me/player/currently-playing",
                      params={"additional_types": "episode"},
                      headers={"Authorization": f"Bearer {self._token()}"}, timeout=30)
        if r.status_code == 204:
            return None
        r.raise_for_status()
        return r.json()
