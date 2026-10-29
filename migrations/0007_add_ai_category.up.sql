-- Add the AI category (slug 'ai').
--
-- Categories are a closed vocabulary: POST /questions/bulk rejects an unknown
-- slug, so seeds/ai_questions.json cannot load until this row exists. The
-- 'database' and 'system-design' categories the other seed files use were
-- inserted by hand and have no migration; this one is reproducible.
--
-- Those hand-inserted rows mean the current highest position cannot be known
-- from the migrations alone, so the new category goes after whatever is there.
-- ON CONFLICT DO NOTHING (no target, so it covers both the name and the slug
-- unique constraints) makes a rerun, or a database where someone already added
-- the row by hand, a no-op.

BEGIN;

INSERT INTO categories (name, slug, position)
SELECT 'AI', 'ai', COALESCE(MAX(position), 0) + 1
FROM categories
ON CONFLICT DO NOTHING;

COMMIT;
