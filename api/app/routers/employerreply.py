###################################################################################################
# A previous employer answering, from a link - 49 CFR 391.23(d) and (e).
#
# The person at the other end has no account here, no stake in answering, and is doing the asking
# carrier a favour. So this is built to be finished in two minutes on a phone:
#
#   they open it   -> who is asking, who about, and the dates the driver gave
#   they answer    -> did this person work for you, then the two statutory questions
#   they sign      -> their name and title, which is what makes it a response and not a form
#
# WHAT THE PAGE DOES NOT DO
#
# It does not ask them to prove who they are. There is nothing to prove against - the carrier has
# no record of this employer's staff - and a password gate on a favour is a favour that does not
# get done. What protects it is that the token says nothing until it is opened and reveals only
# what the driver already told us about their own employment.
#
# It cannot be answered twice. An employer who replies and then changes their mind rings the
# carrier, and the carrier records that - because a record that can be silently rewritten by
# whoever holds the link is not evidence of anything.
###################################################################################################
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import employers, events, sphiview
from app.db import get_conn, row, run, saved, utcnow
from app.security import client_ip

router = APIRouter(prefix="/api/employer-reply", tags=["employerreply"])


def _open_inquiry(conn: Connection, token: str) -> dict:
    found = row(conn, """
        SELECT i.recordid, i.accountid, i.driverid, i.employer, i.contactname, i.email, i.phone,
               i.address1, i.city, i.state, i.zip, i.employedfrom, i.employedthrough,
               i.respondedon, i.expireson, i.createdon,
               d.firstname, d.lastname, d.dob, d.licensenumber, d.licensestate, d.drivernumber,
               a.name AS accountname, a.address1 AS accountaddress, a.city AS accountcity,
               a.state AS accountstate, a.zip AS accountzip, a.phone AS accountphone,
               a.email AS accountemail
        FROM employerinquiries i
        JOIN drivers d ON d.recordid = i.driverid
        JOIN accounts a ON a.recordid = i.accountid
        WHERE i.token = :tok
    """, tok=token)
    if not found:
        raise HTTPException(404, "That link is not valid")
    if found["respondedon"]:
        raise HTTPException(409, "This request has already been answered. Thank you.")
    if found["expireson"] and found["expireson"] < utcnow():
        raise HTTPException(410, "That link has expired - contact the company that sent it")
    return found


@router.get("/{token}")
def what_is_being_asked(token: str, request: Request, conn: Connection = Depends(get_conn)):
    """The form, with everything already known filled in.

    Sections 1, 2 and 3 of the SPHI are things the carrier knows and the employer should not have to
    type: who the driver is, who is asking, and what the driver said about working there. The
    employer confirms or corrects; they do not transcribe.

    The driver's license number is here because the form asks for it and it is how a previous
    employer finds the right person in their own records - the same reason their date of birth is.
    Nothing is shown that the carrier did not already hold about their own applicant."""
    held = _open_inquiry(conn, token)
    return {
        # Where the person signing is, for the stamp under their signature - the same address the
        # reply is recorded against when it is sent.
        "ip": client_ip(request),
        # 1 - the driver, so the employer can find them in their records
        "driver": {
            "name": f'{held["firstname"]} {held["lastname"]}'.strip().title(),
            "dob": held["dob"],
            "licensenumber": held["licensenumber"],
            "licensestate": held["licensestate"],
            "driverid": held["drivernumber"],
        },
        # 2 - who is asking
        "requestor": {
            "company": held["accountname"],
            "address1": held["accountaddress"],
            "city": held["accountcity"],
            "state": held["accountstate"],
            "zip": held["accountzip"],
            "phone": held["accountphone"],
            "email": held["accountemail"],
            "sent": held["createdon"],
        },
        # 3 - what the driver said about working there, for the employer to confirm or correct
        "employer": {
            "company": held["employer"],
            "contactname": held["contactname"],
            "email": held["email"],
            "phone": held["phone"],
            "address1": held["address1"],
            "city": held["city"],
            "state": held["state"],
            "zip": held["zip"],
            "employedfrom": held["employedfrom"],
            "employedthrough": held["employedthrough"],
        },
    }


# Every answer on the form is three-valued or four, never a checkbox. "No" and "no records
# available" are different answers: one is evidence, the other is a gap the carrier still owns.
YESNO = ("yes", "no", "na")
FOURWAY = ("yes", "no", "unknown", "na")
VERIFIED = ("yes", "no", "unable")
MODES = ("FMCSA", "FTA", "FRA", "FAA", "PHMSA", "USCG", "other")


class Reply(BaseModel):
    # 3 - the employment itself
    employmentverified: str                      # yes | no | unable
    position: str | None = None
    confirmedfrom: date | None = None
    confirmedthrough: date | None = None
    operatedcmv: str | None = None               # yes | no | unknown
    dotmode: str | None = None

    # 4 - §391.23(d), accidents recorded under §390.15
    accidentanswer: str | None = None            # no | yes | norecords
    accidents: list[dict] | None = None
    accidentsattached: bool = False

    # 5 - §391.23(e). Not asked of an FMCSA employer: that history comes from the Clearinghouse.
    alcohol04: str | None = None
    positivetest: str | None = None
    refusedtest: str | None = None
    otherviolation: str | None = None

    # 6 - SAP and return to duty, where any of the above was yes
    sapevaluated: str | None = None
    saptreatment: str | None = None
    rtdtest: str | None = None
    followupplan: str | None = None

    # 7 - the certification. Not proof of identity: it is the name that goes on the record, the way
    # a name goes on a faxed form.
    respondedby: str
    title: str | None = None
    company: str | None = None
    phone: str | None = None
    email: str | None = None
    signature: str | None = None
    fontkey: str | None = None
    note: str | None = None


@router.post("/{token}")
def answer_it(token: str, body: Reply, request: Request, conn: Connection = Depends(get_conn)):
    """Take the answer. It is recorded once and not editable afterwards from this link."""
    held = _open_inquiry(conn, token)
    who = (body.respondedby or "").strip().upper()
    if not who:
        raise HTTPException(400, "Please give your name")
    # The reply is a certification, and a certification nobody signed is a filled-in form.
    if not (body.signature or "").strip():
        raise HTTPException(400, "Sign the certification before sending it")
    if body.employmentverified not in VERIFIED:
        raise HTTPException(400, "Please say whether this person worked for you")
    # Every answer is checked against its own vocabulary rather than taken as given: a value this
    # code does not understand would read later as an answer nobody actually gave.
    def one_of(value, allowed, what):
        if value in (None, ""):
            return None
        if value not in allowed:
            raise HTTPException(400, f"Unrecognised answer for {what}")
        return value

    title = (body.title or "").strip().upper() or None
    company = (body.company or "").strip().upper() or None
    run(conn, """
        UPDATE employerinquiries
           SET respondedon = :now, respondedby = :who, certtitle = :title, certcompany = :co,
               certphone = :ph, certemail = :em, certsignature = :sig, certfontkey = :font, respondedip = :ip,
               employed = :worked, employmentverified = :ver, position = :pos,
               confirmedfrom = :from_, confirmedthrough = :to_, operatedcmv = :cmv, dotmode = :mode,
               accidentanswer = :acca, accidents = :acc, accidentsattached = :attached,
               alcohol04 = :a04, positivetest = :pos_t, refusedtest = :ref, otherviolation = :oth,
               sapevaluated = :sape, saptreatment = :sapt, rtdtest = :rtd, followupplan = :plan,
               responsenote = :note,
               -- A reply overtakes a good faith effort that was already filed: "nobody answered"
               -- stops being true. The effort stays as the record of what was done; this stamps
               -- the day it was overtaken, and the requirement goes back to needing a reading.
               effortsupersededon = CASE WHEN effortclosedon IS NOT NULL
                                         THEN :now ELSE effortsupersededon END,
               reviewedon = NULL, reviewedby = NULL
         WHERE recordid = :i
    """, now=utcnow(), who=who[:120], title=title, co=company,
        ph=(body.phone or None), em=(body.email or None),
        sig=(body.signature.strip().upper()[:160]),
        font=(body.fontkey if body.fontkey in view.SIGNATURE_FACES else "modern"),
        ip=client_ip(request),
        worked=1 if body.employmentverified == "yes" else 0,
        ver=body.employmentverified, pos=((body.position or "").strip().upper() or None),
        from_=body.confirmedfrom, to_=body.confirmedthrough,
        cmv=one_of(body.operatedcmv, FOURWAY, "whether they operated a CMV"),
        mode=one_of(body.dotmode, MODES, "the DOT mode"),
        acca=one_of(body.accidentanswer, ("no", "yes", "norecords"), "the accident question"),
        acc=json.dumps(body.accidents or []), attached=1 if body.accidentsattached else 0,
        a04=one_of(body.alcohol04, YESNO, "the alcohol question"),
        pos_t=one_of(body.positivetest, YESNO, "the positive test question"),
        ref=one_of(body.refusedtest, YESNO, "the refusal question"),
        oth=one_of(body.otherviolation, YESNO, "the other violation question"),
        sape=one_of(body.sapevaluated, FOURWAY, "the SAP evaluation question"),
        sapt=one_of(body.saptreatment, FOURWAY, "the SAP treatment question"),
        rtd=one_of(body.rtdtest, FOURWAY, "the return-to-duty question"),
        plan=one_of(body.followupplan, FOURWAY, "the follow-up testing question"),
        note=(body.note or None), i=held["recordid"])
    signed = who if not body.title else f"{who}, {body.title.strip()}"
    employers.record_attempt(conn, held["accountid"], held["recordid"], channel="email",
                             outcome="answered", sentto=signed[:255],
                             note="Answered online")
    # Rendered the moment they submit, so what is kept is the page they filled in and signed -
    # not one rebuilt later from columns that may since have been edited.
    sphiview.keep(conn, held["recordid"])
    events.record(conn, held["accountid"], "driver", None, "uploaded", "SAFETY_PERFORMANCE",
                  label=f'{held["employer"]} answered for '
                        f'{held["firstname"]} {held["lastname"]}'.strip())
    saved(conn)
    return {"ok": True, "accountname": held["accountname"], "employer": held["employer"]}
