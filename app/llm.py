import json
import os
import re
from anthropic import Anthropic

MODEL = os.environ.get("MEMORIZER_MODEL", "claude-sonnet-4-6")

def extract_json(text: str):
    match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    payload = match.group(1) if match else text
    start = payload.find("{") if "{" in payload else payload.find("[")
    end = max(payload.rfind("}"), payload.rfind("]")) + 1
    return json.loads(payload[start:end])

TRIAGE_PROMPT = """You triage content for a personal spaced-repetition learning app.
INTEREST PROFILE:\n{profile}\n
CONTENT (title: {title}):\n{content}\n
Should this become learning material? Respond with JSON only:
{{"keep": true/false, "reason": "<one sentence>", "title": "<inferred title if missing>"}}"""

CARDS_PROMPT = """Distill this content into 2-5 rich insight cards for spaced repetition.
Each card: a substantial, self-contained question (include enough source context to make
sense weeks later, e.g. "From the FT piece on TSMC: ..."), a thorough answer, and 2-4
key_points a correct answer must mention. Respond with JSON only:
[{{"question": "...", "answer": "...", "key_points": ["..."]}}]\n
CONTENT (title: {title}):\n{content}"""

GRADE_PROMPT = """Grade this spaced-repetition answer. QUESTION: {question}
EXPECTED ANSWER: {answer}\nKEY POINTS: {key_points}\nUSER'S ANSWER: {user_answer}\n
Map to FSRS: "again" (didn't know), "hard" (partial, struggled), "good" (got the substance),
"easy" (complete and confident). Respond with JSON only:
{{"grade": "again|hard|good|easy", "feedback": "<2-3 sentences: what they got right and what they missed>"}}"""

class ClaudeLLM:
    def __init__(self):
        self.client = Anthropic()  # reads ANTHROPIC_API_KEY

    def _ask(self, prompt: str):
        resp = self.client.messages.create(model=MODEL, max_tokens=2000,
                                           messages=[{"role": "user", "content": prompt}])
        return extract_json(resp.content[0].text)

    def triage(self, title: str | None, content: str, profile: str) -> dict:
        return self._ask(TRIAGE_PROMPT.format(profile=profile, title=title or "unknown", content=content[:12000]))

    def generate_cards(self, title: str | None, content: str) -> list[dict]:
        return self._ask(CARDS_PROMPT.format(title=title or "unknown", content=content[:24000]))

    def grade(self, question: str, answer: str, key_points: list, user_answer: str) -> dict:
        return self._ask(GRADE_PROMPT.format(question=question, answer=answer,
                                             key_points=key_points, user_answer=user_answer))
