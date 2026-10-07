CREATE TABLE IF NOT EXISTS afk_users (
    user_id BIGINT PRIMARY KEY,
    reason TEXT,
    afk_time BIGINT
);
