-- Offline review SQL for Alembic revision 20261104_0002
-- Generated for operator review — DO NOT auto-apply remotely.
-- Placeholder / localhost context only; contains no production secrets.
--
-- Prerequisite: 20261104_0001 applied (app schema + base tables).
-- PRIVATE_DATA_READS_ENABLED must stay false until this is reviewed + tested.

BEGIN;

-- Running upgrade 20261104_0001 -> 20261104_0002

ALTER TABLE app.agent_decisions ADD COLUMN owner_user_id UUID;
ALTER TABLE app.system_events ADD COLUMN owner_user_id UUID;
ALTER TABLE app.strategy_configs ADD COLUMN owner_user_id UUID;

CREATE INDEX ix_agent_decisions_owner_created ON app.agent_decisions (owner_user_id, created_at);
CREATE INDEX ix_system_events_owner_created ON app.system_events (owner_user_id, created_at);
CREATE INDEX ix_strategy_configs_owner_created ON app.strategy_configs (owner_user_id, created_at);

DROP INDEX IF EXISTS app.ix_strategy_configs_name;

CREATE UNIQUE INDEX ix_strategy_configs_owner_name
ON app.strategy_configs (owner_user_id, name)
WHERE owner_user_id IS NOT NULL;

ALTER TABLE app.agent_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.system_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE app.strategy_configs ENABLE ROW LEVEL SECURITY;

-- Policies only when Supabase role `authenticated` exists.
-- NULL owner_user_id excluded (unowned / legacy inaccessible).
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
    EXECUTE $p$
      CREATE POLICY agent_decisions_select_own
      ON app.agent_decisions
      FOR SELECT
      TO authenticated
      USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
    $p$;
    EXECUTE $p$
      CREATE POLICY system_events_select_own
      ON app.system_events
      FOR SELECT
      TO authenticated
      USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
    $p$;
    EXECUTE $p$
      CREATE POLICY strategy_configs_select_own
      ON app.strategy_configs
      FOR SELECT
      TO authenticated
      USING (owner_user_id IS NOT NULL AND owner_user_id = auth.uid())
    $p$;
  END IF;
END $$;

UPDATE app.alembic_version SET version_num='20261104_0002';

COMMIT;

-- Notes for operators:
-- 1. postgres / table owner bypass RLS unless FORCE ROW LEVEL SECURITY (not set here).
-- 2. FastAPI MUST filter by verified JWT sub regardless of RLS.
-- 3. No GRANT USAGE ON SCHEMA app TO anon/authenticated in this revision.
-- 4. Existing rows keep owner_user_id NULL → API-inaccessible.
-- 5. Downgrade is manual only — do not auto-run.
