CREATE TABLE IF NOT EXISTS afk_users (
    user_id BIGINT PRIMARY KEY,
    reason TEXT,
    afk_time BIGINT
);

CREATE TABLE IF NOT EXISTS tiktok_reposter (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS nickknock_settings (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    interval_seconds BIGINT NOT NULL DEFAULT 600
);

CREATE TABLE IF NOT EXISTS water_settings (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    channel_id BIGINT,
    interval_seconds BIGINT NOT NULL DEFAULT 3600,
    ping_member_ids BIGINT[] NOT NULL DEFAULT '{}',
    next_reminder_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS modlog_settings (
    guild_id BIGINT PRIMARY KEY,
    config JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS verification_settings (
    guild_id BIGINT PRIMARY KEY,
    channel_id BIGINT NOT NULL,
    unverified_role_id BIGINT NOT NULL,
    verified_role_id BIGINT,
    message_id BIGINT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS gate_settings (
    guild_id BIGINT PRIMARY KEY,
    enabled BOOLEAN NOT NULL DEFAULT FALSE,
    channel_id BIGINT,
    welcome_message TEXT,
    goodbye_message TEXT,
    dm_message TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS extended_timeouts (
    guild_id BIGINT NOT NULL,
    member_id BIGINT NOT NULL,
    end_at TIMESTAMPTZ NOT NULL,
    next_refresh_at TIMESTAMPTZ NOT NULL,
    reason TEXT,
    PRIMARY KEY (guild_id, member_id)
);

CREATE TABLE IF NOT EXISTS commands (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS users (
    id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS guilds (
    id BIGINT PRIMARY KEY
);

CREATE TABLE IF NOT EXISTS command_usage (
    id BIGSERIAL PRIMARY KEY,
    command_id BIGINT NOT NULL REFERENCES commands(id),
    user_id BIGINT NOT NULL REFERENCES users(id),
    guild_id BIGINT REFERENCES guilds(id),
    used_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS command_usage_user_command_idx
    ON command_usage (user_id, command_id);

CREATE INDEX IF NOT EXISTS command_usage_guild_command_idx
    ON command_usage (guild_id, command_id);

CREATE INDEX IF NOT EXISTS command_usage_command_idx
    ON command_usage (command_id);

CREATE TABLE IF NOT EXISTS message_counts (
    guild_id BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    message_count BIGINT NOT NULL DEFAULT 0,
    PRIMARY KEY (guild_id, user_id)
);

CREATE TABLE IF NOT EXISTS customs_guilds (
    guild_id BIGINT PRIMARY KEY,
    whitelisted BOOLEAN NOT NULL DEFAULT FALSE,
    customizations JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
