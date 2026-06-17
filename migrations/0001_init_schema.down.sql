-- Rollback for 0001_init_schema

BEGIN;

DROP TABLE IF EXISTS app_feedback;
DROP TABLE IF EXISTS question_reports;
DROP TABLE IF EXISTS user_question_stats;
DROP TABLE IF EXISTS refresh_tokens;
DROP TABLE IF EXISTS user_answers;
DROP TABLE IF EXISTS quiz_attempts;
DROP TABLE IF EXISTS question_tags;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS question_options;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

COMMIT;
