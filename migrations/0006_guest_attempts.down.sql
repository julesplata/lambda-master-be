-- Restore the user/attempt link. NOTE: this only succeeds if every quiz_attempts
-- row has a non-NULL user_id that references an existing users row. Any guest
-- attempts created while this migration was applied must be deleted/backfilled
-- first, e.g.: DELETE FROM quiz_attempts WHERE user_id IS NULL;
ALTER TABLE quiz_attempts ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE quiz_attempts
    ADD CONSTRAINT quiz_attempts_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE;
