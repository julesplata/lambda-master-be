BEGIN;

ALTER TABLE quiz_attempts
    DROP COLUMN source;

COMMIT;
