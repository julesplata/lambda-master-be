-- Mark quizzes taken in the site owner's own browsers (C1).
--
-- Signing in to the admin console marks that browser as internal, and the
-- frontend then sends X-Internal: 1 on every request. POST /quiz-attempts
-- stores it here, so analysis can leave the owner's testing out. Anyone can
-- send the header; all it does is leave their own quizzes out of the figures.
--
-- Every earlier row is false. Rows known to be the owner's can be marked by
-- visitor id, once: UPDATE quiz_attempts SET is_internal = true
-- WHERE visitor_id = '<id>';
--
-- ADD COLUMN with a constant default does not rewrite the table (Postgres 11+).

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN is_internal BOOLEAN NOT NULL DEFAULT false;

COMMIT;
