-- Turn Row Level Security back off on every table in public. This reopens
-- every table to the Supabase Data API's anon key (see the up migration).

BEGIN;

DO $$
DECLARE
    t text;
BEGIN
    FOR t IN SELECT tablename FROM pg_tables WHERE schemaname = 'public' LOOP
        EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', t);
    END LOOP;
END $$;

COMMIT;
