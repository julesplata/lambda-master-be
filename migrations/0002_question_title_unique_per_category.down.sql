-- Revert to a global unique title constraint.
ALTER TABLE questions DROP CONSTRAINT questions_title_category_unique;
ALTER TABLE questions ADD CONSTRAINT questions_title_key UNIQUE (title);
