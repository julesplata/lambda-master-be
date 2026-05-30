"""XP, level, and streak math for gamification.

Pure helpers (no DB/session) mirroring ``spaced_repetition.py`` so the economy is
unit-testable and the weights stay in ``config.py``. ``complete_attempt`` calls
these and persists the results.
"""

import math
from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.core.config import settings


def level_for_xp(xp: int) -> int:
    """Derived level for a total XP. Level 0 at 0 XP, growing with sqrt(xp)."""
    if xp <= 0:
        return 0
    return int(math.isqrt(xp // settings.xp_per_level_factor))


def xp_for_correct(difficulty: str, *, was_due: bool) -> int:
    """XP for a single correctly-answered question.

    Base XP scaled by the question's difficulty, plus a flat bonus when the card
    was due for spaced-repetition review — so revising a weak spot pays more than
    grinding a fresh easy question.
    """
    multiplier = settings.xp_difficulty_multipliers.get(difficulty, 1.0)
    earned = settings.xp_per_correct * multiplier
    if was_due:
        earned += settings.xp_review_bonus
    return int(earned)


def streak_day(now: datetime) -> date:
    """Calendar day (in the configured streak timezone) that ``now`` falls on."""
    return now.astimezone(ZoneInfo(settings.streak_timezone)).date()


def next_streak(current_streak: int, last_activity: date | None, today: date) -> int:
    """New ``current_streak`` after activity on ``today``.

    Same day as last activity → unchanged (multiple attempts don't double-count).
    Exactly the day after → +1. Any larger gap (or first ever) → reset to 1.
    """
    if last_activity is None:
        return 1
    delta = (today - last_activity).days
    if delta <= 0:
        return current_streak  # already counted today (or clock skew)
    if delta == 1:
        return current_streak + 1
    return 1  # missed at least one day
