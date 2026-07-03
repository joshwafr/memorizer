from pydantic import BaseModel

class CaptureRequest(BaseModel):
    url: str

class AnswerRequest(BaseModel):
    answer: str

class ProfileUpdate(BaseModel):
    text: str
