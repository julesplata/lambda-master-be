DROP INDEX IF EXISTS questions_active_idx;

ALTER TABLE questions DROP COLUMN archived_at;
