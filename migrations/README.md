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
| 0001 | init_schema | Initial tables: users, questions, options, tags, attempts, answers |
| 0002 | refresh_tokens | Refresh-token store for JWT auth (rotation + revocation) |
| 0003 | user_question_stats | Per-(user, question) mastery rollup for spaced-repetition review and progress stats |
