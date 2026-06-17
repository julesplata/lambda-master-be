-- Migration: 0001_init_schema
-- Consolidated baseline for a fresh database. Represents the final schema
-- state after the original 0001-0011 migration chain, with all historical
-- backfills, renames, and constraint swaps removed (they only mattered for an
-- already-populated DB).

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS tsm_system_rows;

-- 1. users
CREATE TABLE users (
    id                 UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    username           VARCHAR(50)  NOT NULL UNIQUE,
    email              VARCHAR(255) NOT NULL UNIQUE,
    password_hash      TEXT         NOT NULL,
    xp                 INTEGER      NOT NULL DEFAULT 0,
    current_streak     INTEGER      NOT NULL DEFAULT 0,
    longest_streak     INTEGER      NOT NULL DEFAULT 0,
    last_activity_date DATE,
    created_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at         TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 2. categories (closed, seeded vocabulary)
CREATE TABLE categories (
    id       UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name     VARCHAR(50) NOT NULL UNIQUE,
    slug     VARCHAR(50) NOT NULL UNIQUE,
    position INTEGER     NOT NULL DEFAULT 0
);

INSERT INTO categories (name, slug, position) VALUES
    ('Backend',         'backend',         1),
    ('OOP',             'oop',             2),
    ('Design Patterns', 'design-patterns', 3),
    ('Coding',          'coding',          4),
    ('Frontend',        'frontend',        5),
    ('Security',        'security',        6),
    ('Databases',       'databases',       7),
    ('DevOps',          'devops',          8);

-- 3. questions
CREATE TABLE questions (
    id          UUID         PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(255) NOT NULL UNIQUE,
    description TEXT         NOT NULL,
    difficulty  VARCHAR(12)  NOT NULL CHECK (difficulty IN ('beginner', 'intermediate', 'advanced')),
    explanation TEXT,
    category_id UUID         NOT NULL REFERENCES categories(id) ON DELETE RESTRICT,
    created_by  UUID         REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_created_by ON questions(created_by);
CREATE INDEX idx_questions_category_id ON questions(category_id);
CREATE INDEX idx_questions_created_at ON questions(created_at DESC);

-- 4. question_options
CREATE TABLE question_options (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID    NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT    NOT NULL,
    is_correct  BOOLEAN NOT NULL DEFAULT FALSE,
    position    INTEGER NOT NULL,
    UNIQUE (question_id, position)
);

CREATE INDEX idx_question_options_question_id ON question_options(question_id);

-- 5. tags
CREATE TABLE tags (
    id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE
);

-- 6. question_tags (M:N)
CREATE TABLE question_tags (
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, tag_id)
);

CREATE INDEX idx_question_tags_tag_id ON question_tags(tag_id);

-- 7. quiz_attempts
-- Guest-only mode: attempts are anonymous, so user_id is nullable with no FK.
-- The column and its index are kept so auth can be re-enabled later without
-- schema churn.
CREATE TABLE quiz_attempts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID,
    score           INTEGER     NOT NULL DEFAULT 0,
    total_questions INTEGER     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts(user_id);

-- 8. user_answers
CREATE TABLE user_answers (
    id                 UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    attempt_id         UUID        NOT NULL REFERENCES quiz_attempts(id) ON DELETE CASCADE,
    question_id        UUID        NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    selected_option_id UUID        REFERENCES question_options(id) ON DELETE SET NULL,
    is_correct         BOOLEAN     NOT NULL DEFAULT FALSE,
    answered_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (attempt_id, question_id)
);

CREATE INDEX idx_user_answers_attempt_id ON user_answers(attempt_id);
CREATE INDEX idx_user_answers_question_id ON user_answers(question_id);

-- 9. refresh_tokens (backs JWT refresh-token rotation/revocation)
CREATE TABLE refresh_tokens (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT        NOT NULL UNIQUE,   -- sha256 of the opaque token
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);

-- 10. user_question_stats
-- Per-(user, question) mastery rollup backing spaced-repetition "review my
-- mistakes" and progress stats. Maintained on attempt completion.
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

-- 11. question_reports (users flag something wrong with a specific question)
CREATE TABLE question_reports (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID        NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    -- Optional context of which quiz the report came from. No FK, mirroring the
    -- guest-attempt pattern: it stays valid even if the attempt is gone.
    attempt_id  UUID,
    reason      VARCHAR(20) NOT NULL,
    comment     TEXT,
    status      VARCHAR(10) NOT NULL DEFAULT 'open',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT question_reports_reason_check
        CHECK (reason IN ('incorrect_answer', 'typo', 'unclear', 'outdated', 'other')),
    CONSTRAINT question_reports_status_check
        CHECK (status IN ('open', 'resolved', 'dismissed'))
);

CREATE INDEX idx_question_reports_question_id ON question_reports (question_id);
CREATE INDEX idx_question_reports_status ON question_reports (status);

-- 12. app_feedback (free-form, app-wide feedback not tied to any question)
CREATE TABLE app_feedback (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    category   VARCHAR(20) NOT NULL,
    message    TEXT        NOT NULL,
    rating     SMALLINT,
    status     VARCHAR(10) NOT NULL DEFAULT 'open',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT app_feedback_category_check
        CHECK (category IN ('bug', 'idea', 'praise', 'other')),
    CONSTRAINT app_feedback_rating_check
        CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
    CONSTRAINT app_feedback_status_check
        CHECK (status IN ('open', 'reviewed'))
);

CREATE INDEX idx_app_feedback_status ON app_feedback (status);

COMMIT;
