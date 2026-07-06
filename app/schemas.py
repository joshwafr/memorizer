from pydantic import BaseModel

class CaptureRequest(BaseModel):
    url: str

class AnswerRequest(BaseModel):
    answer: str

class ProfileUpdate(BaseModel):
    text: str

class TTSRequest(BaseModel):
    text: str

class CardUpdate(BaseModel):
    question: str | None = None
    answer: str | None = None
    suspended: bool | None = None
