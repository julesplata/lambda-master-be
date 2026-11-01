BEGIN;

ALTER TABLE quiz_attempts
    DROP COLUMN difficulty,
    DROP COLUMN category;

COMMIT;
