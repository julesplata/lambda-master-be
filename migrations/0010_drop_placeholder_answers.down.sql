-- Revert 0010 for a rollback to the code before 0009, which looks an attempt's
-- questions up through user_answers: put back a placeholder row for every
-- unanswered question still in the bank, and restore the default its INSERT
-- relies on. Apply before reverting 0009.

BEGIN;

ALTER TABLE quiz_attempts ALTER COLUMN question_ids SET DEFAULT '{}';

INSERT INTO user_answers (attempt_id, question_id, selected_option_id, is_correct, answered_at)
SELECT attempt.id, picked.question_id, NULL, false, attempt.started_at
FROM quiz_attempts AS attempt
CROSS JOIN LATERAL unnest(attempt.question_ids) AS picked(question_id)
WHERE EXISTS (SELECT 1 FROM questions WHERE questions.id = picked.question_id)
ON CONFLICT (attempt_id, question_id) DO NOTHING;

COMMIT;
