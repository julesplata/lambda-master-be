-- Shuffle the stored order of every question's options.
--
-- The seed bank was authored with the correct option first (349 of 350
-- questions), and bulk import stores options in payload order, so
-- question_options.position alone gave away the answer. Attempts shuffle
-- options per attempt, but any read that returns them in position order leaks
-- the key. This randomises the order once; the seed files were shuffled too, so
-- a fresh import stays balanced.
--
-- Two passes, because UNIQUE (question_id, position) is not deferrable: first
-- move every row out of the 0..n range, then assign the new positions.

BEGIN;

UPDATE question_options SET position = position + 1000;

UPDATE question_options o
SET position = r.new_pos
FROM (
    SELECT id,
           row_number() OVER (PARTITION BY question_id ORDER BY random()) - 1 AS new_pos
    FROM question_options
) r
WHERE o.id = r.id;

COMMIT;
