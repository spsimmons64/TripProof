#!/usr/bin/env bash
# Publish the public site (site/) to tripproofonline.com. One static page - no build, no tests.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOST=spsimmons@arrowleaftech.io
PORT=5859
rsync -a --delete -e "ssh -p $PORT" "$ROOT/site/" "$HOST:/applications/tripproofonline.com/site/"
curl -fsS -o /dev/null -w "tripproofonline.com: %{http_code}\n" https://tripproofonline.com/
