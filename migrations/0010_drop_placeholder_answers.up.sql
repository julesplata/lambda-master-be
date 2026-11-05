-- Finish moving attempts' questions onto quiz_attempts.question_ids (0009).
--
-- Apply AFTER the code that writes question_ids is live. Until then, an attempt
-- the old code starts gets the empty default and shows no questions. This:
--
-- 1. Backfills those attempts, started between 0009 and the deploy.
-- 2. Drops the default, so an INSERT that forgets the ids fails instead of
--    creating an empty quiz.
-- 3. Deletes the placeholder rows: written at start, never answered. A row with
--    no selected option and is_correct false reads as unanswered everywhere
--    (GET, scoring, stats), so deleting it changes nothing a client can see.
--    A row with no selected option but is_correct true is kept: it is a correct
--    answer whose option an admin edit deleted later (ON DELETE SET NULL), and
--    it still counts toward the score.
--
-- If this deletes many rows, run VACUUM (ANALYZE) user_answers; afterwards. It
-- cannot run inside a transaction.

BEGIN;

UPDATE quiz_attempts AS attempt
SET question_ids = picked.question_ids
FROM (
    SELECT attempt_id, array_agg(question_id ORDER BY id) AS question_ids
    FROM user_answers
    GROUP BY attempt_id
) AS picked
WHERE picked.attempt_id = attempt.id
  AND attempt.question_ids = '{}';

ALTER TABLE quiz_attempts ALTER COLUMN question_ids DROP DEFAULT;

DELETE FROM user_answers
WHERE selected_option_id IS NULL
  AND NOT is_correct;

COMMIT;
