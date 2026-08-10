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
