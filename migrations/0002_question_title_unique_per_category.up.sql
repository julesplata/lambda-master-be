-- Allow the same question title to exist in different categories, while still
-- preventing duplicate titles within a single category.
ALTER TABLE questions DROP CONSTRAINT questions_title_key;
ALTER TABLE questions
    ADD CONSTRAINT questions_title_category_unique UNIQUE (title, category_id);
