-- Rename difficulty values: easy → beginner, medium → intermediate, hard → advanced

ALTER TABLE questions DROP CONSTRAINT questions_difficulty_check;

UPDATE questions SET difficulty = 'beginner'     WHERE difficulty = 'easy';
UPDATE questions SET difficulty = 'intermediate' WHERE difficulty = 'medium';
UPDATE questions SET difficulty = 'advanced'     WHERE difficulty = 'hard';

ALTER TABLE questions
    ADD CONSTRAINT questions_difficulty_check
    CHECK (difficulty IN ('beginner', 'intermediate', 'advanced'));
