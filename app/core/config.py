from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode

# A random key this long (e.g. secrets.token_urlsafe(32), 43 chars) cannot be
# guessed online at any request rate, which is what lets the admin endpoints
# rely on per-IP limits alone.
ADMIN_API_KEY_MIN_LENGTH = 32
# HS256 is only as strong as its key; PyJWT itself warns below 32 bytes.
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    app_name: str = "Lambda API"
    # Anything but "development" turns on the startup checks in
    # _deployment_guards, so a deploy with a missing or dev-only setting refuses
    # to boot instead of serving errors. Set ENV=production on Railway.
    env: Literal["development", "staging", "production"] = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Set via the CORS_ORIGINS env var as a comma-separated list, e.g.
    # CORS_ORIGINS="https://app.example.com,https://admin.example.com"
    cors_origins: Annotated[list[str], NoDecode] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value

    # All limits are per client IP; there are no app-wide buckets (see
    # core/limiter.py for why). Several limits can be combined with ";", e.g.
    # "30/minute;500/hour" enforces both. Size them for a shared IP, not one
    # person: classrooms, offices and carrier-grade NAT put dozens of real users
    # behind one address, and a single quiz is ~14 calls.
    rate_limit_default: str = "300/minute"
    # The open, unauthenticated submit endpoints (question reports + app feedback).
    rate_limit_submit: str = "5/minute;50/hour"

    # Anonymous quiz-attempt creation writes one quiz_attempts row plus up to 100
    # user_answers rows per call, so it is tighter than the default. The minute
    # limit covers a whole class starting at once; the hourly one bounds what a
    # single address can write over time. Note an explicit per-route limit
    # replaces rate_limit_default rather than stacking with it.
    rate_limit_attempt_create: str = "30/minute;500/hour"

    # Abandoned anonymous attempts have no owner and no expiry. The
    # scripts/purge_stale_attempts.py job deletes in-progress ones older than
    # this many days. Completed attempts are kept.
    attempt_retention_days: int = 7

    # Storage backend for rate-limit counters. Empty = in-memory (per-process,
    # resets on redeploy) which is fine for a single instance. For multiple
    # instances, point this at Redis, e.g. "redis://default:pass@host:6379".
    rate_limit_storage_uri: str = ""

    # How many proxies in front of the app append to X-Forwarded-For. The client
    # IP is the entry this many places from the RIGHT; everything further left
    # was written by the client and is ignored. 1 = a single platform edge
    # (Railway). 0 = the app is exposed directly, so the header is not read at
    # all. Too high makes the limits bypassable; too low puts every user in one
    # bucket — so when unsure, err low. See SECURITY.md for how to verify it.
    trusted_proxy_hops: int = Field(default=1, ge=0)

    admin_api_key: str = ""  # set via ADMIN_API_KEY in .env
    # The admin console trades admin_api_key for a token with this lifetime, so
    # the long-lived key is never persisted in a browser. Long enough for an
    # editing session, short enough that a leaked token stops working the same day.
    admin_token_ttl_minutes: int = 480
    # Per-IP limit on the admin key exchange. It slows guessing from one address,
    # but a distributed attacker just uses more addresses, so what actually makes
    # guessing impractical is the key's length: admin routes refuse to run with a
    # key shorter than ADMIN_API_KEY_MIN_LENGTH. There is no app-wide bucket here
    # on purpose: one would let anyone lock every admin out by sending bad keys.
    rate_limit_admin_session: str = "5/minute;30/hour"

    # DEV ONLY. When set (AUTH_BYPASS_USER_ID in .env), get_current_user_id skips
    # JWT validation and returns this user id. MUST be empty in production.
    auth_bypass_user_id: str = ""

    jwt_secret: str = ""  # REQUIRED in prod; HS256 signing key (JWT_SECRET in .env)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lambda"
    # Connection pool sizing. db_pool_size is the number of persistent
    # connections; db_max_overflow is how many extra are opened under burst load.
    # Keep pool_size + max_overflow under the Postgres max_connections limit
    # (and divide by the number of web instances when scaling horizontally).
    db_pool_size: int = 10
    db_max_overflow: int = 5

    # Spaced repetition (Leitner). Index i = days until review for box (i + 1);
    # a correct answer promotes a card one box (capped at the last), a wrong one
    # resets it to box 1. Box 1 = "due immediately" so misses resurface right away.
    leitner_intervals_days: list[int] = [0, 1, 3, 7, 21]

    # Gamification XP, awarded on attempt completion per correctly-answered question:
    #   xp = xp_per_correct * difficulty_multiplier  (+ xp_review_bonus if the card
    #   was due for review). All env-overridable so the economy can be retuned.
    xp_per_correct: int = 10
    xp_difficulty_multipliers: dict[str, float] = {
        "beginner": 1.0,
        "intermediate": 1.5,
        "advanced": 2.0,
    }
    xp_review_bonus: int = 5  # extra XP per due card answered correctly in review
    # Level curve: level = floor(sqrt(xp / xp_per_level_factor)).
    xp_per_level_factor: int = 100
    # Timezone whose calendar day defines a streak boundary (IANA name).
    streak_timezone: str = "UTC"

    # PostHog product analytics. When posthog_api_key is empty the analytics
    # helpers are no-ops (no client, no network calls) so local dev and tests
    # stay quiet. posthog_host is the ingestion endpoint (US Cloud by default).
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"
    # Server-side salt for the anonymous distinct_id. Unauthenticated visitors
    # are identified to PostHog by HMAC(salt, client_ip) rather than by the raw
    # IP, so no address leaves this process. Keep it secret and stable: changing
    # it re-buckets every anonymous visitor. When empty, analytics falls
    # back to a random per-process salt — still non-reversible, but anonymous
    # ids then differ per instance and reset on every redeploy.
    analytics_ip_salt: str = ""

    @model_validator(mode="after")
    def _deployment_guards(self) -> "Settings":
        """Refuse to start a staging/production process with unsafe settings.

        Every check here is something that otherwise fails open or fails per
        request: an empty JWT_SECRET makes token verification raise on every
        call, the auth bypass authenticates anonymous requests, and DEBUG leaks
        stack traces and SQL. All problems are reported at once so one deploy
        fixes them all.
        """
        if self.env == "development":
            return self
        errors = []
        if self.debug:
            errors.append("DEBUG must be false")
        if self.auth_bypass_user_id:
            errors.append("AUTH_BYPASS_USER_ID must be empty")
        if len(self.jwt_secret) < JWT_SECRET_MIN_LENGTH:
            errors.append(
                f"JWT_SECRET must be at least {JWT_SECRET_MIN_LENGTH} characters"
            )
        if len(self.admin_api_key) < ADMIN_API_KEY_MIN_LENGTH:
            errors.append(
                f"ADMIN_API_KEY must be at least {ADMIN_API_KEY_MIN_LENGTH} characters"
            )
        if any("localhost" in o or "127.0.0.1" in o for o in self.cors_origins):
            errors.append("CORS_ORIGINS must not include localhost origins")
        if errors:
            raise ValueError(f"Unsafe settings for ENV={self.env}: " + "; ".join(errors))
        return self

    class Config:
        env_file = ".env"


settings = Settings()
