-- Record where each quiz was started (C3): home_hero, topic_guide,
-- results_retry and so on, or "other" for a value the API does not know.
-- NULL on every earlier row, and for a client that sends none.

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN source VARCHAR(30);

COMMIT;
