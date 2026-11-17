BEGIN;

ALTER TABLE quiz_attempts
    DROP COLUMN is_internal;

COMMIT;
