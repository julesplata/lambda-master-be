"""Delete abandoned anonymous quiz attempts, then check the database size.

Guest attempts have no owner and no expiry, so an in-progress attempt that is
never completed would otherwise live forever, and POST /quiz-attempts is open:
every call stores a row. An attempt cannot be completed without an answer, so a
script that starts and completes quizzes in a loop leaves in-progress rows that
end up here too. Completed attempts are kept: the attempt id is the only
handle a guest has on their own history.

The run then exits with status 1 when the database is larger than
DATABASE_SIZE_ALERT_MB, so a growing database shows up as a failed scheduled
run while there is still room to act.

Run from the repo root:  python -m scripts.purge_stale_attempts
"""

import asyncio
import sys

from sqlalchemy import text

from app.core.config import settings
from app.db.session import AsyncSessionLocal, engine

BATCH_SIZE = 5000

# Batched so a large backlog never holds one long transaction or a wide lock.
# make_interval(days => :retention_days) types the parameter explicitly, which
# asyncpg needs; deleting the attempt cascades to its user_answers rows.
DELETE_BATCH = text("""
    DELETE FROM quiz_attempts
    WHERE id IN (
        SELECT id FROM quiz_attempts
        WHERE completed_at IS NULL
          AND started_at < now() - make_interval(days => :retention_days)
        LIMIT :batch_size
    )
    """)

DATABASE_SIZE = text("SELECT pg_database_size(current_database())")


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


async def database_size_mb() -> float:
    async with AsyncSessionLocal() as session:
        size_bytes = (await session.execute(DATABASE_SIZE)).scalar_one()
    return size_bytes / (1024 * 1024)


async def main() -> int:
    deleted = await purge_stale_attempts()
    print(
        f"Deleted {deleted} abandoned quiz attempts "
        f"older than {settings.attempt_retention_days} days"
    )
    size_mb = await database_size_mb()
    await engine.dispose()

    print(
        f"Database size: {size_mb:.0f} MB "
        f"(alert above {settings.database_size_alert_mb} MB)"
    )
    if size_mb > settings.database_size_alert_mb:
        print("ALERT: the database is over DATABASE_SIZE_ALERT_MB", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
