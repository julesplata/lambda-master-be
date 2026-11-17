BEGIN;

ALTER TABLE user_answers
    DROP COLUMN time_spent_ms;

ALTER TABLE quiz_attempts
    DROP COLUMN repeated_question_ids;

COMMIT;
