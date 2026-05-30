-- Migration: 0003_user_question_stats
-- Per-(user, question) mastery rollup backing spaced-repetition "review my
-- mistakes" and progress stats. Maintained on attempt completion.

BEGIN;

CREATE TABLE user_question_stats (
    user_id          UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    question_id      UUID        NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    times_seen       INTEGER     NOT NULL DEFAULT 0,
    times_correct    INTEGER     NOT NULL DEFAULT 0,
    last_answered_at TIMESTAMPTZ,
    last_correct     BOOLEAN,
    box              SMALLINT    NOT NULL DEFAULT 1,   -- Leitner box 1..5
    due_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (user_id, question_id)
);

-- Drives the review query: "my cards due now, soonest first".
CREATE INDEX idx_user_question_stats_due ON user_question_stats(user_id, due_at);

COMMIT;
