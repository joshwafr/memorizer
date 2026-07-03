from app.llm import extract_json

def test_extract_json_plain():
    assert extract_json('{"keep": true}') == {"keep": True}

def test_extract_json_fenced():
    text = 'Here you go:\n```json\n{"grade": "good", "feedback": "nice"}\n```'
    assert extract_json(text) == {"grade": "good", "feedback": "nice"}
