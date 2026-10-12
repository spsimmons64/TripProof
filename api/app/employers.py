###################################################################################################
# Previous employer safety performance history - 49 CFR 391.23(d), (e) and (i).
#
# The carrier must ask every DOT-regulated employer from the previous three years about accidents
# and about drug and alcohol violations. 391.23(i) is what shapes this module:
#
#     the carrier must document a good faith effort to obtain the information, and the previous
#     employer's failure to respond does not relieve the carrier of the obligation
#
# So the record being kept is not the answer. It is the ASKING - every attempt, what channel it
# went by, to whom, and when. A file with one unanswered email in it is a different file from one
# with three attempts across two channels, and only the second is a good faith effort anybody would
# recognise.
#
# WHO GETS ASKED
#
# The employers come from the driver's own application, but they are COPIED here rather than read
# through it. A driver can correct their application afterwards; an inquiry that has already gone
# out went to the address it went to, and the record of it must not change underneath.
#
# THREE WAYS TO ASK, AND ONLY ONE OF THEM IS AUTOMATIC
#
#   email     a link the employer fills in, and the answer lands structured
#   fax       recorded here, sent elsewhere - online faxing is not built yet
#   mail      recorded here, printed and posted by the office
#
# The last two are attempts the office logs after doing them. That is not a lesser kind of record:
# 391.23(i) asks what was done, not what this software did.
###################################################################################################
import json
import secrets
from datetime import date, datetime, timedelta

from sqlalchemy.engine import Connection

from app.config import settings
from app.db import newid, row, rows, run, utcnow

# How long the employer's link stays alive. Longer than a driver's, because it is answered by
# somebody with no stake in answering it and a full inbox.
VALID_DAYS = 45

# 391.23(d): the three years before the application. A CMV driver's own employment history reaches
# back ten, but the safety performance inquiry is three.
LOOKBACK_YEARS = 3

# 391.23(d) again: the carrier has 30 days from the start of employment to obtain the history.
# After that, asking is late rather than diligent, and the honest thing is to stop asking and
# certify what was actually done inside the window.
REQUEST_DAYS = 30


def window(hiredon: date | None, today: date | None = None) -> dict:
    """Whether a request may still go out, and until when.

    Open for a driver nobody has hired yet - the clock runs from the start of employment, so there
    is nothing to run out. It is not an invitation to leave it: the inquiry is normally sent during
    hiring."""
    today = today or date.today()
    if not hiredon:
        return {"open": True, "closeson": None, "why": None}
    closes = hiredon + timedelta(days=REQUEST_DAYS)
    return {
        "open": today <= closes, "closeson": closes,
        "why": None if today <= closes else
               (f"The 30 days 49 CFR 391.23(d) allows ran out on {closes:%m/%d/%Y}. What is left "
                f"is to certify what was done inside the window."),
    }

CHANNELS = {
    "email": "Email",
    "fax": "Fax",
    "mail": "Mail",
    "phone": "Telephone",
    "inperson": "In person",
}


def link_for(token: str) -> str:
    return f"{settings.public_url.rstrip('/')}/employer-reply/{token}"


def _asked_of(employer: dict) -> bool:
    """Whether 391.23(d) reaches this employer at all.

    A DOT-regulated employer where the driver did safety-sensitive work. Somebody's Saturday job at
    a shop is in the employment history and is not a safety performance inquiry."""
    return (str(employer.get("dotregulated") or "").lower() in ("yes", "true", "1")
            and str(employer.get("safetysensitive") or "").lower() in ("yes", "true", "1"))


def _within(employer: dict, today: date) -> bool:
    """Whether the employment falls inside the three years the rule asks about."""
    through = employer.get("through")
    if not through:
        return True                             # still there, or no end date given
    try:
        ended = date.fromisoformat(str(through)[:10])
    except ValueError:
        return True                             # unreadable date: ask rather than skip
    return ended >= date(today.year - LOOKBACK_YEARS, today.month, today.day)


def from_application(conn: Connection, accountid: str, driverid: str,
                     today: date | None = None) -> list[dict]:
    """The previous employers this driver's application names who must be asked."""
    today = today or date.today()
    app_ = row(conn, """
        SELECT data FROM driverapplications
        WHERE driverid = :d AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=accountid)
    if not app_:
        return []
    try:
        steps = (json.loads(app_["data"] or "{}") or {}).get("steps") or {}
    except ValueError:
        return []
    found: list[dict] = []
    for step in steps.values():
        if isinstance(step, dict) and step.get("employers"):
            found.extend(step["employers"])
    return [e for e in found if _asked_of(e) and _within(e, today)]


def ensure(conn: Connection, accountid: str, driverid: str, createdby: str | None = None,
           today: date | None = None) -> int:
    """Open an inquiry for each employer who must be asked and has not been.

    Matched on the employer's name and the dates worked, because that is what the driver gave and
    what an auditor reads them by. Nothing already sent is touched."""
    made = 0
    for e in from_application(conn, accountid, driverid, today):
        already = row(conn, """
            SELECT recordid FROM employerinquiries
            WHERE accountid = :a AND driverid = :d AND employer = :name
              AND COALESCE(employedfrom, '1900-01-01') = COALESCE(:from_, '1900-01-01')
        """, a=accountid, d=driverid, name=(e.get("employer") or "")[:160],
            from_=e.get("from") or None)
        if already:
            continue
        run(conn, """
            INSERT INTO employerinquiries (recordid, accountid, driverid, employer, contactname,
                                           email, phone, address1, city, state, zip, employedfrom,
                                           employedthrough, dotregulated, safetysensitive, token,
                                           expireson, createdby)
            VALUES (:id, :a, :d, :name, :who, :em, :ph, :a1, :city, :st, :zip, :from_, :to_,
                    1, 1, :tok, :exp, :u)
        """, id=newid(), a=accountid, d=driverid, name=(e.get("employer") or "")[:160],
            who=(e.get("supervisor") or None), em=(e.get("email") or None),
            ph=(e.get("phone") or None), a1=(e.get("address1") or None),
            city=(e.get("city") or None), st=((e.get("state") or "")[:2] or None),
            zip=(e.get("zip") or None), from_=e.get("from") or None, to_=e.get("through") or None,
            tok=secrets.token_urlsafe(32), exp=utcnow() + timedelta(days=VALID_DAYS), u=createdby)
        made += 1
    return made


def attempts(conn: Connection, inquiryid: str) -> list[dict]:
    return rows(conn, """
        SELECT recordid, channel, sentto, senton, outcome, note, documentid
        FROM employerinquiryattempts WHERE inquiryid = :i ORDER BY senton DESC
    """, i=inquiryid)


def record_attempt(conn: Connection, accountid: str, inquiryid: str, *, channel: str,
                   sentto: str | None = None, note: str | None = None,
                   outcome: str | None = None, documentid: str | None = None,
                   enteredby: str | None = None, senton: datetime | None = None) -> str:
    """One attempt to reach an employer. This is the good faith effort, one row at a time."""
    rid = newid()
    run(conn, """
        INSERT INTO employerinquiryattempts (recordid, inquiryid, accountid, channel, sentto,
                                             senton, outcome, note, documentid, enteredby)
        VALUES (:id, :i, :a, :c, :to_, :on, :out, :n, :doc, :u)
    """, id=rid, i=inquiryid, a=accountid, c=channel, to_=(sentto or None),
        on=senton or utcnow(), out=(outcome or None), n=(note or None), doc=documentid,
        u=enteredby)
    return rid


# How an investigation ended. Five endings, and they are not interchangeable: a file saying the
# history was received is a different record from one saying nobody ever answered, and 391.23(i)
# turns on being able to tell them apart years later.
GFE_STATUS = {
    "received": "Investigation completed - records received",
    "noresponse": "Good faith effort completed - no response received",
    "unable": "Previous employer unable to provide records",
    "notlocated": "Previous employer cannot be located or no longer exists",
    "pending": "Investigation still pending",
}
# The ones that close it. "Pending" is an answer about where things stand, not an ending.
GFE_CLOSING = ("received", "noresponse", "unable", "notlocated")


# What the carrier decided about a reply once it read it - section 9 of the SPHI.
DISPOSITIONS = {
    "qualified": "Qualified",
    "disqualified": "Disqualified",
    "review": "Additional review required",
    "documentation": "Additional documentation required",
}


def standing(inquiry: dict, tried: list[dict]) -> tuple[str, str]:
    """Where one inquiry stands, and the sentence for it.

    An inquiry nobody has sent is not the same as one sent and unanswered, and neither is the
    same as one answered but unread. A reply arrives from outside this office and may say the
    driver was dismissed, or that there are accidents on their record - none of which anybody
    here has seen. So an answer does not finish the requirement; reading it does."""
    if inquiry.get("respondedon") and not inquiry.get("reviewedon"):
        # A reply beats an effort. "We asked and nobody answered" stops being true the moment they
        # answer, and what is on the table is a document nobody here has read.
        if inquiry.get("effortclosedon"):
            return "toreview", (f'Answered {inquiry["respondedon"]:%m/%d/%Y} after a good faith '
                                f'effort was filed - unread')
        return "toreview", f'Answered {inquiry["respondedon"]:%m/%d/%Y}, unread'
    if inquiry.get("respondedon"):
        return "answered", (f'{DISPOSITIONS.get(inquiry.get("disposition"), "Read")} '
                            f'{inquiry["reviewedon"]:%m/%d/%Y}')
    if inquiry.get("effortclosedon"):
        n = len(tried)
        # Said in the words of the ending it actually had. "Closed" told an auditor nothing about
        # whether the history was obtained or merely chased.
        ending = GFE_STATUS.get(inquiry.get("effortstatus") or "noresponse")
        return "effort", (f'{ending} - {inquiry["effortclosedon"]:%m/%d/%Y}, '
                          f'after {n} attempt{"" if n == 1 else "s"}')
    if tried:
        last = tried[0]
        return "waiting", (f'{CHANNELS.get(last["channel"], last["channel"])} '
                           f'{last["senton"]:%m/%d/%Y}, no answer')
    return "notasked", "Nobody has asked this employer yet"


def for_driver(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every inquiry on this driver, with its attempts and where it stands."""
    out = []
    for inq in rows(conn, """
        SELECT recordid, employer, contactname, email, fax, phone, address1, city, state, zip,
               employedfrom, employedthrough, token, requestsignature, requestsignedon,
               respondedon, respondedby, employed, employmentverified, position, accidentanswer,
               alcohol04, positivetest, refusedtest, otherviolation,
               disposition, reviewcomments, reviewedon,
               accidents, drugalcohol, responsenote, documentid, effortclosedon, effortnote,
               effortstatus, effortsignature, effortfontkey, effortsignedon, effortsupersededon,
               effortdocumentid
        FROM employerinquiries
        WHERE accountid = :a AND driverid = :d
        ORDER BY employedthrough DESC, employer
    """, a=accountid, d=driverid):
        tried = attempts(conn, inq["recordid"])
        state, says = standing(inq, tried)
        # MariaDB hands JSON back as a string through PyMySQL, so it is parsed here rather than
        # left for every reader to discover that `accidents` is text that looks like a list.
        got = dict(inq)
        for field in ("accidents", "drugalcohol"):
            raw = got.get(field)
            if isinstance(raw, (str, bytes)):
                try:
                    got[field] = json.loads(raw)
                except ValueError:
                    got[field] = None
        out.append({**got, "attempts": tried, "state": state, "says": says,
                    "link": link_for(inq["token"])})
    return out


def complete(inquiries: list[dict]) -> bool | None:
    """Whether the requirement is answered: every employer either replied or was chased and closed
    out. None where there is nobody to ask, because that is not the same as being finished."""
    if not inquiries:
        return None
    return all(i["state"] in ("answered", "effort") for i in inquiries)


def adverse(inquiry: dict) -> bool:
    """Whether a reply says something the office has to act on rather than merely file."""
    return (inquiry.get("accidentanswer") == "yes"
            or any(inquiry.get(k) == "yes" for k in
                   ("alcohol04", "positivetest", "refusedtest", "otherviolation")))
