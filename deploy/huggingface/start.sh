#!/bin/sh
# Entry point of the all-in-one demo container: prepares data dirs, initialises PostgreSQL
# on first start, creates an internal API key and hands over to supervisord.
set -e

export PGDATA="$DATA_DIR/pg"
mkdir -p "$DATA_DIR" "$STORAGE_DIR" "$DATA_DIR/redis" /tmp/docintel

if [ ! -s "$PGDATA/PG_VERSION" ]; then
  initdb -D "$PGDATA" -U docintel --auth=trust --encoding=UTF8 >/dev/null
  cat >> "$PGDATA/postgresql.conf" <<EOF
listen_addresses = '127.0.0.1'
unix_socket_directories = '/tmp'
shared_buffers = 256MB
max_connections = 60
fsync = off
synchronous_commit = off
EOF
fi

# The API is only reachable inside the container; the web proxy holds this key.
if [ -z "$API_KEYS" ]; then
  API_KEYS="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export API_KEYS
export BACKEND_API_KEY="$API_KEYS"

exec supervisord -c /opt/docintel/supervisord.conf
