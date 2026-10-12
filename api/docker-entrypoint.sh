#!/bin/sh
set -e
# Apply pending migrations before serving unless told not to (RUN_MIGRATIONS=0), e.g. when several
# API replicas start at once and one migration job runs separately.
if [ "${RUN_MIGRATIONS:-1}" = "1" ]; then
    python -m app.cli migrate
fi
exec "$@"
