-- Guest-only mode: quiz attempts are anonymous, so they no longer belong to a
-- user. Drop the FK to users and the NOT NULL constraint on user_id. The column
-- and its index are kept so auth can be re-enabled later without a schema churn.
ALTER TABLE quiz_attempts DROP CONSTRAINT quiz_attempts_user_id_fkey;
ALTER TABLE quiz_attempts ALTER COLUMN user_id DROP NOT NULL;
