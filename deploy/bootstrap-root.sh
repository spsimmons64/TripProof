#!/bin/bash
###################################################################################################
# One-time (and re-runnable) root setup for dev.tripproofonline.com.
#
#   sudo bash /home/spsimmons/tripproof-stage/deploy/bootstrap-root.sh
#
# Everything it needs has already been staged in /home/spsimmons/tripproof-stage as spsimmons:
# the api, the migrations, the built web, a python venv and the .env holding the database password.
# Re-running it is safe: it updates the tree in place and restarts the service.
###################################################################################################
set -euo pipefail

APP=/applications/dev.tripproofonline.com
STAGE=/home/spsimmons/tripproof-stage
OWNER=spsimmons
SITE=dev.tripproofonline.com

[[ $EUID -eq 0 ]] || { echo "Run this with sudo."; exit 1; }
[[ -d $STAGE ]] || { echo "Nothing staged at $STAGE"; exit 1; }
[[ -f $STAGE/.env ]] || { echo "No $STAGE/.env - the deploy script writes it"; exit 1; }

say() { printf '\n\033[1;36m== %s\033[0m\n' "$1"; }

say "system packages for WeasyPrint"
apt-get update -qq
apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libcairo2 libgdk-pixbuf-2.0-0 libffi8 fonts-dejavu-core >/dev/null
echo "ok"

say "application directory $APP"
install -d -o "$OWNER" -g www-data -m 2750 "$APP"
install -d -o "$OWNER" -g www-data -m 2750 "$APP/storage"

say "copying the staged tree into place"
for part in api db web venv; do
    rsync -a --delete "$STAGE/$part/" "$APP/$part/"
done
install -o "$OWNER" -g www-data -m 640 "$STAGE/.env" "$APP/.env"
chown -R "$OWNER":www-data "$APP"
# nginx (www-data) reads the web root and walks down to it; nothing else is world readable.
chmod -R a+rX "$APP/web"
echo "ok"

say "database"
DBNAME=$(grep -E '^DB_NAME=' "$APP/.env" | cut -d= -f2-)
DBUSER=$(grep -E '^DB_USER=' "$APP/.env" | cut -d= -f2-)
DBPASS=$(grep -E '^DB_PASSWORD=' "$APP/.env" | cut -d= -f2-)
mariadb <<SQL
CREATE DATABASE IF NOT EXISTS \`$DBNAME\` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER IF NOT EXISTS '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS';
ALTER USER '$DBUSER'@'localhost' IDENTIFIED BY '$DBPASS';
GRANT ALL PRIVILEGES ON \`$DBNAME\`.* TO '$DBUSER'@'localhost';
FLUSH PRIVILEGES;
SQL
echo "database $DBNAME and user $DBUSER ready"

# The laptop's test data is loaded once, into an empty database only: the PHI key in .env is the
# same one that encrypted those rows, so the existing account, drivers and applications open here.
TABLES=$(mariadb -N -B -e "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='$DBNAME'")
if [[ -f $STAGE/seed.sql.gz && $TABLES -eq 0 ]]; then
    say "loading the staged snapshot into an empty database"
    # The DEFINER stamps come from the machine the dump was taken on, where the login was
    # tripproof@%; here it is tripproof@localhost, and a view or trigger pointing at an account that
    # does not exist fails with "Access denied for user", which reads like a wrong password.
    gunzip -c "$STAGE/seed.sql.gz" | sed -E 's/DEFINER=[^ ]+ //g' | mariadb "$DBNAME"
    echo "loaded"
elif [[ -f $STAGE/seed.sql.gz ]]; then
    echo "snapshot skipped: $DBNAME already holds $TABLES tables"
fi

if [[ -f $STAGE/storage.tar.gz ]] && [[ -z $(ls -A "$APP/storage") ]]; then
    say "unpacking stored files"
    tar -xzf "$STAGE/storage.tar.gz" -C "$APP/storage"
    chown -R "$OWNER":www-data "$APP/storage"
    echo "ok"
fi

say "systemd unit"
install -m 644 "$STAGE/deploy/dev-tripproof-api.service" /etc/systemd/system/dev-tripproof-api.service
systemctl daemon-reload
systemctl enable dev-tripproof-api >/dev/null
systemctl restart dev-tripproof-api
sleep 3
systemctl --no-pager --lines=15 status dev-tripproof-api || true

say "nginx site"
install -m 644 "$STAGE/deploy/dev.tripproofonline.com.nginx" "/etc/nginx/sites-available/$SITE"
ln -sfn "/etc/nginx/sites-available/$SITE" "/etc/nginx/sites-enabled/$SITE"
nginx -t
systemctl reload nginx
echo "ok"

say "health check through nginx"
curl -fsS -H "Host: $SITE" http://127.0.0.1/api/health && echo

cat <<NEXT

Done. Still to do, once dev.tripproofonline.com resolves to this box:

    sudo certbot --nginx -d $SITE

NEXT
