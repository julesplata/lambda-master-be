-- Enable Row Level Security on every table in public, with no policies.
--
-- Supabase serves the public schema through its Data API (/rest/v1) to the
-- anon and authenticated roles. With RLS off, the project's anon key can read
-- and write every table. With RLS on and no policies, those roles see no rows
-- and can change none.
--
-- The backend connects as postgres, which owns these tables and bypasses RLS,
-- so the app is unaffected. Do not use FORCE ROW LEVEL SECURITY: it would apply
-- RLS to the owner too and lock the backend out.
--
-- The loop covers every table that exists when this runs, including any that
-- exist in production but not in these migrations. A table created later
-- needs its own ALTER TABLE ... ENABLE ROW LEVEL SECURITY in its migration.
-- Rerunning this is a no-op.

BEGIN;

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    END LOOP;
END $$;

COMMIT;
