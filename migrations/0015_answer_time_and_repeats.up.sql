-- Store time per answer and which of a quiz's questions were repeats (C2).
--
-- quiz_attempts.repeated_question_ids: the picked questions that were in the
-- browser's seen list when the quiz started, an empty array when none were.
-- The seen list itself is still not stored.
--
-- user_answers.time_spent_ms: time on the question as the browser measured it.
--
-- Both stay NULL on existing rows, meaning "not recorded".

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN repeated_question_ids UUID[];

ALTER TABLE user_answers
    ADD COLUMN time_spent_ms INTEGER;

COMMIT;
