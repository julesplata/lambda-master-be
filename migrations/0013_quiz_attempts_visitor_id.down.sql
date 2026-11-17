BEGIN;

DROP INDEX IF EXISTS idx_quiz_attempts_visitor_started;

ALTER TABLE quiz_attempts
    DROP COLUMN visitor_id;

COMMIT;
