"""Delete abandoned anonymous quiz attempts.

Guest attempts have no owner and no expiry, so an in-progress attempt that is
never completed would otherwise live forever -- and POST /quiz-attempts writes up
to 101 rows per call. Completed attempts are kept: the attempt id is the only
handle a guest has on their own history.

Run from the repo root:  python -m scripts.purge_stale_attempts
"""

import asyncio

from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine

BATCH_SIZE = 5000

# Batched so a large backlog never holds one long transaction or a wide lock.
# make_interval(days => :retention_days) types the parameter explicitly, which
# asyncpg needs; deleting the attempt cascades to its user_answers rows.
DELETE_BATCH = text(
    """
    DELETE FROM quiz_attempts
    WHERE id IN (
        SELECT id FROM quiz_attempts
        WHERE completed_at IS NULL
          AND started_at < now() - make_interval(days => :retention_days)
        LIMIT :batch_size
    )
    """
)


async def purge_stale_attempts() -> int:
    """Delete abandoned attempts in batches. Returns the number deleted."""
    deleted_total = 0
    async with AsyncSessionLocal() as session:
        while True:
            result = await session.execute(
                DELETE_BATCH.bindparams(
                    retention_days=settings.attempt_retention_days,
                    batch_size=BATCH_SIZE,
                )
            )
            await session.commit()
            if result.rowcount == 0:
                return deleted_total
            deleted_total += result.rowcount


async def main() -> None:
    deleted = await purge_stale_attempts()
    print(
        f"Deleted {deleted} abandoned quiz attempts "
        f"older than {settings.attempt_retention_days} days"
    )
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
