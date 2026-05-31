from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "Lambda API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]

    rate_limit_default: str = "60/minute"

    admin_api_key: str = ""  # set via ADMIN_API_KEY in .env

    # DEV ONLY. When set (AUTH_BYPASS_USER_ID in .env), get_current_user_id skips
    # JWT validation and returns this user id. MUST be empty in production.
    auth_bypass_user_id: str = ""

    jwt_secret: str = ""  # REQUIRED in prod; HS256 signing key (JWT_SECRET in .env)
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/lambda"

    # Spaced repetition (Leitner). Index i = days until review for box (i + 1);
    # a correct answer promotes a card one box (capped at the last), a wrong one
    # resets it to box 1. Box 1 = "due immediately" so misses resurface right away.
    leitner_intervals_days: list[int] = [0, 1, 3, 7, 21]

    # Gamification XP, awarded on attempt completion per correctly-answered question:
    #   xp = xp_per_correct * difficulty_multiplier  (+ xp_review_bonus if the card
    #   was due for review). All env-overridable so the economy can be retuned.
    xp_per_correct: int = 10
    xp_difficulty_multipliers: dict[str, float] = {
        "easy": 1.0,
        "medium": 1.5,
        "hard": 2.0,
    }
    xp_review_bonus: int = 5  # extra XP per due card answered correctly in review
    # Level curve: level = floor(sqrt(xp / xp_per_level_factor)).
    xp_per_level_factor: int = 100
    # Timezone whose calendar day defines a streak boundary (IANA name).
    streak_timezone: str = "UTC"

    class Config:
        env_file = ".env"


settings = Settings()
