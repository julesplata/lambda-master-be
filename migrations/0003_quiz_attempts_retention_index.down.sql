-- Revert 0003: drop the partial retention index.

BEGIN;

DROP INDEX IF EXISTS idx_quiz_attempts_incomplete_started_at;

COMMIT;
