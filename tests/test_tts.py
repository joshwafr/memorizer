from unittest.mock import patch, MagicMock


def test_tts_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    r = client.post("/tts", json={"text": "hello"})
    assert r.status_code == 503


def test_tts_proxies_audio(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    fake = MagicMock(status_code=200, content=b"MP3BYTES")
    with patch("httpx.post", return_value=fake) as post:
        r = client.post("/tts", json={"text": "hello world"})
    assert r.status_code == 200
    assert r.content == b"MP3BYTES"
    assert r.headers["content-type"].startswith("audio/mpeg")
    assert post.call_args.kwargs["json"]["input"] == "hello world"


def test_tts_provider_error_returns_502(client, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    with patch("httpx.post", return_value=MagicMock(status_code=401)):
        assert client.post("/tts", json={"text": "x"}).status_code == 502
