-- Revert 0007: remove the AI category.
--
-- questions.category_id is ON DELETE RESTRICT, so this fails while any question,
-- archived ones included, still belongs to the category. That is deliberate:
-- deleting those questions would cascade to user_answers and erase attempt
-- history. Move or delete the AI questions on purpose before rolling back.

BEGIN;

DELETE FROM categories WHERE slug = 'ai';

COMMIT;
