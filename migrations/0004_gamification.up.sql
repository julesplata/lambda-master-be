-- Migration: 0004_gamification
-- Adds XP and daily-streak counters to users. Level is derived from xp in
-- application code, so it is intentionally not stored. Columns are additive with
-- defaults, so existing rows backfill to 0 / NULL automatically.

BEGIN;

ALTER TABLE users
    ADD COLUMN xp                 INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN current_streak     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN longest_streak     INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN last_activity_date DATE;

COMMIT;
