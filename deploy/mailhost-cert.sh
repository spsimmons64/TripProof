#!/bin/bash
###################################################################################################
# Put the *.tripproofonline.com certificate on the mail host (10.0.10.10) and hand it to Postfix
# and Dovecot.
#
#   sudo bash mailhost-cert.sh /path/to/fullchain.pem /path/to/privkey.pem
#
# The certificate the server presents today expired on 22 Sep 2026 and names only
# mail.beyondmybooks.com, so every client that verifies TLS - including TripProof - refuses to
# send. A wildcard for *.tripproofonline.com covers mail.tripproofonline.com, which is the name
# TripProof connects to.
#
# The old certificate stays where it is; only what Postfix and Dovecot point at changes, and the
# previous values are printed before anything is written, so the change can be put back.
###################################################################################################
set -euo pipefail

CERT=${1:-}
KEY=${2:-}
DEST=/etc/ssl/tripproofonline

[[ $EUID -eq 0 ]] || { echo "Run this with sudo."; exit 1; }
[[ -f $CERT && -f $KEY ]] || { echo "Usage: sudo bash mailhost-cert.sh <fullchain.pem> <privkey.pem>"; exit 1; }

say() { printf '\n\033[1;36m== %s\033[0m\n' "$1"; }

say "the certificate you gave me"
openssl x509 -in "$CERT" -noout -subject -issuer -dates -ext subjectAltName
openssl x509 -in "$CERT" -noout -checkend 0 >/dev/null || { echo "That certificate has already expired."; exit 1; }
# A certificate and key that are not a pair would leave the server unable to start TLS at all.
c=$(openssl x509 -in "$CERT" -noout -pubkey | openssl sha256)
k=$(openssl pkey -in "$KEY" -pubout | openssl sha256)
[[ $c == "$k" ]] || { echo "That key does not belong to that certificate."; exit 1; }
echo "certificate and key match"

say "what Postfix uses now (write these down)"
postconf -h smtpd_tls_cert_file smtpd_tls_key_file smtpd_tls_security_level || true

say "installing into $DEST"
install -d -m 755 "$DEST"
install -m 644 "$CERT" "$DEST/fullchain.pem"
install -m 640 -g root "$KEY" "$DEST/privkey.pem"
echo "ok"

say "pointing Postfix at it"
postconf -e "smtpd_tls_cert_file = $DEST/fullchain.pem"
postconf -e "smtpd_tls_key_file = $DEST/privkey.pem"
postfix check
systemctl reload postfix
echo "ok"

if systemctl is-active --quiet dovecot; then
    say "pointing Dovecot at it"
    printf 'ssl_cert = <%s\nssl_key = <%s\n' "$DEST/fullchain.pem" "$DEST/privkey.pem" \
        > /etc/dovecot/conf.d/99-tripproof-ssl.conf
    doveconf -n >/dev/null
    systemctl reload dovecot
    echo "ok"
fi

say "what the server presents now"
for port in 587 465; do
    echo "--- $port"
    if [[ $port == 587 ]]; then
        openssl s_client -starttls smtp -connect 127.0.0.1:587 -servername mail.tripproofonline.com </dev/null 2>/dev/null
    else
        openssl s_client -connect 127.0.0.1:465 -servername mail.tripproofonline.com </dev/null 2>/dev/null
    fi | openssl x509 -noout -subject -dates -ext subjectAltName
done

cat <<'NEXT'

If the subject alternative names now include *.tripproofonline.com, TripProof can send with TLS
verification on. Renewals must copy the new files to the same two paths and reload Postfix.
NEXT
