# Memorizer — Design Document

*Status: approved 2026-07-03. Personal knowledge-retention app for Josh.*

## What it is

An app that captures the content Josh consumes — YouTube videos, FT/NYT articles,
Spotify podcasts and audiobooks — distills each item into a handful of rich
"insight cards" using an LLM, schedules them with FSRS spaced repetition, and
quizzes him **by voice** during runs, grading his spoken answers and updating the
schedule automatically.

## Locked decisions

| Decision | Choice |
|---|---|
| Platform | Native iOS app (SwiftUI) + cloud backend |
| Backend | Python / FastAPI, Postgres, cheap cloud host (Railway / Fly.io / Hetzner, $5–15/mo) |
| Scope | Personal single-user now; clean separation (user IDs, hosted backend, no hardcoded keys) so multi-user is a refactor, not a rewrite |
| YouTube capture | Auto-import watch history (cookie-based scrape, scheduled) — with share sheet as the always-working fallback |
| Article capture (FT/NYT) | iOS share sheet → backend fetches full text using stored subscription cookies; Shortcuts paste-text fallback |
| Spotify capture | Official API: poll "currently playing" (`additional_types=episode`) every few minutes; count episodes with meaningful listen time (>50% or >10 min) |
| Noise filtering | LLM triage against a living interest profile + approve/reject inbox in the app |
| Card design | 2–5 rich insight cards per item (question, answer, key points for grading, source ref) — not atomic Anki-style facts |
| Scheduling | FSRS via `py-fsrs` (never hand-roll the algorithm) |
| Voice stack | STT → Claude → TTS pipeline. Apple on-device speech recognition (free) → Claude → OpenAI TTS (~$0.01–0.02/min). Upgrade to realtime speech-to-speech only if a low-cost option appears. AVSpeech as offline fallback |
| Grading | Claude grades the spoken answer against the card's key points → maps to FSRS Again/Hard/Good/Easy → tells Josh what he missed |
| Card generation LLM | Claude API |

## Architecture

```
                    ┌────────────────────────── CLOUD BACKEND ──────────────────────────┐
YouTube history ────┤ scheduled scrape (cookies, yt-dlp)                                │
Spotify listening ──┤ scheduled poll (official OAuth API)                               │
Share sheet ────────┤ POST /capture                                                     │
                    │        ▼                                                          │
                    │   [sources] ── fetch transcript / article text / RSS audio+Whisper│
                    │        ▼                                                          │
                    │   LLM triage (interest profile) ── discard junk BEFORE            │
                    │        ▼                            paying for transcription       │
                    │   Claude → 2–5 insight cards                                      │
                    │        ▼                                                          │
                    │   Inbox (pending approval) → approved → FSRS scheduling           │
                    │                                                                   │
                    │   FastAPI: /capture /inbox /cards /session /feedback /profile     │
                    │   Postgres + scheduled jobs (cron/APScheduler)                    │
                    └───────────────────────────────────────────────────────────────────┘
                                             ▲
                    ┌────────────────────────┴───────────────── iOS APP (SwiftUI) ──────┐
                    │ Share extension │ Inbox (swipe approve/reject) │ Library │        │
                    │ Voice session: Apple STT → backend → OpenAI TTS audio             │
                    │ Background audio + lock screen controls (runs with AirPods)       │
                    └───────────────────────────────────────────────────────────────────┘
```

## Ingestion per source type

- **YouTube**: history scrape (fragile, never the only path) or share sheet →
  transcript via `youtube-transcript-api` / `yt-dlp` subtitles.
- **Articles**: share sheet URL → server fetch with stored FT/NYT session cookies →
  readability extraction. Fallback: iOS Shortcut that copies article text and posts it.
- **Spotify podcasts**: official API detects listens → triage on show/title/description
  first → locate public RSS audio (iTunes Search / PodcastIndex) → Whisper
  transcription (~$0.40/audio-hour). Spotify exclusives: show notes + LLM knowledge,
  flagged lower-confidence.
- **Spotify audiobooks**: DRM — no audio access. Cards from Claude's knowledge of the
  book, chapter-scoped where detectable, flagged as "book-knowledge derived".

## Relevance feedback loop

Goal: rejected topics (e.g. football highlights) stop being imported *and* stop being asked.

- **Signals**: inbox rejections (optional reason), voice commands ("skip this",
  "I don't care about this anymore"), manual card suspension.
- **Storage**: `feedback_events` table.
- **Learning**: nightly job gives Claude the current interest profile + recent
  feedback → produces an updated, versioned profile with explicit EXCLUDE rules.
- **Enforcement gates**: (1) import triage skips excluded topics pre-transcription,
  (2) existing cards on newly-excluded topics are auto-suspended (undoable in app),
  (3) suspended cards never enter the quiz queue.
- **Transparency**: profile is viewable/editable in the app — Josh can always see why
  something was filtered.

## Voice session flow (the run)

1. Start session (AirPods, locked phone). App pulls FSRS due queue.
2. OpenAI TTS reads the question with context ("From that FT piece on TSMC last week — …").
3. Josh answers aloud → on-device Apple STT transcribes.
4. Claude grades vs the card's key points → FSRS grade → speaks feedback on what was missed.
5. Digressions welcome ("tell me more about X") — answered grounded in stored
   transcript, then back to the queue.
6. FSRS state updates; next card. ~15-minute run clears a typical daily queue.

Later session modes on the same plumbing: explain-back (Feynman), connection prompts
("how does this relate to…"), hands-free daily briefing. MVP ships quiz + digression.

## Data model (sketch)

- `sources` — url, type (youtube|article|podcast|audiobook), title, author/channel,
  consumed_at, status (pending_triage | triaged_keep | discarded | approved), text/transcript
- `cards` — source_id, question, answer, key_points, FSRS state (stability, difficulty,
  due, reps, lapses, state), suspended flag
- `reviews` — card_id, ts, grade, mode (voice|text), answer transcript
- `feedback_events` — target, action, reason, ts
- `chat_sessions` / `chat_messages`
- `interest_profile` — versioned text document with include/exclude rules

## Build order (each phase usable on its own)

1. **Backend + text MVP** — paste URL → cards → FSRS → review by typing in a bare web
   page. Proves the entire brain with zero iOS/audio complexity.
2. **iOS app** — share extension, inbox, library, text review.
3. **Voice** — audio session, Apple STT, OpenAI TTS, background/lock-screen.
4. **Capture automation** — Spotify poller (official API, do first), then YouTube
   history scraper (fragile, do last).
5. **Feedback loop** — nightly profile-update job + suspension gates.

## Risks

- **Paywalled extraction** (FT/NYT): cookies expire, markup changes. Personal
  automation of Josh's own access; keep paste-text fallback.
- **YouTube scraping**: will break periodically; share sheet is the backbone.
- **LLM grading fairness**: occasional unfair grades — allow voice override
  ("actually I knew that") as a cheap hybrid.
- **Queue sludge**: mitigated by triage + inbox + feedback loop + few-rich-cards.
- **Spotify exclusives / audiobooks**: no transcript — degraded, clearly-flagged card quality.

## Running costs (estimate)

Hosting $5–15/mo · Claude card-gen pennies per item · Whisper $0.40/podcast-hour
(post-triage only) · OpenAI TTS a few cents per session · Apple STT free.
Realistic total: **$15–40/mo**.
