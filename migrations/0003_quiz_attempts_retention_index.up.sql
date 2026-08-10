-- 0003: index supporting the abandoned-attempt retention job.
--
-- scripts/purge_stale_attempts.py deletes anonymous attempts that were never
-- completed and are older than ATTEMPT_RETENTION_DAYS. Without this index that
-- predicate is a sequential scan over quiz_attempts, which is exactly the table
-- an abuse burst inflates. The index is partial so it only covers in-progress
-- rows: completed attempts leave it as soon as completed_at is set, keeping it
-- small no matter how much history accumulates.
--
-- Plain CREATE INDEX rather than CONCURRENTLY: the latter cannot run inside a
-- transaction block, and this repo wraps every migration in BEGIN/COMMIT.

BEGIN;

CREATE INDEX idx_quiz_attempts_incomplete_started_at
    ON quiz_attempts (started_at)
    WHERE completed_at IS NULL;

COMMIT;
