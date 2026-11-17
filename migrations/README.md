# Database Migrations

Numbered SQL migrations for the system design quiz database (PostgreSQL).

## Convention

- Files: `NNNN_description.up.sql` and `NNNN_description.down.sql`
- `NNNN` is a zero-padded sequential integer (`0001`, `0002`, ...)
- `up` applies the change; `down` reverts it
- Each migration is wrapped in `BEGIN; ... COMMIT;`
- Never edit a migration once it has been applied to a shared environment — write a new one instead
- Every new table needs `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` in the migration that creates it, with no policies (see 0011). Without it, Supabase's Data API serves the table to anyone holding the anon key

## Applying

```bash
psql "$DATABASE_URL" -f 0001_init_schema.up.sql
```

## Rolling back

```bash
psql "$DATABASE_URL" -f 0001_init_schema.down.sql
```

## Migrations

| #    | Name        | Description                                     |
| ---- | ----------- | ----------------------------------------------- |
| 0001 | init_schema | Consolidated baseline: users (with gamification), categories (seeded), questions, options, tags, attempts (guest-mode), answers, refresh_tokens, user_question_stats, question_reports, app_feedback |
| 0002 | question_title_unique_per_category | Replaces the global unique question title with a `(title, category_id)` unique constraint |
| 0003 | quiz_attempts_retention_index | Partial index on `quiz_attempts(started_at) WHERE completed_at IS NULL`, backing the abandoned-attempt purge job |
| 0004 | questions_archived_at | Adds `questions.archived_at` (soft delete) and a partial index on live rows |
| 0005 | shuffle_option_positions | One-off data migration: randomises `question_options.position`, which had the correct answer first for almost every seeded question. The down migration is a no-op |
| 0006 | balance_option_lengths | One-off data migration: applies the seed rewrite that stopped the correct option being the longest (329 of 350 questions). Matches each option on (category, title, old text), so admin-edited options are skipped and a rerun is a no-op; the down migration restores the old text the same way |
| 0007 | add_ai_category | Inserts the `AI` category (slug `ai`) after the existing categories, which `seeds/ai_questions.json` needs before bulk import. A rerun is a no-op; the down migration fails while any question (archived included) is still in the category, rather than cascading into attempt history |
| 0008 | quiz_attempts_settings | Adds nullable `quiz_attempts.category` (slug) and `quiz_attempts.difficulty`, the filters a quiz was started with. NULL means "all"; rows from before the migration are NULL too |
| 0009 | quiz_attempts_question_ids | Adds `quiz_attempts.question_ids`, the picked questions in serve order, and backfills it from the placeholder answer rows. Expand step: apply **before** deploying the code that reads it; the column's default keeps the old code's INSERT working |
| 0010 | drop_placeholder_answers | Backfills attempts started between 0009 and the deploy, drops the column default, and deletes the never-answered placeholder `user_answers` rows. Contract step: apply **right after** the deploy. The down migration recreates the placeholders the old code needs |
| 0011 | enable_rls | Enables Row Level Security, with no policies, on every table in `public`, so Supabase's Data API (`anon`/`authenticated`) can read and write nothing. The backend connects as `postgres`, the owner, and is unaffected. A rerun is a no-op; the down migration disables it again |
| 0012 | name_products_in_stems | One-off data migration: ten existing question stems now name a common product as an example (Nginx, Amazon SQS, Elasticsearch, AWS Lambda, PostgreSQL, ...). Matches each stem on (category, title, old description), so admin-edited stems are skipped and a rerun is a no-op; the down migration restores the old stems the same way |
| 0013 | quiz_attempts_visitor_id | Adds nullable `quiz_attempts.visitor_id`, the browser's random id sent as `X-Visitor-Id` after the visitor accepts analytics, and a partial index on `(visitor_id, started_at)` for non-NULL rows. Apply **before** deploying the code that writes it |
| 0014 | quiz_attempts_is_internal | Adds `quiz_attempts.is_internal` (default false), true for quizzes started in a browser signed in to the admin console (`X-Internal: 1`). Apply **before** deploying the code that writes it |
| 0015 | answer_time_and_repeats | Adds `quiz_attempts.repeated_question_ids` (the picked questions the browser had answered before; empty when none) and `user_answers.time_spent_ms`. NULL on earlier rows, meaning "not recorded". Apply **before** deploying the code that writes them |
| 0016 | quiz_attempts_source | Adds `quiz_attempts.source`, where the quiz was started (`home_hero`, `topic_guide`, ..., `other`). Apply **before** deploying the code that writes it |
| 0017 | analytics_views | Adds `questions.content_updated_at` (set only by the console's question edit) and the `analytics_attempts` / `analytics_answers` views below. Run the placeholder check first (see the migration's header). Needs Postgres 15+ (`security_invoker`). Apply **before** deploying the code that writes the column and reads the views |

## Analytics views

`analytics_attempts` (one row per attempt) and `analytics_answers` (one row per
stored answer) apply the filters every analysis needs, so queries don't repeat
them by hand. Both leave out attempts with `is_internal`, and both are
`security_invoker`, so Supabase's anon and authenticated roles read nothing
through them, as with the tables (0011). The column rules are in the header of
`0017_analytics_views.up.sql`. In short:

| Column | Meaning |
| ------ | ------- |
| `category`, `difficulty` | The quiz's filters. `'all'` / `'mixed'` when NULL from 2026-11-01 14:09 UTC (0008) on, NULL (unknown) before |
| `low_effort` | Answers averaged under 6 seconds each: (last `answered_at` - `started_at`) / answers. Before 2026-11-05 `answered_at` held the start time, so those attempts use `completed_at`, and unfinished ones are NULL |
| `first_time` | `analytics_answers` only. False when the question was a repeat in that browser; NULL before 0015 |
| `after_edit` | `analytics_answers` only. False when the answer predates the question's last console edit, or its options have been replaced since (`selected_option_id` NULL) |
| `answered`, `correct` | `analytics_attempts` only. Counts of stored answers |

Hardest questions, counting first-time, considered answers to the question as
it reads now:

```sql
SELECT question_id, question_difficulty,
       count(*)                                      AS first_answers,
       round(avg(CASE WHEN is_correct THEN 1 ELSE 0 END), 2) AS correct_rate,
       percentile_cont(0.5) WITHIN GROUP (ORDER BY time_spent_ms) AS median_ms
FROM analytics_answers
WHERE first_time AND NOT low_effort AND after_edit
GROUP BY question_id, question_difficulty
ORDER BY correct_rate;
```
