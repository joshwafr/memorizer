from app.llm import extract_json

def test_extract_json_plain():
    assert extract_json('{"keep": true}') == {"keep": True}

def test_extract_json_fenced():
    text = 'Here you go:\n```json\n{"grade": "good", "feedback": "nice"}\n```'
    assert extract_json(text) == {"grade": "good", "feedback": "nice"}

def test_extract_json_top_level_array():
    assert extract_json('[{"q": 1}]') == [{"q": 1}]

def test_extract_json_fenced_array():
    text = 'Here are the cards:\n```json\n[{"q": 1}, {"q": 2}]\n```'
    assert extract_json(text) == [{"q": 1}, {"q": 2}]
