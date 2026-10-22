#!/usr/bin/env bash
###################################################################################################
# Deploy to dev.tripproofonline.com - tests first, and nothing goes live unless they pass.
#
#   deploy/deploy.sh            test, then deploy the API, migrations and web
#   deploy/deploy.sh --test     run the tests only
#
# 1. The working copy's API, tests and migrations go to a staging folder on the server
#    (~/tripproof-ci), never the live tree, and the whole suite runs there against tripproof_test -
#    a database the tests wipe and rebuild from the migrations, so a migration that cannot run on
#    an empty database fails here and not on the next new server.
# 2. Only if every test passes: the web is built here, and the API, migrations and built web are
#    copied into the live tree - the paths the service and nginx actually read (see the dev server
#    note: /applications/dev.tripproofonline.com/{api/app,db/migrations,web}).
# 3. The service is restarted, which applies new migrations, and the deploy is proved: the service
#    is active, /api/health answers, the live tree matches the working copy, and the site serves
#    the bundle just built.
###################################################################################################
set -euo pipefail

HOST=spsimmons@arrowleaftech.io
PORT=5859
LIVE=/applications/dev.tripproofonline.com
CI='~/tripproof-ci'
SITE=https://dev.tripproofonline.com
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SSH=(ssh -p "$PORT" "$HOST")
RSYNC=(rsync -a --delete -e "ssh -p $PORT")

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[1;31mSTOPPED: %s\033[0m\n' "$*"; exit 1; }

say "Staging the working copy for the tests"
"${SSH[@]}" "mkdir -p $CI/api $CI/db"
"${RSYNC[@]}" --exclude __pycache__ "$ROOT/api/app/" "$HOST:$CI/api/app/"
"${RSYNC[@]}" --exclude __pycache__ "$ROOT/api/tests/" "$HOST:$CI/api/tests/"
"${RSYNC[@]}" "$ROOT/db/migrations/" "$HOST:$CI/db/migrations/"

say "Running the tests against tripproof_test"
"${SSH[@]}" "cd $CI/api && set -a && . $LIVE/.env && set +a \
  && if [ -n \"\$TEST_DB_USER\" ]; then export TEST_DB_STRICT=1; \
     else echo 'WARNING: no TEST_DB_USER in .env - the tests are running as the live database user'; \
          export TEST_DB_USER=\$DB_USER TEST_DB_PASSWORD=\$DB_PASSWORD; fi \
  && export TEST_DB_NAME=tripproof_test \
            TEST_DB_HOST=127.0.0.1 MIGRATIONS_PATH=\$HOME/tripproof-ci/db/migrations \
  && PYTHONPATH=. timeout 1800 $LIVE/venv/bin/python -m pytest tests -q -p no:cacheprovider --tb=short \
     2>&1 | grep -vE '^(applying|recorded) ' | tail -40; exit \${PIPESTATUS[0]}" \
  || die "the tests failed - nothing was deployed"

[[ "${1:-}" == "--test" ]] && { say "Tests passed (test only - nothing deployed)"; exit 0; }

say "Building the web"
(cd "$ROOT/web" && npm run build >/tmp/tripproof-build.log 2>&1) \
  || { tail -20 /tmp/tripproof-build.log; die "the web build failed - nothing was deployed"; }

say "Copying the API, migrations and web into the live tree"
"${RSYNC[@]}" --exclude __pycache__ "$ROOT/api/app/" "$HOST:$LIVE/api/app/"
rsync -a -e "ssh -p $PORT" "$ROOT/db/migrations/" "$HOST:$LIVE/db/migrations/"
"${RSYNC[@]}" "$ROOT/web/dist/" "$HOST:$LIVE/web/"

say "Restarting the API (applies new migrations)"
"${SSH[@]}" "sudo systemctl restart dev-tripproof-api"
for _ in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  "${SSH[@]}" "systemctl is-active --quiet dev-tripproof-api" && break
done
"${SSH[@]}" "systemctl is-active --quiet dev-tripproof-api" \
  || { "${SSH[@]}" "journalctl -u dev-tripproof-api --since '-2 min' --no-pager | tail -30"; \
       die "the API did not come back up"; }
"${SSH[@]}" "journalctl -u dev-tripproof-api --since '-2 min' --no-pager | grep -E 'applying|recorded' || true"

say "Proving the deploy landed"
[[ "$(curl -fsS "$SITE/api/health")" == *'"ok":true'* ]] || die "/api/health did not answer ok"
drift="$(rsync -anc --delete --exclude __pycache__ -e "ssh -p $PORT" "$ROOT/api/app/" "$HOST:$LIVE/api/app/")"
[[ -z "$drift" ]] || die "the live API differs from the working copy: $drift"
built="$(grep -o 'assets/index[^"]*\.js' "$ROOT/web/dist/index.html")"
served="$(curl -fsS "$SITE/" | grep -o 'assets/index[^"]*\.js')"
[[ "$built" == "$served" ]] || die "the site serves $served, not the $built just built"

say "Deployed: tests passed, API healthy, site serving $built"
