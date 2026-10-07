#!/usr/bin/env bash
set -euo pipefail

project_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ ! -f "$project_root/.env" ]]; then
    echo "Missing $project_root/.env; copy .env.example and configure the database values." >&2
    exit 1
fi

set -a
# shellcheck source=/dev/null
source "$project_root/.env"
set +a

: "${HOST:?Set HOST in .env, for example localhost:3333}"
: "${USER:?Set USER in .env}"
: "${PASSWORD:?Set PASSWORD in .env}"
: "${DB:?Set DB in .env}"

db_host="${HOST%:*}"
if [[ "$db_host" == "$HOST" ]]; then
    db_port=5432
else
    db_port="${HOST##*:}"
fi

if [[ "$db_host" != "localhost" && "$db_host" != "127.0.0.1" ]]; then
    echo "This helper only manages a local PostgreSQL server; HOST must be localhost or 127.0.0.1." >&2
    exit 1
fi
if [[ ! "$db_port" =~ ^[0-9]+$ ]] || (( 10#$db_port < 1 || 10#$db_port > 65535 )); then
    echo "HOST must contain a valid PostgreSQL port." >&2
    exit 1
fi

pg_data="${XDG_DATA_HOME:-$HOME/.local/share}/axis/postgres"
action="${1:-start}"

case "$action" in
    start)
        mkdir -p "$(dirname "$pg_data")"
        if [[ ! -s "$pg_data/PG_VERSION" ]]; then
            password_file="$(mktemp)"
            trap 'rm -f "$password_file"' EXIT
            chmod 600 "$password_file"
            printf '%s\n' "$PASSWORD" > "$password_file"
            initdb \
                --username="$USER" \
                --pwfile="$password_file" \
                --auth-local=trust \
                --auth-host=scram-sha-256 \
                --encoding=UTF8 \
                --locale=C \
                --pgdata="$pg_data"
            rm -f "$password_file"
            trap - EXIT
        fi

        if ! pg_ctl --pgdata="$pg_data" status >/dev/null 2>&1; then
            pg_ctl \
                --pgdata="$pg_data" \
                --log="$pg_data/server.log" \
                --options="-h 127.0.0.1 -p $db_port" \
                start
        fi

        PGPASSWORD="$PASSWORD" psql \
            --host=127.0.0.1 \
            --port="$db_port" \
            --username="$USER" \
            --dbname=postgres \
            --set=db_name="$DB" \
            --set=db_user="$USER" <<'SQL'
SELECT format('CREATE DATABASE %I OWNER %I', :'db_name', :'db_user')
WHERE NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = :'db_name')
\gexec
SQL

        echo "PostgreSQL is ready at $db_host:$db_port (database: $DB)."
        ;;
    stop)
        pg_ctl --pgdata="$pg_data" --mode=fast stop
        ;;
    status)
        pg_ctl --pgdata="$pg_data" status
        ;;
    *)
        echo "Usage: $0 [start|stop|status]" >&2
        exit 2
        ;;
esac
