#!/bin/bash
###################################################################################################
# Hand Postfix and Dovecot the *.tripproofonline.com certificate that is already on this host.
#
#   sudo bash /home/spsimmons/mailhost-wildcard.sh
#
# Today the server presents /etc/letsencrypt/live/mail.beyondmybooks.com, which expired on
# 22 Sep 2026 and names only that one host, so every client that verifies TLS refuses to send -
# TripProof included. /etc/letsencrypt/live/tripproofonline.com is the wildcard; it covers
# mail.tripproofonline.com, which is the name TripProof connects to.
#
# Nothing is deleted. The current settings are printed and saved before anything changes, and the
# last lines of the script show what the server presents afterwards.
###################################################################################################
set -euo pipefail

LIVE=/etc/letsencrypt/live/tripproofonline.com
BACKUP=/root/mail-tls-before-$(date +%Y%m%d-%H%M%S).txt

[[ $EUID -eq 0 ]] || { echo "Run this with sudo."; exit 1; }

say() { printf '\n\033[1;36m== %s\033[0m\n' "$1"; }

say "the wildcard certificate on this host"
[[ -f $LIVE/fullchain.pem ]] || { echo "No certificate at $LIVE"; exit 1; }
openssl x509 -in "$LIVE/fullchain.pem" -noout -subject -issuer -dates -ext subjectAltName
if ! openssl x509 -in "$LIVE/fullchain.pem" -noout -checkend 0 >/dev/null; then
    echo
    echo "That certificate has expired too. Renew it first:"
    echo "    sudo certbot certonly --manual --preferred-challenges dns -d 'tripproofonline.com' -d '*.tripproofonline.com'"
    echo "then run this script again."
    exit 1
fi
DAYS_LEFT=$(( ( $(date -d "$(openssl x509 -in "$LIVE/fullchain.pem" -noout -enddate | cut -d= -f2)" +%s) - $(date +%s) ) / 86400 ))
echo "valid, $DAYS_LEFT days left"

say "saving the current settings to $BACKUP"
{
    echo "postfix:"
    postconf -h smtpd_tls_cert_file smtpd_tls_key_file
    echo "dovecot:"
    doveconf -h ssl_cert ssl_key 2>/dev/null || true
} | tee "$BACKUP"

say "pointing Postfix at the wildcard"
postconf -e "smtpd_tls_cert_file = $LIVE/fullchain.pem"
postconf -e "smtpd_tls_key_file = $LIVE/privkey.pem"
postfix check
systemctl reload postfix
echo "ok"

if systemctl is-active --quiet dovecot; then
    say "pointing Dovecot at the wildcard"
    printf 'ssl_cert = <%s\nssl_key = <%s\n' "$LIVE/fullchain.pem" "$LIVE/privkey.pem" \
        > /etc/dovecot/conf.d/99-tripproof-ssl.conf
    doveconf -n >/dev/null
    systemctl reload dovecot
    echo "ok"
fi

# A renewal writes new files behind the same paths; the daemons keep the old ones in memory until
# they are told, which is how the current certificate went stale without anyone noticing.
say "reloading the daemons on every future renewal"
install -d -m 755 /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/10-reload-mail.sh <<'HOOK'
#!/bin/sh
# Certbot runs this after any successful renewal.
systemctl reload postfix 2>/dev/null || true
systemctl is-active --quiet dovecot && systemctl reload dovecot 2>/dev/null || true
HOOK
chmod 755 /etc/letsencrypt/renewal-hooks/deploy/10-reload-mail.sh
echo "ok"

say "what the server presents now"
echo "--- 587 STARTTLS, SNI mail.tripproofonline.com"
openssl s_client -starttls smtp -connect 127.0.0.1:587 -servername mail.tripproofonline.com </dev/null 2>/dev/null \
    | openssl x509 -noout -subject -dates -ext subjectAltName
echo "--- 465 implicit TLS"
openssl s_client -connect 127.0.0.1:465 -servername mail.tripproofonline.com </dev/null 2>/dev/null \
    | openssl x509 -noout -subject -dates -ext subjectAltName

cat <<'NEXT'

If the names above include *.tripproofonline.com, TripProof can send with verification on.

Both certificates on this host were issued with certbot's manual DNS challenge, which is why the
old one expired unnoticed: `certbot renew` cannot run it unattended. Worth fixing separately.
NEXT
