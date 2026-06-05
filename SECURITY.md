# Security Notes

Practical security guidance for this API. Covers the controls in place and the
deployment-time settings you must get right (especially on Railway).

## SQL injection

Not a concern as written. All database access goes through SQLAlchemy's
expression API (`select(...).where(Column == value)`), which sends values as
bound parameters — they are never interpolated into SQL text. Path/query/body
values are also coerced to typed Python objects (e.g. `uuid.UUID`) by
FastAPI/Pydantic before reaching a query.

**Rule:** never build SQL with `text(f"... {user_input} ...")`. If you ever need
raw SQL, pass parameters via bound params (`text("... :id"), {"id": value}`),
not f-strings.

## Cross-site scripting (XSS) — output escaping is the frontend's job

`question_reports.comment` and `app_feedback.message` are free-form user text
submitted by unauthenticated guests. The API stores them **raw and unmodified**
(correct — sanitizing on store loses data and is the wrong layer).

Because these strings are later shown in an admin view, any renderer **must
HTML-escape them on output**. A report comment containing
`<script>...</script>` will execute in the admin's browser if rendered with
`innerHTML` / `dangerouslySetInnerHTML` / unescaped templating.

- React/Vue/Angular default text binding escapes automatically — safe.
- Do **not** use `innerHTML`, `dangerouslySetInnerHTML`, or `v-html` on these
  fields without sanitizing first.

## Rate limiting & the proxy assumption

The open submit endpoints (`POST /questions/{id}/reports`, `POST /feedback`)
are unauthenticated and write to the database, so they are rate limited:

- Per-IP: `rate_limit_submit` (default `5/minute`)
- Global backstop across all clients: `rate_limit_submit_global` (default
  `200/hour`)

Client IP is resolved in `app/core/limiter.py`. **Behind a proxy/load balancer
(Railway) the TCP peer is the proxy**, so without special handling every request
would share a single rate bucket. The `trust_forwarded_for` setting (default
`true`) makes the limiter use the leftmost `X-Forwarded-For` entry instead.

- Deployed behind a proxy (Railway, nginx, Cloudflare): keep
  `TRUST_FORWARDED_FOR=true`.
- App exposed directly to clients: set `TRUST_FORWARDED_FOR=false`. The header
  is client-spoofable when there is no trusted proxy to overwrite it.

> Note: SlowAPI's default limiter store is in-memory, so limits are per-process
> and reset on redeploy. For multi-instance deployments, back it with Redis.

## Admin endpoints

Admin read/triage routes (`/admin/reports*`, `/feedback/admin*`) require the
`X-Admin-Key` header, compared with `secrets.compare_digest` (constant-time).
The guard fails closed: if `ADMIN_API_KEY` is unset the routes return 503.

- Use a long, random key (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- Never log it; only send it over HTTPS.

## Production deployment checklist (Railway)

Set these as Railway environment variables:

- [ ] `DEBUG=false` — leaving it on exposes stack traces and SQL query logs.
- [ ] `ADMIN_API_KEY` — long random value; without it admin routes are disabled.
- [ ] `AUTH_BYPASS_USER_ID` — must be **empty/unset**; it short-circuits JWT auth.
- [ ] `JWT_SECRET` — long random value (required if auth is re-enabled).
- [ ] `CORS_ORIGINS` — set to your real frontend origin(s); the default is
      localhost-only. Do not use `*` together with `allow_credentials=true`.
- [ ] `TRUST_FORWARDED_FOR=true` on Railway (see rate limiting above).
- [ ] Serve only over HTTPS (Railway does this at its edge by default).
