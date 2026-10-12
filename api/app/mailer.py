###################################################################################################
# Outgoing mail - the one place that talks SMTP. Every message is multipart: the HTML design from
# app/emails.py plus a plain-text version for clients that don't show HTML (and for spam filters,
# which distrust HTML-only mail).
#
# Configured by SMTP_* in .env. Port 587 uses STARTTLS; port 465 is TLS from the first byte
# (SMTP_SSL=true). With no SMTP_HOST nothing is sent, and callers fall back (invitations show the
# link in the admin portal instead).
###################################################################################################
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

from app import emails
from app.config import settings

log = logging.getLogger("tripproof.mail")


def configured() -> bool:
    return bool(settings.smtp_host)


def send(to: str, subject: str, html: str, text: str,
         attachments: list[tuple[str, bytes, str]] | None = None) -> bool:
    """Send one message. Returns False (and logs why) instead of raising, so a mail outage never
    breaks the action that triggered it.

    `attachments` are (filename, bytes, mimetype) - already rendered by the caller, because a
    background task has no database connection to render them from."""
    if not configured():
        log.info("SMTP not configured; not sending %r to %s", subject, to)
        return False
    msg = EmailMessage()
    msg["From"] = settings.smtp_from
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=settings.smtp_from.rsplit("@", 1)[-1].rstrip(">") or None)
    msg.set_content(text)
    msg.add_alternative(html, subtype="html")
    # Images the HTML refers to by cid: travel with it (multipart/related), e.g. the signature logo.
    html_part = msg.get_payload()[1]
    for cid, data in emails.inline_images(html).items():
        html_part.add_related(data, maintype="image", subtype="png", cid=f"<{cid}>", filename=f"{cid}.png",
                              disposition="inline")
    for filename, blob, mimetype in attachments or []:
        maintype, _, subtype = (mimetype or "application/octet-stream").partition("/")
        msg.add_attachment(blob, maintype=maintype, subtype=subtype or "octet-stream",
                           filename=filename)
    ctx = ssl.create_default_context()
    # SMTP_INSECURE exists for one situation: a development mail host whose certificate has lapsed.
    # It turns off certificate and hostname checking, so anyone between here and the mail server can
    # read what is sent. Never set it anywhere real.
    if settings.smtp_insecure:
        log.warning("SMTP_INSECURE is set: the mail server's certificate is not being checked")
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    try:
        if settings.smtp_ssl:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=20, context=ctx)
        else:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20)
        with server as s:
            if not settings.smtp_ssl and settings.smtp_starttls:
                s.starttls(context=ctx)
            if settings.smtp_user:
                s.login(settings.smtp_user, settings.smtp_password)
            refused = s.send_message(msg)
        if refused:
            log.warning("server refused %r for %s: %s", subject, to, refused)
            return False
        log.info("sent %r to %s (message %s)", subject, to, msg["Message-ID"])
        return True
    except Exception:
        log.exception("could not send %r to %s", subject, to)
        return False
