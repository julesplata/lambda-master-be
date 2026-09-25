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
