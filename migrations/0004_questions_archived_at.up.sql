-- Soft-delete for questions.
--
-- The admin console removes questions from the bank, but user_answers.question_id
-- is ON DELETE CASCADE: a hard delete would silently erase the answer rows of
-- every past attempt that included the question, leaving quiz_attempts.score
-- pointing at answers that no longer exist. Archiving instead keeps attempt
-- history intact and makes the console's "Undo" a real restore.

ALTER TABLE questions ADD COLUMN archived_at TIMESTAMPTZ;

-- Every public read path (browse, question detail, new-attempt sampling) filters
-- on archived_at IS NULL. A partial index keeps only the live rows, which is the
-- set those queries care about; the admin console scans the whole table anyway.
CREATE INDEX questions_active_idx ON questions (archived_at)
    WHERE archived_at IS NULL;
