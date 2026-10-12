###################################################################################################
# Email designs render correctly (no database, no SMTP), and invitations go out through the mailer.
###################################################################################################
from datetime import datetime

from app import emails, invitations, mailer
from app.config import settings

LINK = "https://app.tripproofonline.com/reset?token=abc123"


def render(**over):
    args = dict(purpose="invite", name="Jordan <Rivera>", email="jordan@example.com", link=LINK,
                expires=datetime(2026, 9, 28, 18, 15), accountname="Gulf Coast & Sons", staff=False, role="admin",
                invitedby="Pat Admin", tz="America/Chicago")
    return emails.invitation(**{**args, **over})


def test_invitation_email():
    subject, html, text = render()
    assert subject == "You're invited to TripProof - create your password"
    assert html.startswith("<!DOCTYPE html>") and 'lang="en"' in html
    assert f'href="{LINK}"' in html and LINK in text                      # button + fallback link + text version
    assert "Create your password" in html and "Create your password" in text
    assert "Jordan &lt;Rivera&gt;" not in html and "Hi Jordan," in html     # first name only, and escaped
    assert "Gulf Coast &amp; Sons" in html and "<Rivera>" not in html
    assert "Pat Admin" in html and "Administrator" in html
    assert "Monday, September 28 at 1:15 PM CDT" in html                  # expiry in the recipient's zone
    assert "Trip Proof Online" in html and "Trip Proof Online" in text


def test_staff_invite_and_reset_wording():
    _, html, _ = render(staff=True, role="support", accountname="TripProof (staff)")
    assert "TripProof admin portal" in html and "Support (read-only)" in html
    subject, html, text = render(purpose="reset")
    assert subject == "Reset your TripProof password" and "Choose a new password" in html and "72 hours" in text


def test_deliver_sends_through_the_mailer(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, html, text: sent.append((to, subject)) or True)
    invitations.deliver(purpose="invite", name="Jordan Rivera", email="jordan@example.com", link=LINK,
                        expires=datetime(2026, 9, 28, 18, 15), accountname="Acme", staff=False, role="staff",
                        invitedby=None, tz=None)
    assert sent == [("jordan@example.com", "You're invited to TripProof - create your password")]


def test_mailer_does_nothing_without_a_host(monkeypatch):
    monkeypatch.setattr(settings, "smtp_host", "")
    assert mailer.send("x@example.com", "s", "<p>h</p>", "t") is False


def test_signature_logo_and_confidentiality_notice():
    _, html, text = render()
    assert 'src="cid:tripproof-logo"' in html and "The TripProof Team" in html and "The TripProof Team" in text
    assert "CONFIDENTIALITY NOTICE" in html and "CONFIDENTIALITY NOTICE" in text
    assert html.index("The TripProof Team") < html.index("CONFIDENTIALITY NOTICE")    # the notice comes last
    assert emails.logo_png().startswith(b"\x89PNG")
    assert "cid:" not in emails.for_browser(html) and "data:image/png;base64," in emails.for_browser(html)


def test_mailer_embeds_the_logo_inline(monkeypatch):
    captured = []

    class FakeSMTP:
        def __init__(self, *a, **k): pass
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def starttls(self, **k): pass
        def login(self, *a): pass
        def send_message(self, msg): captured.append(msg)

    monkeypatch.setattr(settings, "smtp_host", "smtp.example.test")
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    subject, html, text = render()
    assert mailer.send("jordan@example.com", subject, html, text) is True
    msg = captured[0]
    assert msg["From"] == settings.smtp_from
    parts = {p.get_content_type(): p for p in msg.walk()}
    assert {"text/plain", "text/html", "multipart/related", "image/png"} <= set(parts)
    img = parts["image/png"]
    assert img["Content-ID"] == "<tripproof-logo>" and img.get_content_disposition() == "inline"
