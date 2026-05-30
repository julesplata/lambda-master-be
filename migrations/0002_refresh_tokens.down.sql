-- Migration: 0002_refresh_tokens (down)
-- Drops the refresh_tokens table.

BEGIN;

DROP TABLE IF EXISTS refresh_tokens;

COMMIT;
