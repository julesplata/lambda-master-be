-- Record the filters a quiz was started with.
--
-- POST /quiz-attempts takes an optional category slug and difficulty, uses them
-- to pick the questions, and until now threw them away. Guessing them back from
-- the questions an attempt drew is unreliable (a short "all" quiz can land on a
-- single category by chance), so the choice is stored on the attempt itself.
--
-- NULL means the filter was left on "all". Existing rows stay NULL, which is
-- indistinguishable from "all"; only attempts started after this migration are
-- meaningful. category holds the slug rather than a categories FK so a NULL
-- keeps meaning "all", never "the category was removed".

BEGIN;

ALTER TABLE quiz_attempts
    ADD COLUMN category   VARCHAR(50),
    ADD COLUMN difficulty VARCHAR(12)
        CONSTRAINT quiz_attempts_difficulty_check
        CHECK (difficulty IN ('beginner', 'intermediate', 'advanced'));

COMMIT;
