# Lambda API

Backend for **Lambda**, a self-directed quiz and spaced-repetition study tool. It serves a bank of system-design questions, runs quiz attempts, schedules reviews with a Leitner system, and awards XP/levels — all over a versioned REST API.

Built with **FastAPI**, **SQLAlchemy** (async, `asyncpg`), and **PostgreSQL**. All database I/O is async.

> **Guest-only mode.** The app currently runs without user accounts: the `auth`, `stats`, and `admin_users` routers are intentionally left unmounted (see [`app/api/v1/routes.py`](app/api/v1/routes.py)). The code is kept on disk so accounts can be re-enabled later. References to JWT auth, streaks, and per-user gamification below describe that latent functionality.

---

## Quick start

```bash
# 1. Create and activate a virtualenv
python -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env        # then edit values (see Configuration)

# 4. Create the database and apply migrations
createdb lambda
psql "$DATABASE_URL" -f migrations/0001_init_schema.up.sql
psql "$DATABASE_URL" -f migrations/0002_question_title_unique_per_category.up.sql

# 5. Run the dev server (auto-reload)
python main.py
# or:  uvicorn app.main:app --reload --port 8000
```

Once running:

- API base: `http://localhost:8000/api/v1`
- Health check: `GET http://localhost:8000/api/v1/health`
- Interactive docs (Swagger): `http://localhost:8000/docs`

There is no test suite yet.

---

## Configuration

All settings live in [`app/core/config.py`](app/core/config.py) as a `pydantic-settings` class loaded from `.env`. Copy [`.env.example`](.env.example) and fill it in. See [`SECURITY.md`](SECURITY.md) for the production checklist.

Key variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | asyncpg connection string (default: `postgresql+asyncpg://postgres:postgres@localhost:5432/lambda`) |
| `ADMIN_API_KEY` | Enables admin endpoints (`X-Admin-Key` header). If empty, admin routes return 503. |
| `DEBUG` | Exposes stack traces and SQL query logs. Keep `false` in production. |
| `CORS_ORIGINS` | Comma/JSON list of allowed frontend origins. Defaults to localhost only. |
| `RATE_LIMIT_*` | Per-IP and global rate-limit windows for the open submit endpoints. |
| `RATE_LIMIT_STORAGE_URI` | Empty = in-memory (single instance). Set to a Redis URL when scaling to 2+ instances. |
| `TRUST_FORWARDED_FOR` | `true` behind a proxy/load balancer; `false` if exposed directly. |
| `POSTHOG_API_KEY` | Project analytics. Empty = analytics disabled (no client, no network calls). |
| `JWT_SECRET` / `AUTH_BYPASS_USER_ID` | Only relevant if user accounts are re-enabled. |

---

## Seeding questions

Question banks live in [`seeds/`](seeds/) as JSON. Load them through the admin bulk-create endpoint (requires the `X-Admin-Key` header):

```bash
curl -X POST http://localhost:8000/api/v1/questions/bulk \
  -H "X-Admin-Key: $ADMIN_API_KEY" \
  -H "Content-Type: application/json" \
  --data @seeds/system_design_questions.json
```

---

## API overview

All routes are mounted under `/api/v1`. Currently active routers:

| Method & path | Description |
|---------------|-------------|
| `GET /health` | Liveness check |
| `GET /categories` | List question categories |
| `GET /questions` | List questions (summaries) |
| `GET /questions/{id}` | Get a single question (options strip `is_correct`) |
| `POST /questions/bulk` | Bulk-create questions (admin) |
| `GET /tags` | List all tags |
| `POST /quiz-attempts` | Start a quiz attempt |
| `GET /quiz-attempts/{id}` | Get an attempt |
| `POST /quiz-attempts/{id}/answers` | Submit an answer (returns correctness) |
| `POST /quiz-attempts/{id}/complete` | Finish an attempt (awards XP, updates review schedule) |
| `POST /questions/{id}/reports` | Report a question (open, rate-limited) |
| `POST /feedback` | Submit app feedback (open, rate-limited) |
| `GET /admin/reports`, `PATCH /admin/reports/{id}` | Triage question reports (admin) |
| `GET /feedback`, `PATCH /feedback/{id}` | Triage feedback (admin) |

> Auth (`/auth`), per-user stats (`/stats`), and admin user management are present in the codebase but unmounted in guest-only mode.

---

## Architecture

### Request flow

```
Request → SlowAPI rate-limit middleware → Analytics middleware → CORS middleware
        → app/api/v1/routes.py (health + sub-routers)
            → endpoints/{questions,attempts,categories,tags,reports,feedback}.py
        → deps.py (auth guards)
        → db/session.py (AsyncSession via get_session dependency)
        → models/models.py (SQLAlchemy ORM)
```

### Project layout

```
app/
├── main.py                 # FastAPI app, middleware, router mount
├── api/
│   ├── deps.py             # Auth guards (JWT user id, X-Admin-Key)
│   └── v1/
│       ├── routes.py       # Versioned router (mounts sub-routers)
│       └── endpoints/      # One module per domain
├── core/
│   ├── config.py           # pydantic-settings (loaded from .env)
│   ├── security.py         # Password hashing, JWT
│   ├── leveling.py         # Pure XP/level math
│   ├── spaced_repetition.py# Pure Leitner scheduler
│   ├── limiter.py          # SlowAPI rate limiter
│   └── analytics*.py       # PostHog client + middleware
├── db/                     # Async engine + session
├── models/models.py        # SQLAlchemy ORM (single file)
└── schemas/                # Pydantic request/response schemas (one file per domain)
migrations/                 # Numbered SQL migrations (applied manually with psql)
seeds/                      # Question bank JSON
```

### Key design decisions

**Gamification** (on attempt completion): XP = `xp_per_correct × difficulty_multiplier` plus an optional `xp_review_bonus` when the card was due. Level is computed on read as `floor(sqrt(xp / xp_per_level_factor))`. A daily streak advances once per calendar day and resets on a missed day. Weights are configurable in `Settings`; pure math lives in [`app/core/leveling.py`](app/core/leveling.py).

**Spaced repetition** (Leitner): 5 boxes with configurable intervals (default `0/1/3/7/21` days). Correct → promote one box (capped); wrong → reset to box 1. The `review` quiz mode queries cards with `due_at <= now()`. Pure scheduler in [`app/core/spaced_repetition.py`](app/core/spaced_repetition.py).

**Answer protection:** quiz options are returned without `is_correct` (`OptionPublic`); the correct answer is only revealed via `AnswerResult` after a submission.

**Auth (latent):** JWT access tokens (15 min, HS256) plus rotating refresh tokens. Only the SHA-256 hash of a refresh token is stored.

### Migrations

Plain SQL files in [`migrations/`](migrations/), numbered `NNNN_description.{up,down}.sql`, applied manually with `psql`. **Never edit a migration after it has been applied — write a new one instead.**

```bash
# Apply
psql "$DATABASE_URL" -f migrations/0001_init_schema.up.sql

# Roll back
psql "$DATABASE_URL" -f migrations/0001_init_schema.down.sql
```

---

## Deployment

A [`Procfile`](Procfile) is included for platforms like Railway/Heroku:

```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Behind a proxy or load balancer, set `TRUST_FORWARDED_FOR=true`. When running 2+ instances, point `RATE_LIMIT_STORAGE_URI` at Redis so per-IP and global rate limits stay consistent across processes. Review [`SECURITY.md`](SECURITY.md) before going to production.

---

## Further reading

- [`CLAUDE.md`](CLAUDE.md) — architecture deep-dive and deferred-decision rationale
- [`SECURITY.md`](SECURITY.md) — production security checklist
