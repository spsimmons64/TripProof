###################################################################################################
# Email designs. Every TripProof email is built from layout(): a branded header, a white card, one
# clear call-to-action button, and a footer - in the product's palette.
#
# Email clients are not browsers (Outlook renders with Word, Gmail strips <style> in places), so
# the markup is deliberately old-fashioned: tables for layout, every style inline, a single
# embedded image (below), a "bulletproof" button that is a padded link inside a table cell, a
# hidden preheader (the preview line in the inbox), and light color-scheme only so dark-mode
# clients don't invert the brand colors. Each email also returns a plain-text version.
#
# The one image is the logo in the signature. It travels inside the message as an inline (cid:)
# attachment - mailer.send attaches it - so it shows without being fetched from a web server
# (PUBLIC_URL is localhost in development, and many clients block remote images anyway).
#
# Add a new email as a function returning (subject, html, text), using layout() and button().
###################################################################################################
import base64
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

TEAL_DARK = "#0f3a43"
TEAL = "#1c6979"
TEAL_MID = "#4a9eb4"
TEAL_LIGHT = "#81bfcb"
SAND = "#ece6e2"
ORANGE = "#ffa52f"
INK = "#13272b"
MUTED = "#5b6d71"
BRAND = "Trip Proof Online"
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif"

# The signature logo: api/app/assets/email_logo.png, cut from the brand sheet tripproof_logo.png
# (stacked mark, transparent background, 2x for sharp high-DPI display at 120px wide).
LOGO_CID = "tripproof-logo"
LOGO_FILE = Path(__file__).parent / "assets" / "email_logo.png"
LOGO_WIDTH, LOGO_HEIGHT = 120, 94


@lru_cache(maxsize=1)
def logo_png() -> bytes:
    return LOGO_FILE.read_bytes()


def inline_images(html: str) -> dict[str, bytes]:
    """The inline images an email's HTML refers to, by content-id (for mailer.send)."""
    return {LOGO_CID: logo_png()} if f"cid:{LOGO_CID}" in html else {}


def for_browser(html: str) -> str:
    """The same HTML with inline images swapped for data: URIs, for previewing in a browser."""
    return html.replace(f"cid:{LOGO_CID}", "data:image/png;base64," + base64.b64encode(logo_png()).decode())


CONFIDENTIALITY = (
    "CONFIDENTIALITY NOTICE: This email and any attachments are confidential and intended solely for the "
    "person or entity to which they are addressed. They may contain information that is privileged, "
    "confidential, or protected from disclosure under applicable law, including protected health "
    "information under HIPAA. If you are not the intended recipient, you are notified that any review, "
    "use, disclosure, copying, or distribution of this email is strictly prohibited. If you received it "
    "in error, please delete it and all copies, and notify the sender by contacting TripProof support. "
    "This notice is not a waiver of any privilege or protection.")


def button(label: str, href: str) -> str:
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" style="margin:8px 0 4px">
  <tr><td align="center" bgcolor="{TEAL}" style="border-radius:999px;background:{TEAL}">
    <a href="{escape(href)}" target="_blank" style="display:inline-block;padding:14px 32px;font-family:{FONT};font-size:16px;
       font-weight:700;color:#ffffff;text-decoration:none;border-radius:999px;background:{TEAL}">{escape(label)}</a>
  </td></tr></table>"""


def detail_rows(rows: list[tuple[str, str]]) -> str:
    """A small label/value table (e.g. sign-in email, role), values already escaped by the caller."""
    cells = "".join(
        f"""<tr><td style="padding:6px 0;font-family:{FONT};font-size:13px;color:{MUTED};width:130px;vertical-align:top">{escape(k)}</td>
            <td style="padding:6px 0;font-family:{FONT};font-size:14px;color:{INK};font-weight:600">{v}</td></tr>"""
        for k, v in rows)
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
      style="margin:18px 0;border-top:1px solid #e6e1dc;border-bottom:1px solid #e6e1dc">{cells}</table>"""


def layout(*, preheader: str, heading: str, body: str, footer_note: str) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><meta name="supported-color-schemes" content="light only">
<title>{escape(heading)}</title>
</head>
<body style="margin:0;padding:0;background:{SAND};-webkit-text-size-adjust:100%">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:transparent">{escape(preheader)}&#8199;&#847;&#8199;&#847;&#8199;&#847;&#8199;&#847;</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{SAND}" style="background:{SAND}">
  <tr><td align="center" style="padding:32px 16px">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" style="width:100%;max-width:600px">
      <!-- header -->
      <tr><td bgcolor="{TEAL_DARK}" style="background:{TEAL_DARK};border-radius:14px 14px 0 0;padding:22px 32px">
        <table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
          <td width="36" height="36" align="center" bgcolor="{TEAL}" style="background:{TEAL};border-radius:9px;font-family:{FONT};
              font-size:18px;font-weight:800;color:#ffffff;line-height:36px">&#10003;</td>
          <td style="padding-left:12px;font-family:{FONT};font-size:22px;font-weight:800;color:#ffffff;letter-spacing:-0.2px">TripProof</td>
        </tr></table>
      </td></tr>
      <tr><td height="4" bgcolor="{ORANGE}" style="background:{ORANGE};font-size:0;line-height:0">&nbsp;</td></tr>
      <!-- card -->
      <tr><td bgcolor="#ffffff" style="background:#ffffff;padding:36px 32px 30px;border-radius:0 0 14px 14px">
        <h1 style="margin:0 0 18px;font-family:{FONT};font-size:26px;line-height:1.25;font-weight:800;color:{TEAL_DARK}">{escape(heading)}</h1>
        {body}
        {signature()}
      </td></tr>
      <!-- footer -->
      <tr><td style="padding:22px 32px 8px;font-family:{FONT};font-size:12px;line-height:1.6;color:{MUTED};text-align:center">
        {footer_note}<br>
        <strong style="color:{TEAL}">{BRAND}</strong> &middot; Trip-level credential proof for NEMT providers<br>
        This is an automated message from a no-reply address &mdash; replies aren&rsquo;t monitored.
      </td></tr>
      <tr><td style="padding:14px 32px 0;font-family:{FONT};font-size:10.5px;line-height:1.55;color:#7d8b8e;text-align:justify">
        {escape(CONFIDENTIALITY)}
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def signature() -> str:
    """The sign-off at the end of every email, with the logo."""
    return f"""<table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%"
      style="margin-top:26px;border-top:1px solid #e6e1dc">
  <tr><td style="padding-top:22px;font-family:{FONT};font-size:15px;line-height:1.5;color:{INK}">
    Thank you,<br><strong>The TripProof Team</strong>
  </td></tr>
  <tr><td style="padding-top:14px">
    <img src="cid:{LOGO_CID}" width="{LOGO_WIDTH}" height="{LOGO_HEIGHT}" alt="TripProof"
         style="display:block;width:{LOGO_WIDTH}px;height:{LOGO_HEIGHT}px;border:0;outline:none;text-decoration:none">
  </td></tr>
</table>"""


TEXT_SIGNATURE = f"Thank you,\nThe TripProof Team\n{BRAND}\n\n{CONFIDENTIALITY}"


def p(text_html: str, *, small: bool = False, muted: bool = False) -> str:
    size, color = ("13px", MUTED) if small or muted else ("16px", INK)
    return f'<p style="margin:0 0 16px;font-family:{FONT};font-size:{size};line-height:1.6;color:{color}">{text_html}</p>'


def _when(expires: datetime, tz: str | None) -> str:
    """'Monday, September 28 at 2:15 PM EDT' in the recipient's time zone."""
    local = expires.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz or "America/New_York"))
    return local.strftime("%A, %B %-d at %-I:%M %p %Z")


# ------------------------------------------------------------------------------------------------
# Invitations and resets
# ------------------------------------------------------------------------------------------------

ROLE_NAMES = {"superadmin": "Super admin", "support": "Support (read-only)", "owner": "Owner", "admin": "Administrator",
              "staff": "Staff", "auditor": "Auditor (read-only)"}


def invitation(*, purpose: str, name: str, email: str, link: str, expires: datetime, accountname: str,
               staff: bool, role: str | None, invitedby: str | None, tz: str | None) -> tuple[str, str, str]:
    """The email with a link to create (invite) or reset a password."""
    first = (name or "").split(" ")[0] or "there"
    where = "the TripProof admin portal" if staff else f"{accountname} on TripProof"
    when = _when(expires, tz)
    lifetime = "7 days" if purpose == "invite" else "72 hours"
    if purpose == "invite":
        subject = "You're invited to TripProof - create your password"
        heading = "You're invited to TripProof"
        preheader = f"{invitedby or 'Your administrator'} added you to {where}. Create your password to sign in."
        intro = (f"{escape(invitedby)} has" if invitedby else "You've been") + \
            f" {'added you to' if invitedby else 'added to'} <strong>{escape(where)}</strong>. " \
            "To finish setting up your account, create a password."
        action = "Create your password"
    else:
        subject = "Reset your TripProof password"
        heading = "Reset your password"
        preheader = "Choose a new password for your TripProof sign-in."
        intro = (f"{escape(invitedby)} started" if invitedby else "An administrator started") + \
            " a password reset for your TripProof sign-in. Choose a new password to continue. " \
            "Your current password keeps working until you do."
        action = "Choose a new password"
    details = [("Sign-in email", escape(email)), ("Account", escape("TripProof staff" if staff else accountname))]
    if role:
        details.append(("Role", escape(ROLE_NAMES.get(role, role))))
    body = (
        p(f"Hi {escape(first)},")
        + p(intro)
        + detail_rows(details)
        + button(action, link)
        + p(f"This link can be used once and expires in {lifetime} &mdash; <strong>{escape(when)}</strong>.", small=True)
        + p(f'Button not working? Copy this link into your browser:<br>'
            f'<a href="{escape(link)}" style="color:{TEAL};word-break:break-all">{escape(link)}</a>', small=True)
    )
    footer = "If you weren&rsquo;t expecting this email, you can safely ignore it &mdash; no account changes will be made."
    html = layout(preheader=preheader, heading=heading, body=body, footer_note=footer)
    text = "\n".join([
        f"Hi {first},", "",
        (f"{invitedby} has added you to {where}." if invitedby and purpose == "invite" else
         f"You've been added to {where}." if purpose == "invite" else
         "A password reset was started for your TripProof sign-in. Your current password keeps working until you choose a new one."),
        "", f"Sign-in email: {email}", f"Account: {'TripProof staff' if staff else accountname}",
        *( [f"Role: {ROLE_NAMES.get(role, role)}"] if role else [] ), "",
        f"{action}: {link}", "",
        f"This link can be used once and expires in {lifetime} ({when}).",
        "If you weren't expecting this email, you can ignore it.", "",
        TEXT_SIGNATURE,
    ])
    return subject, html, text


def road_test_requested(*, examiner: str, accountname: str, driver: str, link: str,
                        days: int) -> tuple[str, str, str]:
    """To the person who will administer a road test under 49 CFR 391.31.

    Written for somebody who may not work here: it says who is asking, who they are testing, and
    that the form and the certificate are the same page - so nobody goes looking for a second
    document to sign afterwards."""
    company = escape(accountname)
    subject = f"Road test - {driver}"
    body = (
        p(f"To {escape(examiner)},")
        + p(f"<strong>{company}</strong> has asked you to administer a road test for "
            f"<strong>{escape(driver)}</strong> under 49 CFR 391.31.")
        + p("The link opens the evaluation form. Record what you saw, say whether the driver "
            "passed, and sign - the certificate is produced from what you enter, so there is "
            "nothing else to fill in afterwards.")
        + button("Open the road test", link)
        + p(f"The link works for {days} days.", small=True)
        + p("The test must be conducted in a vehicle representative of the type the driver will "
            "operate.", small=True, muted=True)
    )
    html = layout(preheader=f"{accountname} has asked you to road test {driver}.",
                  heading="Road test", body=body,
                  footer_note=f"This request comes from {company}.")
    text = "\n".join([
        f"To {examiner},", "",
        f"{accountname} has asked you to administer a road test for {driver} under 49 CFR 391.31.",
        "",
        "Record what you saw, say whether the driver passed, and sign. The certificate is produced "
        "from what you enter.", "",
        f"Open the road test here: {link}", "",
        f"The link works for {days} days.", "",
        "The test must be conducted in a vehicle representative of the type the driver will "
        "operate.",
    ])
    return subject, html, text


def employer_history_requested(*, employer: str, accountname: str, driver: str, link: str,
                               days: int) -> tuple[str, str, str]:
    """To a previous employer, under 49 CFR 391.23(d) and (e).

    Written for somebody with no stake in answering it: it says who is asking, who they are asking
    about, that the driver consented in writing, and how long it takes. The two questions are named
    outright, because an employer who knows what is being asked answers faster than one who has to
    open a link to find out."""
    company = escape(accountname)
    subject = f"Safety performance history request - {driver}"
    body = (
        p(f"To {escape(employer)},")
        + p(f"<strong>{company}</strong> is considering <strong>{escape(driver)}</strong> for a "
            "driving position and is required to ask you about their safety performance history "
            "with you (49 CFR 391.23(d) and (e)).")
        + p("There are two questions: any accidents they were involved in, and any drug or alcohol "
            "testing violations. The driver has given written consent for you to release this.")
        + button("Answer online", link)
        + p(f"It takes a couple of minutes and the link works for {days} days. If you would rather "
            "reply another way, or this person never worked for you, say so on the same page.",
            small=True)
        + p("You are asked to reply within 30 days of the request.", small=True, muted=True)
    )
    html = layout(preheader=f"{accountname} is asking about {driver} under 49 CFR 391.23.",
                  heading="Safety performance history", body=body,
                  footer_note=f"This request comes from {company}.")
    text = "\n".join([
        f"To {employer},", "",
        f"{accountname} is considering {driver} for a driving position and is required to ask you "
        "about their safety performance history with you (49 CFR 391.23(d) and (e)).", "",
        "There are two questions: any accidents they were involved in, and any drug or alcohol "
        "testing violations. The driver has given written consent for you to release this.", "",
        f"Answer online here: {link}", "",
        f"The link works for {days} days. If this person never worked for you, say so on the same "
        "page.", "",
        "You are asked to reply within 30 days of the request.",
    ])
    return subject, html, text


def document_requested(*, name: str, accountname: str, document: str, link: str,
                       days: int) -> tuple[str, str, str]:
    """To the driver, when the office needs a document only they hold: what it is, and where to put
    it. Nothing here says why it is wanted - the reason is often the driver's own licence history,
    and an email subject line is read by whoever is standing behind them."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"{accountname} needs a document from you"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"<strong>{company}</strong> needs a copy of one document for your file:")
        + p(f"<strong>{escape(document)}</strong>")
        + button("Upload it", link)
        + p("You will be asked for your date of birth and Social Security number first, so that only "
            f"you can use this link. It works for {days} days.", small=True)
        + p("A clear photograph is fine. If you do not have the document, tell "
            f"{company} rather than uploading something else.", small=True)
        + p("If you were not expecting this, you can ignore it - nothing is added unless you add it.",
            small=True, muted=True)
    )
    html = layout(preheader=f"{accountname} needs a copy of {document}.",
                  heading="One document to upload", body=body,
                  footer_note=f"Questions? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"{accountname} needs a copy of one document for your file: {document}.", "",
        f"Upload it here: {link}", "",
        "You will be asked for your date of birth and Social Security number first, so that only you "
        f"can use this link. It works for {days} days.", "",
        "A clear photograph is fine. If you do not have the document, tell the company rather than "
        "uploading something else.", "",
        "If you were not expecting this, you can ignore it - nothing is added unless you add it.",
    ])
    return subject, html, text


def signature_requested(*, name: str, accountname: str, document: str, link: str,
                        days: int) -> tuple[str, str, str]:
    """To the driver, when the office needs one more signature: what it is, and the way to give it."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"{accountname} needs your signature"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"<strong>{company}</strong> needs your signature on one document:")
        + p(f"<strong>{escape(document)}</strong>")
        + button("Read and sign it", link)
        + p("You will be asked for your date of birth and Social Security number first, so that only "
            "you can sign it. The link works for "
            f"{days} days.", small=True)
        + p("If you were not expecting this, you can ignore it - nothing is signed unless you sign it.",
            small=True, muted=True)
    )
    html = layout(preheader=f"{accountname} needs your signature on {document}.",
                  heading="One document to sign", body=body,
                  footer_note=f"Questions? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"{accountname} needs your signature on one document: {document}.", "",
        f"Read and sign it here: {link}", "",
        "You will be asked for your date of birth and Social Security number first, so that only you "
        f"can sign it. The link works for {days} days.", "",
        "If you were not expecting this, you can ignore it - nothing is signed unless you sign it.",
    ])
    return subject, html, text


def supervisor_appointed(name: str, accountname: str, link: str) -> tuple[str, str, str]:
    """To a user of the account who has just been made a reasonable suspicion supervisor.

    Not a document request. They already have a login here, so the link only takes them to the
    page - what makes it theirs to sign is signing in, not holding the URL."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"You are now a reasonable suspicion supervisor at {accountname}"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"<strong>{company}</strong> has appointed you as a reasonable suspicion supervisor. "
            "That means you may be the person who decides whether a driver is sent for a drug "
            "or alcohol test on reasonable suspicion.")
        + p("49 CFR 382.603 asks that you have had at least sixty minutes of training on alcohol "
            "misuse and sixty on controlled substances, and that the record says so. Your "
            "training record is waiting for your signature.")
        + button("Read and sign your training record", link)
        + p("Sign in as usual and it is on the page. Nobody else can sign it for you - a record "
            "somebody else fills in about you is not you saying you were trained.", small=True)
    )
    html = layout(preheader=f"{accountname} has appointed you a reasonable suspicion supervisor.",
                  heading="Your training record needs your signature", body=body,
                  footer_note=f"Questions? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"{accountname} has appointed you as a reasonable suspicion supervisor. You may be the "
        "person who decides whether a driver is sent for a drug or alcohol test on reasonable "
        "suspicion.", "",
        "49 CFR 382.603 asks that you have had at least sixty minutes of training on alcohol "
        "misuse and sixty on controlled substances, and that the record says so. Your training "
        "record is waiting for your signature.", "",
        f"Read and sign it here: {link}", "",
        "Sign in as usual and it is on the page. Nobody else can sign it for you.",
    ])
    return subject, html, text


def welcome_aboard(*, name: str, accountname: str, link: str, days: int) -> tuple[str, str, str]:
    """To the driver, the moment they are hired: congratulations, and the two forms to complete.

    One message and one link. A new employee who gets two emails on their first day signs one of
    them and wonders what the other was."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"Welcome to {accountname}"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"Congratulations - you have been hired by <strong>{company}</strong>. "
            "Welcome aboard.")
        + p("Before your first day there are two federal forms every new employee completes:")
        + p("<strong>Form I-9</strong>, Employment Eligibility Verification<br>"
            "<strong>Form W-4</strong>, Employee&rsquo;s Withholding Certificate")
        + button("Complete and sign both forms", link)
        + p("You will see the real forms, already filled in with what you gave us, and you sign "
            "each one. You will be asked for your date of birth and Social Security number first, "
            "so that only you can sign them. The link works for "
            f"{days} days.", small=True)
        + p("Bring your identification documents on your first day - the I-9 needs somebody here "
            "to examine them in person.", small=True, muted=True)
    )
    html = layout(preheader=f"Welcome to {accountname} - two forms to complete.",
                  heading="Welcome aboard", body=body,
                  footer_note=f"Questions? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"Congratulations - you have been hired by {accountname}. Welcome aboard.", "",
        "Before your first day there are two federal forms every new employee completes:",
        "  Form I-9, Employment Eligibility Verification",
        "  Form W-4, Employee's Withholding Certificate", "",
        f"Complete and sign both here: {link}", "",
        "You will see the real forms, already filled in with what you gave us, and you sign each "
        "one. You will be asked for your date of birth and Social Security number first, so that "
        f"only you can sign them. The link works for {days} days.", "",
        "Bring your identification documents on your first day - the I-9 needs somebody here to "
        "examine them in person.",
    ])
    return subject, html, text


def application_received(*, name: str, accountname: str) -> tuple[str, str, str]:
    """To the driver, the moment they submit: we have it, and here is what happens next."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"{accountname} has your driver application"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"Thank you for applying to drive for <strong>{company}</strong>. Your application and every "
            "document you signed have been received and stored securely.")
        + p("<strong>What happens next</strong>")
        + p("The office reviews your application, checks your driving record and background as you "
            "authorized, and contacts you about the next step. Nothing further is needed from you right now.")
        + p(f"If anything needs correcting, {company} will send the application back to you and you can "
            "pick it up where you left off.", small=True)
    )
    html = layout(preheader=f"{accountname} has received your driver application.",
                  heading="We have your application", body=body,
                  footer_note=f"Questions about your application? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"Thank you for applying to drive for {accountname}. Your application and every document you "
        "signed have been received and stored securely.", "",
        "What happens next: the office reviews your application, checks your driving record and "
        "background as you authorized, and contacts you about the next step. Nothing further is needed "
        "from you right now.", "",
        f"If anything needs correcting, {accountname} will send the application back to you and you can "
        "pick it up where you left off.", "",
        TEXT_SIGNATURE,
    ])
    return subject, html, text


def application_submitted(*, drivername: str, accountname: str, link: str, cmv: bool,
                          documents: int) -> tuple[str, str, str]:
    """To the company: someone has applied, and this is where to read it."""
    who = escape(drivername.title())
    subject = f"New driver application: {drivername.title()}"
    body = (
        p(f"<strong>{who}</strong> has completed a driver application for {escape(accountname)} and it is "
          "waiting to be reviewed.")
        + detail_rows([
            ("Applicant", who),
            ("Will drive a commercial vehicle", "Yes" if cmv else "No"),
            ("Documents signed", str(documents)),
        ])
        + button("Review the application", link)
        + p("The application opens as the driver filled it in, with everything they signed and uploaded. "
            "From there you can move them to Pending, send it back for corrections, or mark them not hired.",
            small=True)
    )
    html = layout(preheader=f"{drivername.title()} has applied to drive for {accountname}.",
                  heading="A new driver application", body=body,
                  footer_note="You are receiving this because your company takes applications online through TripProof.")
    text = "\n".join([
        f"{drivername.title()} has completed a driver application for {accountname} and it is waiting to be "
        "reviewed.", "",
        f"Will drive a commercial vehicle: {'Yes' if cmv else 'No'}",
        f"Documents signed: {documents}", "",
        f"Review the application: {link}", "",
        TEXT_SIGNATURE,
    ])
    return subject, html, text


def application_returned(*, name: str, accountname: str, link: str, note: str | None) -> tuple[str, str, str]:
    """To the driver when the office sends the application back: what to put right, and the way back in."""
    first = (name or "").split(" ")[0].title() or "there"
    company = escape(accountname)
    subject = f"{accountname} needs a correction to your driver application"
    body = (
        p(f"Hi {escape(first)},")
        + p(f"<strong>{company}</strong> has looked at your driver application and needs something corrected "
            "before it can go any further.")
        + (p("<strong>What needs correcting</strong>") + p(escape(note).replace("\n", "<br>")) if note else
           p("The office did not say what needs correcting - contact them if you are not sure."))
        + button("Open your application", link)
        + p("Your application opens where you left it, with everything you entered still there. You will be "
            "asked for your date of birth and Social Security number, which is how we find it, and you sign "
            "again when you submit.", small=True)
    )
    html = layout(preheader=f"{accountname} needs a correction to your application.",
                  heading="Your application needs a correction", body=body,
                  footer_note=f"Questions about what to change? Contact {company} directly.")
    text = "\n".join([
        f"Hi {first},", "",
        f"{accountname} has looked at your driver application and needs something corrected before it can go "
        "any further.", "",
        *( [f"What needs correcting: {note}", ""] if note else
           ["The office did not say what needs correcting - contact them if you are not sure.", ""] ),
        f"Open your application: {link}", "",
        "It opens where you left it, with everything you entered still there. You will be asked for your date "
        "of birth and Social Security number, which is how we find it, and you sign again when you submit.", "",
        TEXT_SIGNATURE,
    ])
    return subject, html, text


def sample_invitation(link: str = "https://app.tripproofonline.com/reset?token=EXAMPLE") -> tuple[str, str, str]:
    """For previewing the design (admin portal)."""
    return invitation(purpose="invite", name="Jordan Rivera", email="jordan@example.com", link=link,
                      expires=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=7),
                      accountname="Gulf Coast Care Rides", staff=False, role="admin", invitedby="Platform Admin",
                      tz="America/New_York")
