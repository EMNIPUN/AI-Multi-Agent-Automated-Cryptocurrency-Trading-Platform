BEGIN;

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.alembic_version (
    version_num VARCHAR(32) NOT NULL, 
    CONSTRAINT alembic_version_pkc PRIMARY KEY (version_num)
);

-- Running upgrade  -> 20261104_0001

CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE app.agent_decisions (
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    env_scope VARCHAR(64) NOT NULL, 
    account_fp VARCHAR(64) NOT NULL, 
    symbol VARCHAR(64) NOT NULL, 
    category VARCHAR(32) NOT NULL, 
    action VARCHAR(16) NOT NULL, 
    strategy_id VARCHAR(64) NOT NULL, 
    signal_id VARCHAR(128), 
    correlation_id VARCHAR(128), 
    reason TEXT NOT NULL, 
    payload_json JSONB, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_agent_decisions_env_created ON app.agent_decisions (env_scope, created_at);

CREATE INDEX ix_agent_decisions_symbol_created ON app.agent_decisions (symbol, created_at);

CREATE INDEX ix_agent_decisions_signal_id ON app.agent_decisions (signal_id);

CREATE TABLE app.system_events (
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    env_scope VARCHAR(64) NOT NULL, 
    severity VARCHAR(16) NOT NULL, 
    event_type VARCHAR(64) NOT NULL, 
    message TEXT NOT NULL, 
    details_json JSONB, 
    PRIMARY KEY (id)
);

CREATE INDEX ix_system_events_env_created ON app.system_events (env_scope, created_at);

CREATE INDEX ix_system_events_type_created ON app.system_events (event_type, created_at);

CREATE TABLE app.strategy_configs (
    id UUID NOT NULL, 
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
    name VARCHAR(128) NOT NULL, 
    version VARCHAR(32) NOT NULL, 
    enabled BOOLEAN NOT NULL, 
    config_json JSONB, 
    PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_strategy_configs_name ON app.strategy_configs (name);

INSERT INTO app.alembic_version (version_num) VALUES ('20261104_0001') RETURNING app.alembic_version.version_num;

COMMIT;

