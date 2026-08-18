from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


class Settings(BaseSettings):
    app_name: str = "Lambda API"
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

    rate_limit_default: str = "60/minute"
    # Coarse global backstop on the open, unauthenticated submit endpoints
    # (question reports + app feedback), applied on top of the per-IP limit.
    rate_limit_submit: str = "5/minute"
    rate_limit_submit_global: str = "200/hour"

    # Anonymous quiz-attempt creation writes one quiz_attempts row plus up to 100
    # user_answers rows per call, so it gets its own buckets rather than sharing
    # the reports/feedback budget. The global cap is an emergency ceiling, not a
    # throttle: keep it well above real peak traffic, since exhausting it locks
    # out everyone. Note an explicit per-route limit replaces rate_limit_default
    # rather than stacking with it, so the per-IP value must be tighter on its own.
    rate_limit_attempt_create: str = "10/minute"
    rate_limit_attempt_global: str = "2000/hour"

    # Abandoned anonymous attempts have no owner and no expiry. The
    # scripts/purge_stale_attempts.py job deletes in-progress ones older than
    # this many days. Completed attempts are kept.
    attempt_retention_days: int = 7

    # Storage backend for rate-limit counters. Empty = in-memory (per-process,
    # resets on redeploy) which is fine for a single instance. For multiple
    # instances, point this at Redis, e.g. "redis://default:pass@host:6379".
    rate_limit_storage_uri: str = ""

    # Trust X-Forwarded-For to determine the client IP for rate limiting.
    # MUST be true behind a proxy/load balancer (e.g. Railway), otherwise every
    # request shares one rate bucket. MUST be false when the app is exposed
    # directly, since the header is then client-spoofable.
    trust_forwarded_for: bool = True

    admin_api_key: str = ""  # set via ADMIN_API_KEY in .env
    # The admin console trades admin_api_key for a token with this lifetime, so
    # the long-lived key is never persisted in a browser. Long enough for an
    # editing session, short enough that a leaked token stops working the same day.
    admin_token_ttl_minutes: int = 480
    # Limits on the admin key exchange. The key is a single shared secret with no
    # lockout, so these are what make guessing it impractical. The per-IP limit
    # alone only costs an attacker more addresses, so a global bucket caps the
    # whole endpoint no matter how many IPs the guesses come from. Both count
    # every call, not just failures: under a sustained distributed attack the
    # global bucket will lock out real sign-ins too, which is the intended
    # trade — already-signed-in consoles keep working on their existing token.
    rate_limit_admin_session: str = "5/minute"
    rate_limit_admin_session_global: str = "50/hour"

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
    # middleware is a no-op (no client, no network calls) so local dev and tests
    # stay quiet. posthog_host is the ingestion endpoint (US Cloud by default).
    posthog_api_key: str = ""
    posthog_host: str = "https://us.i.posthog.com"

    class Config:
        env_file = ".env"


settings = Settings()
