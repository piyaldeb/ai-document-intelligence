#!/bin/sh
# Entry point of the single-container deployment (web + API in one service, external Postgres).
set -e

# Some hosts (e.g. Render) mount a fresh, empty /tmp at runtime: create scratch dirs here,
# not only in the image.
mkdir -p /tmp/docintel "${STORAGE_DIR:-/tmp/docintel/uploads}"

# The API listens on 127.0.0.1 only; the web proxy and the API share this internal key.
if [ -z "$API_KEYS" ]; then
  API_KEYS="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export API_KEYS
export BACKEND_API_KEY="${API_KEYS%%,*}"
if [ -z "$CRON_SECRET" ]; then
  CRON_SECRET="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
fi
export CRON_SECRET

cd /app
alembic upgrade head
exec supervisord -c /etc/docintel/supervisord.conf
