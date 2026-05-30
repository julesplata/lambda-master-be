-- Reverses 0004_gamification.

BEGIN;

ALTER TABLE users
    DROP COLUMN xp,
    DROP COLUMN current_streak,
    DROP COLUMN longest_streak,
    DROP COLUMN last_activity_date;

COMMIT;
