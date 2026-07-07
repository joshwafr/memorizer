from app.podcasts import find_episode_audio

FEED = """<rss><channel>
<item><title>Ep 1: The TSMC story</title>
<enclosure url="https://cdn.example.com/ep1.mp3" type="audio/mpeg"/></item>
<item><title><![CDATA[Ep 2: NVIDIA — the whole history]]></title>
<enclosure url="https://cdn.example.com/ep2.mp3" type="audio/mpeg"/></item>
</channel></rss>"""


def test_find_episode_audio_exact():
    assert find_episode_audio(FEED, "Ep 1: The TSMC story") == "https://cdn.example.com/ep1.mp3"


def test_find_episode_audio_fuzzy_cdata():
    assert find_episode_audio(FEED, "Ep 2: NVIDIA the whole history") == "https://cdn.example.com/ep2.mp3"


def test_find_episode_audio_no_match():
    assert find_episode_audio(FEED, "completely different show about cooking pasta") is None
