from unittest.mock import patch, MagicMock

from app.models import ListenProgress, Source, AppSetting
from app.spotify_sync import (record_playback, check_consumed, listen_ratio,
                              get_setting, set_setting)


def _playing(ep_id="ep1", progress=0, duration=100000, playing_type="episode"):
    return {"currently_playing_type": playing_type, "progress_ms": progress,
            "item": {"id": ep_id, "name": "AI and chips", "duration_ms": duration,
                     "description": "A show about semiconductors",
                     "show": {"name": "Acquired"}}}


def test_record_playback_tracks_max_position(db):
    row = record_playback(db, _playing(progress=30000))
    assert row.max_position_ms == 30000
    row = record_playback(db, _playing(progress=50000))
    assert row.max_position_ms == 50000
    row = record_playback(db, _playing(progress=10000))  # user rewound
    assert row.max_position_ms == 50000
    assert db.query(ListenProgress).count() == 1


def test_record_playback_ignores_music(db):
    assert record_playback(db, _playing(playing_type="track")) is None
    assert record_playback(db, None) is None


def test_not_consumed_below_80_pct(db, fake_llm):
    row = record_playback(db, _playing(progress=70000))
    assert check_consumed(db, row, fake_llm) is None
    assert row.consumed is False


def test_consumed_at_80_pct_creates_pending_source(db, fake_llm):
    row = record_playback(db, _playing(progress=80000))
    src = check_consumed(db, row, fake_llm)
    assert row.consumed is True
    assert src is not None
    assert src.source_type == "podcast"
    assert src.status == "pending"
    assert "Acquired" in src.title
    # second call is a no-op
    assert check_consumed(db, row, fake_llm) is None
    assert db.query(Source).count() == 1


def test_consumed_but_triaged_out(db, fake_llm):
    fake_llm.keep = False
    row = record_playback(db, _playing(progress=90000))
    assert check_consumed(db, row, fake_llm) is None
    src = db.query(Source).one()
    assert src.status == "discarded"


def test_settings_roundtrip(db):
    assert get_setting(db, "k") is None
    set_setting(db, "k", "v1")
    set_setting(db, "k", "v2")
    assert get_setting(db, "k") == "v2"
    assert db.query(AppSetting).count() == 1


def test_callback_stores_refresh_token(client, db, monkeypatch):
    monkeypatch.setenv("SPOTIFY_CLIENT_ID", "cid")
    monkeypatch.setenv("SPOTIFY_CLIENT_SECRET", "sec")
    with patch("app.spotify.httpx.post",
               return_value=MagicMock(status_code=200,
                                      json=lambda: {"refresh_token": "rt123"},
                                      raise_for_status=lambda: None)):
        r = client.get("/spotify/callback?code=abc")
    assert r.status_code == 200
    assert get_setting(db, "spotify_refresh_token") == "rt123"
    status = client.get("/spotify/status").json()
    assert status["connected"] is True
