-- Migration: 0001_init_schema
-- Creates initial schema: users, questions, question_options, tags,
-- question_tags, quiz_attempts, user_answers.

BEGIN;

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- 1. users
CREATE TABLE users (
    id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    username      VARCHAR(50) NOT NULL UNIQUE,
    email         VARCHAR(255) NOT NULL UNIQUE,
    password_hash TEXT        NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- 2. questions
CREATE TABLE questions (
    id          UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    title       VARCHAR(255) NOT NULL,
    description TEXT        NOT NULL,
    difficulty  VARCHAR(10) NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    explanation TEXT,
    created_by  UUID        REFERENCES users(id) ON DELETE SET NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_questions_difficulty ON questions(difficulty);
CREATE INDEX idx_questions_created_by ON questions(created_by);

-- 3. question_options
CREATE TABLE question_options (
    id          UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    question_id UUID    NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    option_text TEXT    NOT NULL,
    is_correct  BOOLEAN NOT NULL DEFAULT FALSE,
    position    INTEGER NOT NULL,
    UNIQUE (question_id, position)
);

CREATE INDEX idx_question_options_question_id ON question_options(question_id);

-- 4. tags
CREATE TABLE tags (
    id   UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(50) NOT NULL UNIQUE
);

-- 5. question_tags (M:N)
CREATE TABLE question_tags (
    question_id UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    tag_id      UUID NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (question_id, tag_id)
);

CREATE INDEX idx_question_tags_tag_id ON question_tags(tag_id);

-- 6. quiz_attempts
CREATE TABLE quiz_attempts (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID        NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    score           INTEGER     NOT NULL DEFAULT 0,
    total_questions INTEGER     NOT NULL,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

CREATE INDEX idx_quiz_attempts_user_id ON quiz_attempts(user_id);

-- 7. user_answers
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

COMMIT;
