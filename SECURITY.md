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

Admin routes (`/admin/questions*`, `/admin/reports*`, `/feedback/admin*`,
`/questions/bulk`) accept **either** credential:

- `X-Admin-Key` — the raw shared secret, compared with `secrets.compare_digest`
  (constant-time). For seeding scripts and curl.
- `Authorization: Bearer <token>` — a short-lived admin session token from
  `POST /admin/session`. For the browser console, so the long-lived key is never
  persisted in browser storage.

The guard fails closed: if `ADMIN_API_KEY` is unset, all of it returns 503.

- Use a long, random key (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- Never log it; only send it over HTTPS.
- The key exchange is rate limited two ways, and these are the only things
  standing between the key and online guessing — there is no lockout, so do not
  raise them casually:
  - per IP (`RATE_LIMIT_ADMIN_SESSION`, default `5/minute`)
  - globally (`RATE_LIMIT_ADMIN_SESSION_GLOBAL`, default `50/hour`), because a
    per-IP limit only costs a distributed attacker more addresses

  Both count every call rather than only failures, so a sustained distributed
  attack will exhaust the global bucket and lock out real sign-ins as well.
  That is the intended trade: consoles already holding a token keep working.
  With the default in-memory limiter store both caps are per-process and reset
  on redeploy — set `RATE_LIMIT_STORAGE_URI` to Redis on more than one instance
  or the global cap is fiction.

### Rotating the admin key revokes live sessions

Admin tokens carry `akf`, a truncated SHA-256 of the `ADMIN_API_KEY` that minted
them, re-derived from the environment and checked on every request. Changing the
env var changes the fingerprint, so sessions opened with the previous key fail on
their next call rather than staying valid for the rest of their 8-hour TTL.

This means **rotating `ADMIN_API_KEY` is the sign-out-everywhere button** — reach
for it if the key leaks or a machine with an open console goes missing. It is not
a substitute for rotating `JWT_SECRET`: anyone who can forge signatures can copy
the fingerprint out of any token they have seen, since a JWT payload is signed
but not encrypted.

### The admin console page is public; the data behind it is not

The console at `/admin` on the frontend is a static page anyone can load. It
holds no secrets — every request it makes is rejected without a valid
credential, and the sign-in screen is all an anonymous visitor can reach. If you
want the page itself unreachable, put it behind Vercel password protection or an
IP allowlist; that is defence in depth, not a substitute for the key.

## Production deployment checklist (Railway)

Set these as Railway environment variables:

- [ ] **Apply migration `0004` before deploying the backend.** It adds
      `questions.archived_at`, which every question query now filters on. Deploy
      the code first and reads fail against the old schema.
- [ ] `DEBUG=false` — leaving it on exposes stack traces and SQL query logs.
- [ ] `ADMIN_API_KEY` — long random value; without it admin routes are disabled.
- [ ] `AUTH_BYPASS_USER_ID` — must be **empty/unset**; it short-circuits JWT auth.
- [ ] `JWT_SECRET` — long random value. **Required**, even in guest-only mode:
      admin session tokens are signed with it, so `POST /admin/session` returns
      503 without it and the admin console cannot sign in. (It is separately
      needed if user accounts are re-enabled.)
- [ ] `CORS_ORIGINS` — set to your real frontend origin(s); the default is
      localhost-only. Do not use `*` together with `allow_credentials=true`.
- [ ] `TRUST_FORWARDED_FOR=true` on Railway (see rate limiting above).
- [ ] `ANALYTICS_IP_SALT` — long random value, set whenever `POSTHOG_API_KEY`
      is. Unauthenticated requests are reported to PostHog as
      `HMAC(salt, client_ip)`, so the salt is what keeps client IPs inside
      your infrastructure. Unset falls back to a random per-process salt:
      still non-reversible, but anonymous ids then differ per instance and
      reset on every redeploy. Keep it stable — rotating it re-buckets every
      anonymous visitor.
- [ ] Serve only over HTTPS (Railway does this at its edge by default).
- [ ] Schedule the abandoned-attempt purge — add a Railway Cron service running
      `python -m scripts.purge_stale_attempts` (suggested schedule: `0 3 * * *`).
      `POST /quiz-attempts` is open and writes up to 101 rows per call; without
      this job, attempts left in progress accumulate permanently.
