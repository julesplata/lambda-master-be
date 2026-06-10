-- Revert difficulty values: beginner → easy, intermediate → medium, advanced → hard

ALTER TABLE questions DROP CONSTRAINT questions_difficulty_check;

UPDATE questions SET difficulty = 'easy'   WHERE difficulty = 'beginner';
UPDATE questions SET difficulty = 'medium' WHERE difficulty = 'intermediate';
UPDATE questions SET difficulty = 'hard'   WHERE difficulty = 'advanced';

ALTER TABLE questions
    ADD CONSTRAINT questions_difficulty_check
    CHECK (difficulty IN ('easy', 'medium', 'hard'));
