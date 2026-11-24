-- Rarest Blue on Supabase: the daily prompt sets, every guess, and the daily finishes.
--
-- The FastAPI backend is the only client. It connects straight to Postgres as the `postgres` role through
-- DATABASE_URL, so nothing here needs Supabase's REST/GraphQL APIs. Those APIs are public (the anon key ships
-- to browsers), and daily_prompts holds every answer and the golden krill, so this migration shuts them out:
--   * RLS on with no policies, so anon/authenticated see zero rows even if a grant slips back in;
--   * table, sequence and default grants revoked from anon/authenticated;
--   * an event trigger that turns RLS on for any table created in public later.
--
-- No explicit BEGIN/COMMIT: `supabase db push` wraps each file in its own transaction, and psql/the SQL Editor
-- can re-run it after a partial failure. Idempotent: safe to run before or after the backend's own `CREATE TABLE IF NOT EXISTS` (infrastructure/postgres.py init_schema),
-- and safe to re-run. The table definitions must stay identical to SCHEMA in src/rarest_blue/infrastructure/postgres.py.

CREATE TABLE IF NOT EXISTS public.daily_prompts (
    day TEXT PRIMARY KEY,
    prompts JSONB NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.guesses (
    day TEXT NOT NULL,
    prompt_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    raw TEXT NOT NULL,
    answer TEXT,
    points INTEGER NOT NULL,
    share DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (day, prompt_id, player_id)
);

CREATE TABLE IF NOT EXISTS public.finishes (
    day TEXT NOT NULL,
    player_id TEXT NOT NULL,
    nickname TEXT NOT NULL,
    college TEXT,
    score INTEGER NOT NULL,
    PRIMARY KEY (day, player_id)
);

-- Sanity limits that mirror what the API already validates, so a bad write fails loudly instead of landing.
-- NOT VALID: enforced on new rows only, so a re-run never trips over rows written before the constraint existed.
DO $$
DECLARE
    c record;
BEGIN
    FOR c IN
        SELECT * FROM (VALUES
            ('daily_prompts', 'daily_prompts_day_iso',      'CHECK (day ~ ''^\d{4}-\d{2}-\d{2}$'')'),
            ('daily_prompts', 'daily_prompts_is_array',     'CHECK (jsonb_typeof(prompts) = ''array'')'),
            ('guesses',       'guesses_day_iso',            'CHECK (day ~ ''^\d{4}-\d{2}-\d{2}$'')'),
            ('guesses',       'guesses_player_id_len',      'CHECK (char_length(player_id) BETWEEN 8 AND 64)'),
            ('guesses',       'guesses_raw_len',            'CHECK (char_length(raw) <= 80)'),
            ('guesses',       'guesses_share_range',        'CHECK (share >= 0 AND share <= 1)'),
            ('finishes',      'finishes_day_iso',           'CHECK (day ~ ''^\d{4}-\d{2}-\d{2}$'')'),
            ('finishes',      'finishes_player_id_len',     'CHECK (char_length(player_id) BETWEEN 8 AND 64)'),
            ('finishes',      'finishes_nickname_len',      'CHECK (char_length(nickname) <= 20)')
        ) AS t(tbl, name, def)
    LOOP
        IF NOT EXISTS (
            SELECT 1 FROM pg_constraint
            WHERE conname = c.name AND conrelid = format('public.%I', c.tbl)::regclass
        ) THEN
            EXECUTE format('ALTER TABLE public.%I ADD CONSTRAINT %I %s NOT VALID', c.tbl, c.name, c.def);
        END IF;
    END LOOP;
END
$$;

-- /api/leaderboard sorts the day's finishes by score; /api/finish counts the ones below a score.
CREATE INDEX IF NOT EXISTS finishes_day_score_idx ON public.finishes (day, score DESC);

ALTER TABLE public.daily_prompts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.guesses       ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.finishes      ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON public.daily_prompts, public.guesses, public.finishes FROM PUBLIC;

-- Every new function is executable by PUBLIC (and so by anon) unless this default is removed. A function in public
-- is callable over REST at /rest/v1/rpc/<name>, and a SECURITY DEFINER one would bypass RLS.
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
DO $$
DECLARE
    f regprocedure;
BEGIN
    FOR f IN
        SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
        WHERE n.nspname = 'public' AND pg_get_userbyid(p.proowner) = current_user
    LOOP
        EXECUTE format('REVOKE EXECUTE ON FUNCTION %s FROM PUBLIC', f);
    END LOOP;
END
$$;

-- anon/authenticated only exist on Supabase; skip quietly on plain Postgres (local dev, CI).
DO $$
DECLARE
    r text;
BEGIN
    FOREACH r IN ARRAY ARRAY['anon', 'authenticated'] LOOP
        IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = r) THEN
            EXECUTE format('REVOKE ALL ON public.daily_prompts, public.guesses, public.finishes FROM %I', r);
            EXECUTE format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM %I', r);
            EXECUTE format('REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM %I', r);
            -- Tables, sequences and functions created later by this role don't get auto-granted to the public APIs.
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON SEQUENCES FROM %I', r);
            EXECUTE format('ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE EXECUTE ON FUNCTIONS FROM %I', r);
        END IF;
    END LOOP;
END
$$;

-- Turn RLS on for any table later created in public (e.g. a new table added to the backend's SCHEMA).
-- Creating an event trigger needs privileges some hosts withhold; if refused, the tables above stay locked down.
-- Not SECURITY DEFINER: it runs as whoever created the table (its owner), so the ALTER always has rights, and
-- a failure only warns, so the trigger can never block another role's CREATE TABLE.
CREATE OR REPLACE FUNCTION public.rarest_blue_enable_rls()
RETURNS event_trigger
LANGUAGE plpgsql
SET search_path = pg_catalog
AS $$
DECLARE
    obj record;
BEGIN
    FOR obj IN
        SELECT * FROM pg_event_trigger_ddl_commands()
        WHERE command_tag IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
          AND object_type = 'table'
          AND schema_name = 'public'
    LOOP
        BEGIN
            EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY', obj.object_identity);
        EXCEPTION WHEN OTHERS THEN
            RAISE WARNING 'Could not enable RLS on % (%): enable it by hand', obj.object_identity, SQLERRM;
        END;
    END LOOP;
END
$$;

REVOKE ALL ON FUNCTION public.rarest_blue_enable_rls() FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON FUNCTION public.rarest_blue_enable_rls() FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON FUNCTION public.rarest_blue_enable_rls() FROM authenticated;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_event_trigger WHERE evtname = 'rarest_blue_enable_rls') THEN
        CREATE EVENT TRIGGER rarest_blue_enable_rls ON ddl_command_end
            WHEN TAG IN ('CREATE TABLE', 'CREATE TABLE AS', 'SELECT INTO')
            EXECUTE FUNCTION public.rarest_blue_enable_rls();
    END IF;
EXCEPTION WHEN OTHERS THEN
    RAISE WARNING 'Could not create the RLS event trigger (%). Tables above are still locked down; '
                  'enable RLS by hand on any table you add later.', SQLERRM;
END
$$;
