BEGIN;

DROP VIEW analytics_answers;
DROP VIEW analytics_attempts;

ALTER TABLE questions
    DROP COLUMN content_updated_at;

COMMIT;
