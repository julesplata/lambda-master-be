"""Leitner spaced-repetition scheduling.

Pure helpers (no DB/session) so the box/due-date math is unit-testable and shared
by the stats-upsert path today and the "review my mistakes" feature later. The
``due_at`` field they produce is the only contract callers depend on, so the
scheduler could be swapped for SM-2 without touching the rest of the app.
"""

from datetime import datetime, timedelta

from app.core.config import settings


def max_box() -> int:
    """Highest Leitner box, i.e. the number of configured intervals."""
    return len(settings.leitner_intervals_days)


def next_box(current_box: int, correct: bool) -> int:
    """Promote one box on a correct answer (capped), reset to box 1 on a miss."""
    if not correct:
        return 1
    return min(current_box + 1, max_box())


def due_at_for_box(box: int, *, now: datetime) -> datetime:
    """When a card in ``box`` should next resurface, measured from ``now``."""
    intervals = settings.leitner_intervals_days
    # Boxes are 1-based; clamp defensively so a bad/legacy box never indexes out.
    idx = min(max(box, 1), len(intervals)) - 1
    return now + timedelta(days=intervals[idx])


def schedule(current_box: int, correct: bool, *, now: datetime) -> tuple[int, datetime]:
    """Return the ``(box, due_at)`` for a card after an answer with outcome ``correct``."""
    box = next_box(current_box, correct)
    return box, due_at_for_box(box, now=now)
