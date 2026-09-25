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

Every limit is keyed **per client IP**, using a moving window. The open write
endpoints carry their own, tighter limits:

- `POST /quiz-attempts`: `RATE_LIMIT_ATTEMPT_CREATE` (default `30/minute;500/hour`)
- `POST /questions/{id}/reports`, `POST /feedback`: `RATE_LIMIT_SUBMIT`
  (default `5/minute;50/hour`)
- Everything else: `RATE_LIMIT_DEFAULT` (default `300/minute`)

**There are no app-wide buckets, and none should be added.** A counter shared by
every client is a kill switch: an attacker who sends enough requests blocks all
real users until the window resets, and organic spikes hit the same wall. The
hourly per-IP windows bound sustained abuse from one address. Abuse spread
across many addresses has to be stopped at the edge (Cloudflare WAF rules, or
Turnstile on quiz start), not with a counter real users share.

Size the per-IP values for a shared address, not one person: classrooms, offices
and mobile carrier-grade NAT put dozens of users behind one IP, and a 10-question
quiz is ~14 API calls.

Client IP is resolved in `app/core/limiter.py`. **Behind a proxy/load balancer
(Railway) the TCP peer is the proxy**, so without special handling every request
would share a single rate bucket. So the limiter reads `X-Forwarded-For`, but
**never its leftmost entry**: the client writes that one, and each proxy only
appends to the right. `TRUSTED_PROXY_HOPS` (default `1`) is how many entries,
counted from the right, were written by proxies you control; the limiter uses
the entry at that position and ignores everything to its left.

- Behind one platform edge (Railway): `TRUSTED_PROXY_HOPS=1`.
- Behind Cloudflare *and* Railway, or nginx in front of the app: add one per
  proxy that appends to the header.
- App exposed directly to clients: `TRUSTED_PROXY_HOPS=0`. The header is not
  read at all and the TCP peer address is used.

The setting fails in two directions, so verify it after each deploy that
changes the network path:

- **Too high → the limits are bypassable.** Check: send 6 requests to
  `POST /api/v1/admin/session`, each with a different
  `-H "X-Forwarded-For: $RANDOM.1.1.1"`. The 6th must return 429.
- **Too low → every user shares one bucket.** Check: exhaust that limit from
  one network (e.g. your laptop), then call it from another (e.g. a phone on
  mobile data). The second must not get 429.

Railway's staff have described its edge both ways (stripping the header vs.
appending to it), which is why the right-hand count is used: it is correct in
either case as long as the hop count is.

> Note: SlowAPI's default limiter store is in-memory, so limits are per-process
> and reset on redeploy. For multi-instance deployments, set
> `RATE_LIMIT_STORAGE_URI` to Redis, or each instance multiplies every limit. If
> Redis is unreachable the limiter falls back to in-memory counters rather than
> failing requests.

## Admin endpoints

Admin routes (`/admin/questions*`, `/admin/reports*`, `/feedback/admin*`,
`/questions/bulk`) accept **either** credential:

- `X-Admin-Key` — the raw shared secret, compared with `secrets.compare_digest`
  (constant-time). For seeding scripts and curl.
- `Authorization: Bearer <token>` — a short-lived admin session token from
  `POST /admin/session`. For the browser console, so the long-lived key is never
  persisted in browser storage.

The guard fails closed: if `ADMIN_API_KEY` is unset **or shorter than 32
characters**, all of it returns 503. The public quiz keeps working.

- Use a long, random key (e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`).
- Never log it; only send it over HTTPS.
- There is no lockout. **The key's length is the defence against online
  guessing**, not the rate limit: a 32+ character random key cannot be guessed
  at any request rate, from any number of addresses.
- The key exchange is rate limited per IP (`RATE_LIMIT_ADMIN_SESSION`, default
  `5/minute;30/hour`), which slows guessing from one address. There is
  deliberately no app-wide limit: one would let anyone lock every admin out by
  sending bad keys.

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
- [ ] **Apply migration `0005`** (any time; order-independent of the deploy).
      It shuffles stored option positions, which had the correct answer first
      for almost every seeded question.
- [ ] `ENV=production` — turns on the startup checks: the process refuses to
      boot (and says why) if `DEBUG` is on, `AUTH_BYPASS_USER_ID` is set,
      `JWT_SECRET` or `ADMIN_API_KEY` is under 32 characters, or `CORS_ORIGINS`
      still includes localhost. Without it none of the items below are enforced.
- [ ] `DEBUG=false` — leaving it on exposes stack traces and SQL query logs.
- [ ] `ADMIN_API_KEY` — long random value; without it admin routes are disabled.
- [ ] `AUTH_BYPASS_USER_ID` — must be **empty/unset**; it short-circuits JWT auth.
- [ ] `JWT_SECRET` — long random value. **Required**, even in guest-only mode:
      admin session tokens are signed with it, so `POST /admin/session` returns
      503 without it and the admin console cannot sign in. (It is separately
      needed if user accounts are re-enabled.)
- [ ] `CORS_ORIGINS` — set to your real frontend origin(s); the default is
      localhost-only. Do not use `*` together with `allow_credentials=true`.
- [ ] `TRUSTED_PROXY_HOPS=1` on Railway, and run both checks under rate
      limiting above. Remove the old `TRUST_FORWARDED_FOR` variable; it is no
      longer read.
- [ ] `ANALYTICS_IP_SALT` — long random value, set whenever `POSTHOG_API_KEY`
      is. Unauthenticated visitors are reported to PostHog as
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
