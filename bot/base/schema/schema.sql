CREATE TABLE IF NOT EXISTS afk_users (
    user_id BIGINT PRIMARY KEY,
    reason TEXT,
    afk_time BIGINT
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