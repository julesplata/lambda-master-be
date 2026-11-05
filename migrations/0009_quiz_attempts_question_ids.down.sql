-- Revert 0009. Revert 0010 first: it puts back the placeholder rows the old
-- code reads an attempt's questions from.

BEGIN;

ALTER TABLE quiz_attempts DROP COLUMN question_ids;

COMMIT;
