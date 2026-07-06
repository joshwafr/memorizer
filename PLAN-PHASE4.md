# Phase 4 Build Plan — Capture Automation & Learning Quality

*Drafted 2026-07-05 from Josh's feedback. Order: quality fixes → Spotify (priority) →
article sources → YouTube auto-sync.*

## 0. Learning-quality fixes (shipped 2026-07-05, backend-only)

- ✅ **Higher-level cards**: generation prompt rewritten — 2–4 big-idea cards (arguments,
  frameworks, mechanisms, implications), trivia explicitly banned unless the detail IS the
  insight. Applies to all new captures; existing over-detailed cards can be edited or
  deleted in the Cards tab.
- ✅ **Wrong answers teach**: grading prompt rewritten — `again`/`hard` grades must come
  with a 3–5 sentence explanation of the correct answer *and the why/mechanism*, written
  as flowing prose because voice sessions read it aloud.

Still open in this bucket (needs an app update, bundle with 4a's release):

- **Re-ask failed cards in the same session**: when a card grades `again`, requeue it at
  the end of the current voice/text session so Josh proves he absorbed the explanation
  before the session ends. (FSRS already schedules it `due now`; the app just doesn't
  loop back today.)

## 4a. Spotify ingestion (PRIORITY)

Same pipeline as everything else; the new part is detection and transcription.

1. **OAuth setup (one-time, needs Josh ~5 min)**: create a Spotify developer app
   (developer.spotify.com), scopes `user-read-playback-state user-read-currently-playing`,
   one-time browser consent; backend stores the refresh token in Postgres.
2. **Listen detection**: APScheduler job polls `GET /me/player?additional_types=episode`
   every ~2 min. Track per-episode max playback position vs duration in a
   `listen_progress` table. **Threshold: mark consumed at ≥80% listened** (Josh's rule —
   mirrors the intended YouTube logic). Music tracks ignored; only episodes/audiobooks.
3. **Triage before transcription** (cost gate): show name + episode title + description →
   Claude keep/discard against the interest profile. Discards never pay for Whisper.
4. **Transcription**: locate the episode's public RSS audio via iTunes Search /
   PodcastIndex, download, Whisper API (~$0.36/hr, OpenAI key already configured).
   Spotify-exclusive shows (no public RSS): fall back to show notes + Claude knowledge,
   cards flagged lower-confidence.
5. **Audiobooks**: DRM = no audio access. Detect via `currently_playing_type`; generate
   book-knowledge cards from Claude's knowledge of the title, flagged as such.
6. Cards land in the same inbox → approve → FSRS. Nothing new to learn in the UI.

## 4b. Article sources beyond FT (gift links, Economist, anything)

- **Today already works**: any *readable* URL shared to Memorizer gets extracted by
  trafilatura — FT non-member/gift links, Economist gift links, blogs, Reuters, etc.
  Nothing to build for the happy path.
- **Build**: a **paywall fallback ladder** per capture: (1) plain fetch → (2) fetch with
  stored per-site cookies (start with FT + Economist, table `site_cookies`) → (3) if both
  yield a stub, mark source `needs_text` and let Josh paste text via a small iOS
  Shortcut / web form instead of failing.
- Sources stay generic — no per-publisher code beyond cookies.

## 4c. YouTube history auto-sync (last — fragile by nature)

- Cookie-based scrape of watch history every few hours (yt-dlp/Playwright with Josh's
  session cookies), dedupe against `sources`.
- **Triage gate answers Josh's question: NOT every video lands in the inbox.** Flow is
  history → LLM triage vs interest profile (music/shorts/sports/off-interest discarded,
  with reasons visible) → cards generated only for keepers → inbox for swipe approval.
  The inbox is the second gate; nothing enters reviews without approval.
- **80%-watched caveat**: YouTube's history does not expose watch percentage, so the
  YouTube equivalent of the Spotify 80% rule is approximated instead: skip Shorts,
  skip <3-min videos, and let triage + inbox filter the rest. (True watch-% would need a
  browser extension — future option.)
- Share sheet remains the always-working manual path; scraper failures degrade to that.

## Phase 5 preview (unchanged, next after 4): relevance feedback loop

Inbox rejections + card deletions/suspensions (Josh's addition) feed a nightly Claude job
that rewrites the interest profile with EXCLUDE rules; newly excluded topics auto-suspend
existing cards. This is what makes "football highlights stop appearing" permanent.
