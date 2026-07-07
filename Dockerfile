FROM python:3.12-slim

WORKDIR /app

# ffmpeg: chunk long podcast audio under Whisper's 25MB request limit
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY app ./app

# NOTE: the default SQLite DB lives inside the container and is lost on restart —
# set DATABASE_URL to an external database or mount a volume for persistence.
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
