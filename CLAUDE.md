# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Run the dev server (auto-reload)
python main.py
# or
uvicorn app.main:app --reload --port 8000

# Activate virtualenv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Apply a migration
psql "$DATABASE_URL" -f migrations/0001_init_schema.up.sql

# Roll back a migration
psql "$DATABASE_URL" -f migrations/0001_init_schema.down.sql

# Seed questions
# Load seeds/*.json question files via the POST /api/v1/questions/bulk endpoint (requires X-Admin-Key header)

# Regenerate the question inventory (validates seeds + rewrites seeds/coverage_report.md)
python seeds/generate_coverage.py

# Delete abandoned guest attempts (run on a schedule in production; safe to run by hand)
python -m scripts.purge_stale_attempts
```

**Adding seed questions:** read [seeds/system_design_coverage.md](seeds/system_design_coverage.md) first — it explains the `concept`/`format` fields, the dedup rules, and the generated `seeds/coverage_report.md` inventory (never hand-edit that report; rerun the script after changing seeds).

There is no test suite yet.

## Architecture

**Stack:** FastAPI + SQLAlchemy (async, `asyncpg`) + PostgreSQL. All DB I/O is async.

**Entry point:** [main.py](main.py) → [app/main.py](app/main.py). The app mounts a single versioned router at `/api/v1` (configured via `settings.api_v1_prefix`).

### Request flow

```
Request → SlowAPI rate-limit middleware → CORS middleware
        → app/api/v1/routes.py (health + sub-routers)
            → endpoints/{auth,questions,attempts,tags,stats,admin_users}.py
        → deps.py (auth: get_current_user_id / require_admin)
        → db/session.py (AsyncSession via get_session dependency)
        → models/models.py (SQLAlchemy ORM)
```

### Key design decisions

**Auth:** JWT access tokens (15 min TTL, HS256) + rotating refresh tokens. Only the SHA-256 hash of the refresh token is stored in `refresh_tokens`; the raw token is returned once. Signup/login are rate-limited to 10/min via SlowAPI.

**Two auth guards in `deps.py`:**
- `get_current_user_id` — Bearer JWT, returns `uuid.UUID`; used by all user-facing endpoints
- `require_admin` — accepts *either* the `X-Admin-Key` header (compared via `secrets.compare_digest`; used by seeding scripts and curl) *or* a short-lived admin session token as `Authorization: Bearer`. Used by question bulk-create, the admin question console, reports, feedback and admin user endpoints.

**Admin sessions:** `POST /admin/session` trades `ADMIN_API_KEY` for a JWT with `type: "admin"` and no subject (admin access is a capability, not an identity), TTL `admin_token_ttl_minutes`. This exists so the browser console never has to persist the long-lived key. The exchange is rate-limited per IP (`rate_limit_admin_session`) because the key is one shared secret with no lockout, so that limit is what makes online guessing impractical. Requires `JWT_SECRET`; returns 503 without it.

**Questions are soft-deleted, never dropped:** `questions.archived_at` (migration `0004`). `user_answers.question_id` is `ON DELETE CASCADE`, so a real delete would erase the answer rows of every past attempt that used the question and leave `quiz_attempts.score` pointing at answers that no longer exist. Archiving keeps history intact and makes the console's "Undo" a genuine restore. **Every public read path must filter `archived_at IS NULL`** — the browse list, question detail, and new-attempt sampling all do; the attempt *review* path deliberately does not, since a learner must still see a question they already answered. The unfiltered `TABLESAMPLE` fast path in `attempts.py` oversamples 2× and trims with `LIMIT`, because the filter is applied after the sample.

**Gamification (on `complete_attempt`):**
- XP = `xp_per_correct × difficulty_multiplier` + optional `xp_review_bonus` if the card was due
- Level = `floor(sqrt(xp / xp_per_level_factor))` — computed on read, not stored
- Daily streak: advances once per calendar day (idempotent), resets to 1 on a missed day
- Pure math lives in `core/leveling.py`; weights are in `Settings`

**Spaced repetition (Leitner):**
- 5 boxes with configurable intervals (default: 0/1/3/7/21 days)
- Correct → promote one box (capped); wrong → reset to box 1
- `UserQuestionStat` is an upserted rollup per `(user_id, question_id)` — the `review` quiz mode queries `due_at <= now()` against this table
- Pure scheduler in `core/spaced_repetition.py`

**Rate limiting the open write surface:** the three unauthenticated write endpoints each carry an explicit per-IP limit plus a global backstop keyed by a constant. Note that an explicit `@limiter.limit` *replaces* `rate_limit_default` for that route rather than stacking with it (SlowAPI's `override_defaults` is `True` by default), so each per-IP value has to stand on its own. Reports and feedback share the `submit-global` bucket; attempt creation deliberately has its own (`attempt-create-global`, `rate_limit_attempt_*`) because it is the app's primary user action and writes up to 101 rows per call — sharing the 200/hour submit budget would throttle normal use. A global bucket is a self-DoS surface, so size it as an emergency ceiling, not a throttle.

**Analytics never sees a raw IP:** the per-request PostHog event is keyed by the authenticated user id when a valid access token is present, and by `HMAC(analytics_ip_salt, client_ip)` — truncated, prefixed `anon-` — when there is not, which in guest-only mode is every request. Hashing without a salt would be theatre (the IPv4 space is small enough to brute-force a digest back to an address), so `ANALYTICS_IP_SALT` must be a real secret and must stay stable: rotating it re-buckets every anonymous visitor. When it is unset the middleware falls back to a random per-process salt — never a constant — which keeps IPs in but makes anonymous ids per-instance and reset-on-redeploy, so set it in production. The salt is the *only* thing standing between the analytics vendor and the addresses, since there is no consent banner.

**Guest attempt retention:** anonymous attempts have no owner and no expiry, so `scripts/purge_stale_attempts.py` deletes those left in progress (`completed_at IS NULL`) beyond `attempt_retention_days`, in batches; `user_answers` rows go with them via `ON DELETE CASCADE`. Completed attempts are kept — the attempt id is a guest's only handle on their own history. Migration `0003` adds the partial index the purge predicate needs. The job needs an external scheduler (see the SECURITY.md checklist); nothing in the app runs it.

**Migrations:** Plain SQL files in `migrations/`, numbered `NNNN_description.{up,down}.sql`. Applied manually with `psql`. Never edit a migration after it has been applied; write a new one instead.

### Configuration

All settings live in `core/config.py` as a `pydantic-settings` `BaseSettings` class loaded from `.env`. Key env vars:

| Var | Purpose |
|-----|---------|
| `DATABASE_URL` | asyncpg connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/lambda`) |
| `JWT_SECRET` | HS256 signing key (required in production) |
| `ADMIN_API_KEY` | Enables the admin endpoints |
| `DEBUG` | Enables SQLAlchemy query logging |
| `ANALYTICS_IP_SALT` | Salt for the anonymous PostHog `distinct_id` (see the analytics note above) |

### Schemas vs Models

- `app/models/models.py` — SQLAlchemy ORM models (single file)
- `app/schemas/` — Pydantic request/response schemas, one file per domain (`auth`, `question`, `attempt`, `stats`, `user`)

Options are returned without `is_correct` to the client in quiz context (`OptionPublic`); the correct answer is only revealed via `AnswerResult` after the user submits.

`GET /quiz-attempts/{id}` returns `AttemptQuestion`, which extends `QuestionDetail` with this attempt's answer to each question so a client that lost its in-memory state (a page refresh) can rebuild it. The answer key half of that (`correct_option_id`, `explanation`) is filled in **only for questions already answered**, matching what `AnswerResult` returned at the time: an attempt is readable by anyone holding its id, so populating it earlier would hand out the answers to the rest of the quiz. The endpoint also orders its questions by `user_answers.id`, which is what makes a resume see the same quiz twice; the id is a random UUID, so the order is arbitrary but stable, and stable is the only property a resume needs.

## Deferred decisions

**Server-side quiz sessions (hide upcoming questions):** Considered an approach where the server holds the picked questions and exposes only "current question" so the full list never reaches the client — preventing cheating *within* an attempt. Deferred. Rationale: this is a self-directed spaced-repetition tool with no graded exams or stakes, so the incentive to cheat is near zero, and answers are already protected (`OptionPublic` strips `is_correct`). When it does become a requirement, build it DB-backed (a `quiz_sessions` table with picked question IDs + a cursor), not in-memory — in-memory state breaks JWT statelessness and doesn't survive `--reload` or horizontal scaling. Revisit when attempts carry weight (graded exams, competitive leaderboards).

**Redis — only when scaling horizontally:** Not a runtime dependency. The single legitimate use today is shared rate-limit state: SlowAPI counters live in-process (`core/limiter.py`), so with 2+ web instances the per-IP limits fragment (effective limit becomes `limit × N`) and the global submit bucket (`submit_global_key`) breaks entirely since each process has its own "global". The fix is already wired: set `RATE_LIMIT_STORAGE_URI` to a Redis URL — no code change. Decision rule: **single instance → no Redis; scale to 2+ instances → set `RATE_LIMIT_STORAGE_URI`.** Do NOT add Redis for caching (reads are small, Postgres-backed, no measured pressure), sessions (stateless JWT + DB refresh-token hashes), or quiz state (see above — DB-backed when needed). Adding it for those now is over-engineering.

# Engineering Standards

## Maintainability First

- Readability over cleverness
- Explicit code over abstractions
- Favor simple solutions
- Prefer duplication over premature abstraction


## Naming

- No abbreviations
- No single-letter variables
- Functions should clearly describe intent

## Code Size

- Functions < 30 lines
- Files < 300 lines where practical

## Design Patterns

Do not introduce:
- Factory Pattern
- Strategy Pattern
- Generic Base Classes

unless explicitly requested.

## Copy Style

No em dashes (—) in user-facing data, output, or text (error messages, seed question content, generated reports, etc.). Use a comma, colon, semicolon, or period instead, whichever reads naturally, keeping the wording otherwise unchanged. Code comments and internal docs are exempt.

## Output Format

Before coding:
1. Explain tradeoffs