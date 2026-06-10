-- Enforce globally unique question titles so re-POSTing the same bulk
-- payload fails instead of silently creating duplicate questions.

ALTER TABLE questions
    ADD CONSTRAINT questions_title_unique UNIQUE (title);
