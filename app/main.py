from fastapi import FastAPI

app = FastAPI(title="Memorizer")

@app.get("/health")
def health():
    return {"status": "ok"}
