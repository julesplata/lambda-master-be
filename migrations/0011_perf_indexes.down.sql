BEGIN;

DROP INDEX IF EXISTS idx_questions_created_at;
DROP INDEX IF EXISTS idx_questions_category_id;

COMMIT;
