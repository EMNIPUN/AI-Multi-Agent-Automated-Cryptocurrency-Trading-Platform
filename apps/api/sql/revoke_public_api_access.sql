-- Phase 2B — least-privilege hardening for schema `app` (MANUAL REVIEW ONLY)
--
-- Purpose: keep application tables out of Supabase Data API (PostgREST) exposure
-- and deny anon/authenticated by default.
--
-- DO NOT auto-run from the FastAPI process.
-- DO NOT apply until you have confirmed you are on the intended development project.
-- DO NOT grant service_role to clients or put it in NEXT_PUBLIC_*.
--
-- Also in Supabase Dashboard → Settings → API:
--   Ensure schema `app` is NOT listed under "Exposed schemas".
--   Keep exposed schemas limited to public (and other intentional API schemas).

BEGIN;

REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA app FROM PUBLIC;

-- Supabase API roles (no-op if roles absent on non-Supabase Postgres)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA app FROM anon';
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA app FROM anon';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM anon';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE 'REVOKE ALL ON SCHEMA app FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL TABLES IN SCHEMA app FROM authenticated';
    EXECUTE 'REVOKE ALL ON ALL SEQUENCES IN SCHEMA app FROM authenticated';
  END IF;
END $$;

ALTER DEFAULT PRIVILEGES IN SCHEMA app
  REVOKE ALL ON TABLES FROM PUBLIC;
ALTER DEFAULT PRIVILEGES IN SCHEMA app
  REVOKE ALL ON SEQUENCES FROM PUBLIC;

COMMIT;

-- Future least-privilege plan (not created here):
--   1. CREATE ROLE app_runtime NOINHERIT LOGIN;  -- or use Supabase custom secret role
--   2. GRANT USAGE ON SCHEMA app TO app_runtime;
--   3. GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO app_runtime;
--   4. Point server-side DATABASE_URL at that role (not the dashboard superuser long-term).
--   5. Enable RLS + tenant policies before any PostgREST exposure of `app`.
