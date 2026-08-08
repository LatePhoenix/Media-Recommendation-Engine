#!/bin/sh
set -e
alembic upgrade head
if [ "${SEED_FAIL_SOFT:-false}" = "true" ]; then
  python -m app.seed || true
else
  python -m app.seed
fi
exec "$@"
