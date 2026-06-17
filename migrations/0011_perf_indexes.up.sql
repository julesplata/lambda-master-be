-- Migration: 0011_perf_indexes
-- Adds indexes for the question-listing and quiz-sampling hot paths.
--
-- 1. questions.category_id was added in 0005 with no index, so every
--    category-filtered list/quiz query sequentially scans the table.
-- 2. The default question listing orders by created_at DESC; a dedicated
--    index lets Postgres satisfy the ORDER BY ... LIMIT/OFFSET without a sort.
-- 3. tsm_system_rows powers TABLESAMPLE SYSTEM_ROWS(n), used to pick a random
--    quiz sample without an ORDER BY random() full-table sort.

BEGIN;

CREATE EXTENSION IF NOT EXISTS tsm_system_rows;

CREATE INDEX IF NOT EXISTS idx_questions_category_id ON questions (category_id);
CREATE INDEX IF NOT EXISTS idx_questions_created_at ON questions (created_at DESC);

COMMIT;
