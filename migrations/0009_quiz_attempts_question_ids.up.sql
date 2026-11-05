-- Keep an attempt's questions on the attempt itself.
--
-- POST /quiz-attempts used to write a placeholder user_answers row for every
-- question it picked, so one open request stored up to 101 rows, kept forever
-- once the attempt was completed. From now on the picked ids live in
-- quiz_attempts.question_ids, in the order they are served, and a user_answers
-- row is written only when an answer arrives.
--
-- This is the expand half, safe while the old code is still serving: the
-- default keeps the old INSERT working and nothing is removed. Apply it BEFORE
-- deploying the code that reads the column, and 0010 right AFTER the deploy.
--
-- The backfill orders each attempt's ids by user_answers.id, the order GET has
-- served them in until now, so a quiz in progress keeps its numbering.
-- ADD COLUMN with a constant default does not rewrite the table.

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN question_ids UUID[] NOT NULL DEFAULT '{}';

UPDATE quiz_attempts AS attempt
SET question_ids = picked.question_ids
FROM (
    SELECT attempt_id, array_agg(question_id ORDER BY id) AS question_ids
    FROM user_answers
    GROUP BY attempt_id
) AS picked
WHERE picked.attempt_id = attempt.id;

COMMIT;
