# Database Migrations

Numbered SQL migrations for the system design quiz database (PostgreSQL).

## Convention

- Files: `NNNN_description.up.sql` and `NNNN_description.down.sql`
- `NNNN` is a zero-padded sequential integer (`0001`, `0002`, ...)
- `up` applies the change; `down` reverts it
- Each migration is wrapped in `BEGIN; ... COMMIT;`
- Never edit a migration once it has been applied to a shared environment — write a new one instead

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
| 0011 | name_products_in_stems | One-off data migration: ten existing question stems now name a common product as an example (Nginx, Amazon SQS, Elasticsearch, AWS Lambda, PostgreSQL, ...). Matches each stem on (category, title, old description), so admin-edited stems are skipped and a rerun is a no-op; the down migration restores the old stems the same way |
