-- One clean place to analyse quiz use (C4).
--
-- Before applying, run the placeholder check (analysis findings 3.1):
--   SELECT count(*) FILTER (WHERE selected_option_id IS NULL AND NOT is_correct)
--   FROM user_answers;
-- Above 0 can mean migration 0010 was never applied; resolve that first. Once
-- 0010 is in, a NULL selected_option_id always means the question's options
-- were replaced by an edit after the answer, and the views keep those rows.
--
-- questions.content_updated_at: set by the admin console's question edit
-- (update_question) only. Archive, restore and bulk edits leave it alone,
-- unlike updated_at. NULL means not edited since this migration.
--
-- analytics_attempts: one row per attempt, without the internal ones (0014).
--   category / difficulty: NULL meant "all" from migration 0008 on
--     (2026-11-01 14:09 UTC), so it reads 'all' / 'mixed' from then and NULL
--     (unknown) before.
--   answered / correct: counts of stored answers.
--   low_effort: answers averaged under 6 seconds each (decision D2), measured
--     as (last answered_at - started_at) / answers. Until 2026-11-05 (commit
--     10f6130) answered_at held the start time, so where the last answer is
--     not after the start, completed_at is used instead, and an unfinished
--     attempt from then is NULL (unknown). NULL with no answers.
--
-- analytics_answers: one row per stored answer, with its attempt's columns.
--   question_number: the answer's 1-based position in question_ids.
--   first_time: false when the question was a repeat in that browser (0015),
--     NULL when the attempt predates that column.
--   after_edit: the answer describes the question as it reads now. False when
--     answered before content_updated_at, and when selected_option_id is NULL
--     (its options were replaced since, which also covers edits made before
--     content_updated_at existed).
--
-- Both views are security_invoker (Postgres 15+), so they apply the callers'
-- permissions and the tables' row level security (0011): Supabase's anon and
-- authenticated roles read nothing through them, as with the tables.

BEGIN;

ALTER TABLE questions
    ADD COLUMN content_updated_at TIMESTAMPTZ;

CREATE VIEW analytics_attempts WITH (security_invoker = true) AS
SELECT a.id AS attempt_id,
       a.visitor_id,
       a.source,
       a.started_at,
       a.completed_at,
       CASE
           WHEN a.category IS NOT NULL THEN a.category
           WHEN a.started_at >= '2026-11-01 14:09+00' THEN 'all'
       END AS category,
       CASE
           WHEN a.difficulty IS NOT NULL THEN a.difficulty
           WHEN a.started_at >= '2026-11-01 14:09+00' THEN 'mixed'
       END AS difficulty,
       totals.answered,
       totals.correct,
       EXTRACT(EPOCH FROM (
           CASE
               WHEN totals.last_answered_at > a.started_at THEN totals.last_answered_at
               ELSE a.completed_at
           END - a.started_at
       )) / NULLIF(totals.answered, 0) < 6 AS low_effort
FROM quiz_attempts a
CROSS JOIN LATERAL (
    SELECT count(*)                         AS answered,
           count(*) FILTER (WHERE u.is_correct) AS correct,
           max(u.answered_at)               AS last_answered_at
    FROM user_answers u
    WHERE u.attempt_id = a.id
) totals
WHERE NOT a.is_internal;

CREATE VIEW analytics_answers WITH (security_invoker = true) AS
SELECT u.attempt_id,
       u.question_id,
       u.is_correct,
       u.time_spent_ms,
       u.answered_at,
       array_position(qa.question_ids, u.question_id) AS question_number,
       CASE
           WHEN qa.repeated_question_ids IS NOT NULL
               THEN NOT (u.question_id = ANY (qa.repeated_question_ids))
       END AS first_time,
       aa.visitor_id,
       aa.source,
       aa.started_at,
       aa.completed_at,
       aa.category,
       aa.difficulty,
       q.difficulty AS question_difficulty,
       c.slug AS question_category,
       aa.low_effort,
       u.selected_option_id IS NOT NULL
           AND (q.content_updated_at IS NULL OR u.answered_at >= q.content_updated_at)
           AS after_edit
FROM user_answers u
JOIN analytics_attempts aa ON aa.attempt_id = u.attempt_id
JOIN quiz_attempts qa ON qa.id = u.attempt_id
JOIN questions q ON q.id = u.question_id
JOIN categories c ON c.id = q.category_id;

COMMIT;
