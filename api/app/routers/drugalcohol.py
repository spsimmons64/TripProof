"""Drug and alcohol testing, and the bar, The rest of the drug and alcohol program, The supervisor's own acknowledgment - moved out of routers/vault.py, which grew too large to work in safely.

Shared helpers still live in vault and are imported from there."""
import hashlib
import io
import json
import logging
import re
import secrets
import zipfile
from datetime import date, datetime, time, timedelta
from html import escape

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import (accidents, annualreview, applicationview, backgroundchecks, billing,
                 invitations,
                 certn, documents, drivers,
                 eligibility, emails, exposure,
                 employers, events, gfeview, hos, i9, misreport, pdfform, randompool,
                 roadtest, roadtestview,
                 mvr as mvrs,
                 facts as factset, formats, images, mailer, phi, qualification, rules,
                 screening, screeningaccount, signatures, storage, tripcheck,
                 rates as rateset, vehicleclass, wheremap)
from app import dispatch, gateways, payerlines
from app.routers import signing, uploading
from app.activity import log
from app.config import settings
from app.db import get_conn, localnow, newid, row, rows, run, saved, utcnow
from app.evaluator import evaluate
from app.profiles import PROFILE_FIELDS, clean_profile
from app.routers import admin
from app.security import account_admin, client_ip, current_user, editor
from app.validity import credential_window
from app.routers.vault import (  # noqa: F401 - shared helpers
    RANDOM_RATES,
    _applicant,
    _driver_for_rules,
    _filed_here,
    _policy_context,
    _reevaluate_subject,
    _supervisor_blanks,
    _transit,
    _with_stamp,
)

router = APIRouter(prefix="/api", tags=["vault"])


@router.get("/drivers/{driverid}/testing")
def driver_testing(driverid: str, user: dict = Depends(current_user),
                   conn: Connection = Depends(get_conn)):
    """Every test on file, the bar in force if there is one, and what it would take to lift it."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    under = eligibility.program(driver, _transit(conn, acct))
    # Random, post-accident and reasonable suspicion are things that happen to somebody who is
    # employed and driving.
    hired = bool(driver.get("hiredon")) or driver["status"] in ("hired", "inactive")
    offer = ["preemployment"]
    if hired:
        offer += ["random", "postaccident", "reasonablesuspicion"]
    # A return-to-duty test is the last step of a process somebody is actually in. Offering it to a
    # driver with no violation invites a test that answers nothing - 49 CFR 40.305 is about coming
    # back from a prohibition, and there is nothing to come back from.
    #
    # Nor is it the last step until the steps before it are done. Under Part 40 the test lifts the
    # bar only once a SAP has evaluated the driver and recorded that they completed what was
    # prescribed, so a collection taken before that changes nothing. Offering it anyway is how the
    # office came to file a negative return-to-duty test, watch the driver stay prohibited, and
    # have nothing on screen to say why. It is offered when it would mean something, and until
    # then the prohibition itself says what is owed first.
    if held and (held.get("sapcompliedon") or (held.get("program") or "dot") != "dot"):
        offer.append("returntoduty")
    # Follow-up testing exists because a SAP wrote a plan. No plan, no follow-up tests.
    if any(h.get("followuptests") for h in eligibility.history(conn, acct, driverid)):
        offer.append("followup")
    return {"covered": eligibility.covered(driver),
            # What a bar still owes, which is not only the way back: the SAP information is owed to
            # an applicant who will never work here, and the hiring decision is the company's own.
            "owed": eligibility.owed(held), "decisions": eligibility.DECISIONS,
            "program": under, "programs": eligibility.PROGRAMMES,
            "returntoduty": eligibility.RETURN_TO_DUTY.get(under),
            # Every reason, so a test already on file reads by its name whatever the driver's
            # standing is now, and the shorter list of what may be filed today.
            "results": eligibility.RESULTS, "reasons": eligibility.REASONS, "offer": offer,
            "prohibited": held, "history": eligibility.history(conn, acct, driverid),
            "tests": eligibility.tests(conn, acct, driverid),
            "preemployment": eligibility.preemployment_state(conn, acct, driverid)}


class WithdrawTestIn(BaseModel):
    reason: str


@router.post("/drivers/{driverid}/testing/tests/{testid}/withdraw")
def withdraw_drug_test(driverid: str, testid: str, body: WithdrawTestIn, request: Request,
                       user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back a test filed on the wrong driver, and undo everything it did.

    A reason is required and goes on the record. The correction is the kind of thing an auditor
    reads closely - a positive that leaves a file wants an explanation beside it - so there is
    nowhere in this to remove one silently."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (body.reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this test is being withdrawn")
    driver = _driver_for_rules(conn, acct, driverid)
    try:
        out = eligibility.withdraw(conn, acct, driverid, testid, reason=why,
                                   by=user["recordid"])
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    # Taking the bar off may put this driver back in the pool's way, and putting somebody back
    # on safety-sensitive work is not a decision this makes quietly - so it is only ever
    # reported, never done.
    out["poolnote"] = (None if randompool.is_member(conn, acct, driverid)
                       else "This driver is not in the random testing pool. If the bar was the "
                            "reason they came out, put them back from their own requirements.")
    log(conn, user, "test-withdrawn", "driver", driverid,
        {"testid": testid, "reason": why, "undone": out["undone"]}, ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "undone": out["undone"], "poolnote": out["poolnote"],
            "driver": f'{driver["firstname"]} {driver["lastname"]}'.strip()}


@router.get("/drivers/{driverid}/accidents")
def driver_accidents(driverid: str, user: dict = Depends(current_user),
                     conn: Connection = Depends(get_conn)):
    """The accident register for this driver, and for each one whether 382.303 owed a test."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"accidents": accidents.for_driver(conn, acct, driverid),
            "windows": {"alcohol": 8, "drug": 32}}


@router.post("/drivers/{driverid}/accidents/{recordid}/withdraw")
def withdraw_accident(driverid: str, recordid: str, body: WithdrawTestIn, request: Request,
                      user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Take back an accident recorded against the wrong driver, with the reason kept.

    49 CFR 390.15(b) asks the carrier to keep the register for three years, so the row stays and
    is marked - an accident that vanishes out of a register is the one thing nobody can be shown
    an explanation for."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    why = (body.reason or "").strip()
    if len(why) < 3:
        raise HTTPException(400, "Say why this accident is being withdrawn")
    try:
        out = accidents.withdraw(conn, acct, driverid, recordid, reason=why,
                                 by=user["recordid"])
    except ValueError as e:
        raise HTTPException(404, str(e)) from e
    log(conn, user, "accident-withdrawn", "driver", driverid,
        {"recordid": recordid, "reason": why, "undone": out["undone"]}, ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "undone": out["undone"]}


@router.get("/accidents")
def company_accident_register(user: dict = Depends(current_user),
                              conn: Connection = Depends(get_conn)):
    """The register itself - 49 CFR 390.15(b) - across every driver.

    The per-driver view lives inside post-accident testing, because 382.303 is the reason to
    ask a driver's accidents. The REGISTER is a different thing addressed to the carrier, and
    it is one list: an auditor asking to see it is not asking to be walked through the roster
    one driver at a time."""
    acct = user["accountid"]
    kept = rows(conn, """
        SELECT a.recordid, a.driverid, a.occurredon, a.location, a.fatalities, a.injuries,
               a.hazmatreleased, a.note,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS driver
        FROM driveraccidents a LEFT JOIN drivers d ON d.recordid = a.driverid
        WHERE a.accountid = :a AND a.withdrawn IS NULL
        ORDER BY a.occurredon DESC, a.createdon DESC
    """, a=acct)
    # The particulars 390.15(b)(1) names, so the screen can say which are missing on which row
    # rather than only that the register as a whole is short.
    for x in kept:
        x["missing"] = [w for w, ok in (
            ("date", x["occurredon"]), ("where", (x["location"] or "").strip()),
            ("driver", x["driver"]), ("injured", x["injuries"] is not None),
            ("killed", x["fatalities"] is not None),
            ("hazmat", x["hazmatreleased"] is not None)) if not ok]
    return {"accidents": kept,
            # Only drivers on the roster. An accident is something that happened to somebody
            # who drives for this company, and offering an applicant who has never been behind
            # one of its wheels invites the wrong name onto a federal register.
            "drivers": rows(conn, """
                SELECT recordid, TRIM(CONCAT(firstname, ' ', lastname)) AS name
                FROM drivers WHERE accountid = :a AND deleted IS NULL AND status = 'hired'
                ORDER BY lastname, firstname""", a=acct)}


@router.post("/drivers/{driverid}/accidents")
def add_accident(driverid: str, request: Request, body: dict,
                 user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Write one accident up. It is written before anybody knows whether a citation was issued -
    that is the normal case, not an incomplete record - so every 382.303 answer may be left
    unanswered and filled in later."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    when = (body.get("occurredon") or "").strip()
    if not when:
        raise HTTPException(400, "Say when the accident happened")
    rid = accidents.record(
        conn, acct, driverid, occurredon=when.replace("T", " ")[:19],
        location=(body.get("location") or None), fatalities=body.get("fatalities"),
        injuries=body.get("injuries"), hazmatreleased=body.get("hazmatreleased"),
        injurytreatedaway=body.get("injurytreatedaway"), towaway=body.get("towaway"),
        cited=body.get("cited"), citedon=(body.get("citedon") or None),
        nottested=(body.get("nottested") or None), note=(body.get("note") or None),
        enteredby=user["recordid"], atfault=body.get("atfault"))
    log(conn, user, "accident", "driver", driverid, {"occurredon": when}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid}


class MovingViolationIn(BaseModel):
    occurredon: date
    violation: str
    convictedon: date | None = None
    atfault: bool | None = None
    onnemt: bool = True
    note: str | None = None


@router.get("/drivers/{driverid}/moving-violations")
def moving_violations(driverid: str, user: dict = Depends(current_user),
                      conn: Connection = Depends(get_conn)):
    """Moving violations recorded against this driver, and the at-fault accidents beside them -
    the two things DCH 914.2.5 counts together."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {
        "violations": rows(conn, """
            SELECT recordid, occurredon, violation, convictedon, atfault, onnemt, note
            FROM drivermovingviolations WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL
            ORDER BY occurredon DESC
        """, a=acct, d=driverid),
        "accidents": rows(conn, """
            SELECT recordid, occurredon, location, atfault FROM driveraccidents
            WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL ORDER BY occurredon DESC
        """, a=acct, d=driverid)}


@router.post("/drivers/{driverid}/moving-violations")
def add_moving_violation(driverid: str, body: MovingViolationIn, request: Request,
                         user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    if not body.violation.strip():
        raise HTTPException(400, "Say what the violation was")
    rid = newid()
    run(conn, """
        INSERT INTO drivermovingviolations (recordid, accountid, driverid, occurredon, violation,
                                            convictedon, atfault, onnemt, note, enteredby, createdon)
        VALUES (:id, :a, :d, :on, :v, :c, :af, :nemt, :n, :u, :now)
    """, id=rid, a=acct, d=driverid, on=body.occurredon, v=body.violation.strip().upper()[:160],
        c=body.convictedon, af=None if body.atfault is None else int(body.atfault),
        nemt=int(body.onnemt), n=(body.note or "").strip().upper()[:512] or None,
        u=user["recordid"], now=utcnow())
    log(conn, user, "moving-violation", "driver", driverid, {"occurredon": str(body.occurredon)},
        ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"recordid": rid}


@router.post("/drivers/{driverid}/moving-violations/{recordid}/withdraw")
def withdraw_moving_violation(driverid: str, recordid: str, request: Request,
                              user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Recorded against the wrong driver, or never convicted. Withdrawn, never deleted."""
    n = run(conn, "UPDATE drivermovingviolations SET withdrawn = :now WHERE recordid = :r "
                  "AND driverid = :d AND accountid = :a AND withdrawn IS NULL",
            now=utcnow(), r=recordid, d=driverid, a=user["accountid"]).rowcount
    if not n:
        raise HTTPException(404, "No such violation")
    log(conn, user, "moving-violation-withdrawn", "driver", driverid, {"recordid": recordid},
        ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True}


class SecurementIncidentIn(BaseModel):
    occurredon: date
    confirmed: bool = False
    note: str | None = None


@router.get("/drivers/{driverid}/securement-incidents")
def securement_incidents(driverid: str, user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """Wheelchair securement failures recorded against this driver - DCH 907.16."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    return {"incidents": rows(conn, """
        SELECT recordid, occurredon, confirmed, note FROM driversecurementincidents
        WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL ORDER BY occurredon DESC
    """, a=acct, d=driverid)}


@router.post("/drivers/{driverid}/securement-incidents")
def add_securement_incident(driverid: str, body: SecurementIncidentIn, request: Request,
                            user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    rid = newid()
    run(conn, """
        INSERT INTO driversecurementincidents (recordid, accountid, driverid, occurredon, confirmed,
                                               note, enteredby, createdon)
        VALUES (:id, :a, :d, :on, :c, :n, :u, :now)
    """, id=rid, a=acct, d=driverid, on=body.occurredon, c=int(body.confirmed),
        n=(body.note or "").strip().upper()[:512] or None, u=user["recordid"], now=utcnow())
    log(conn, user, "securement-incident", "driver", driverid,
        {"occurredon": str(body.occurredon), "confirmed": body.confirmed}, ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"recordid": rid}


@router.post("/drivers/{driverid}/securement-incidents/{recordid}/confirm")
def confirm_securement_incident(driverid: str, recordid: str, request: Request,
                                user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """A reported failure, now confirmed. Only a confirmed one removes the driver."""
    n = run(conn, "UPDATE driversecurementincidents SET confirmed = 1 WHERE recordid = :r "
                  "AND driverid = :d AND accountid = :a AND withdrawn IS NULL",
            r=recordid, d=driverid, a=user["accountid"]).rowcount
    if not n:
        raise HTTPException(404, "No such incident")
    log(conn, user, "securement-confirmed", "driver", driverid, {"recordid": recordid},
        ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/securement-incidents/{recordid}/withdraw")
def withdraw_securement_incident(driverid: str, recordid: str, request: Request,
                                 user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    n = run(conn, "UPDATE driversecurementincidents SET withdrawn = :now WHERE recordid = :r "
                  "AND driverid = :d AND accountid = :a AND withdrawn IS NULL",
            now=utcnow(), r=recordid, d=driverid, a=user["accountid"]).rowcount
    if not n:
        raise HTTPException(404, "No such incident")
    log(conn, user, "securement-withdrawn", "driver", driverid, {"recordid": recordid},
        ip=client_ip(request))
    _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/accidents/{recordid}")
def amend_accident(driverid: str, recordid: str, request: Request, body: dict,
                   user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Answer what was not known when it was written up - above all whether the driver was cited,
    which is the fact that decides whether a test was owed at all."""
    acct = user["accountid"]
    _applicant(conn, acct, driverid)
    held = accidents.one(conn, acct, recordid)
    if not held:
        raise HTTPException(404, "No such accident")
    accidents.amend(conn, acct, recordid, **body)
    log(conn, user, "accident-amended", "driver", driverid,
        {"recordid": recordid, "occurredon": str(held.get("occurredon") or "")},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.post("/drivers/{driverid}/testing/tests")
async def file_drug_test(
    driverid: str,
    request: Request,
    reason: str = Form(...),
    collectedon: date = Form(...),
    result: str = Form(...),
    # What the MIS report is counted off - 49 CFR 382.403. The form is two halves, controlled
    # substances and alcohol, so a test that does not say which cannot be reported at all.
    testtype: str | None = Form(None),
    substance: str | None = Form(None),
    bac: float | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(editor),
    conn: Connection = Depends(get_conn),
):
    """File a test result. What follows from it follows automatically: a positive or a refusal bars
    the driver, and a negative return-to-duty test lifts that bar once the SAP has signed the
    driver off."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    try:
        out = eligibility.file_test(conn, acct, driverid, driver, reason=reason,
                                    collectedon=collectedon, result=result, documentid=documentid,
                                    note=note, enteredby=user["recordid"],
                                    transit=_transit(conn, acct),
                                    testtype=testtype, substance=substance, bac=bac)
    except ValueError as e:
        raise HTTPException(400, str(e))
    _filed_here(conn, acct, driverid, "drugtests", out["recordid"], user["recordid"])
    log(conn, user, "drugtest", "driver", driverid,
        {"reason": reason, "result": result, "collectedon": str(collectedon)}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {**out, "evaluation": evaluation}


class ProhibitIn(BaseModel):
    source: str                              # clearinghouse | actualknowledge
    startedon: date
    note: str | None = None


@router.post("/drivers/{driverid}/testing/prohibit")
def prohibit_driver(driverid: str, body: ProhibitIn, request: Request,
                    user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Bar a driver without a test of our own - a Clearinghouse query that came back prohibited, or
    actual knowledge of a violation. Both bar the driver exactly as a positive test does."""
    acct = user["accountid"]
    driver = _driver_for_rules(conn, acct, driverid)
    if body.source not in ("clearinghouse", "actualknowledge"):
        raise HTTPException(400, "Say where this came from")
    if not eligibility.covered(driver):
        raise HTTPException(409, "Part 382 does not reach this driver")
    pid = eligibility.prohibit(conn, acct, driverid, source=body.source,
                               reason=eligibility.SOURCES[body.source], startedon=body.startedon,
                               note=body.note, enteredby=user["recordid"])
    if not pid:
        raise HTTPException(409, "This driver is already prohibited")
    log(conn, user, "prohibit", "driver", driverid, {"source": body.source}, ip=client_ip(request))
    evaluation = _reevaluate_subject(conn, user, "driver", driverid)
    saved(conn)
    return {"ok": True, "evaluation": evaluation}


@router.post("/drivers/{driverid}/testing/decision")
async def employment_decision(driverid: str, request: Request,
                              decision: str | None = Form(None),
                              sapinfogivenon: date | None = Form(None),
                              file: UploadFile | None = File(None),
                              user: dict = Depends(editor),
                              conn: Connection = Depends(get_conn)):
    """The employment decision after a violation, and the SAP information that is owed either way.

    These are deliberately one endpoint, because they are the two halves of the same moment and the
    second one is the one that gets forgotten. Neither touches the bar: DOT decides what the person
    may do, and nothing recorded here changes that.

    The list of SAPs is kept, not merely dated - 40.287 asks for the list to be given, and a date
    with nothing behind it is the employer's word for it."""
    acct = user["accountid"]
    _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    if not held:
        raise HTTPException(404, "This driver is not prohibited")
    decision = (decision or "").strip().lower() or None
    if decision and decision not in eligibility.DECISIONS:
        raise HTTPException(400, "Unknown employment decision")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # A list on file says it was given, so the date follows the document where none was typed.
    if documentid and not sapinfogivenon:
        sapinfogivenon = localnow(user["timezone"]).date()
    run(conn, """
        UPDATE driverprohibitions
           SET decision = COALESCE(:dec, decision),
               decidedon = CASE WHEN :dec IS NULL THEN decidedon ELSE CURDATE() END,
               decidedby = CASE WHEN :dec IS NULL THEN decidedby ELSE :u END,
               sapinfogivenon = COALESCE(:given, sapinfogivenon),
               sapinfogivenby = CASE WHEN :given IS NULL THEN sapinfogivenby ELSE :u END,
               sapinfodocumentid = COALESCE(:doc, sapinfodocumentid)
         WHERE recordid = :id AND accountid = :a
    """, dec=decision, given=sapinfogivenon, doc=documentid, u=user["recordid"],
        id=held["recordid"], a=acct)
    log(conn, user, "employment-decision", "driver", driverid,
        {"decision": decision, "sapinfogivenon": str(sapinfogivenon) if sapinfogivenon else None},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.put("/drivers/{driverid}/testing/prohibition")
async def update_prohibition(driverid: str, request: Request,
                             sapname: str | None = Form(None),
                             sapevaluatedon: date | None = Form(None),
                             sapcompliedon: date | None = Form(None),
                             followuptests: int | None = Form(None),
                             followupuntil: date | None = Form(None),
                             note: str | None = Form(None),
                             file: UploadFile | None = File(None),
                             user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """The return-to-duty process as it goes along: who the SAP is, when they evaluated the driver,
    when the driver completed what was prescribed, and the follow-up testing plan that will outlive
    the prohibition. None of this lifts the bar - only a negative return-to-duty test does."""
    acct = user["accountid"]
    _driver_for_rules(conn, acct, driverid)
    held = eligibility.standing(conn, acct, driverid)
    if not held:
        raise HTTPException(404, "This driver is not prohibited")
    if sapcompliedon and not (sapevaluatedon or held["sapevaluatedon"]):
        raise HTTPException(400, "Record the evaluation before the driver's compliance with it")
    # A date with nothing behind it is somebody's word for it, so the determination itself is kept.
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    run(conn, """
        UPDATE driverprohibitions SET sapname = COALESCE(:n, sapname),
               sapevaluatedon = COALESCE(:ev, sapevaluatedon),
               sapcompliedon = COALESCE(:co, sapcompliedon),
               followuptests = COALESCE(:ft, followuptests),
               followupuntil = COALESCE(:fu, followupuntil),
               documentid = COALESCE(:doc, documentid),
               note = COALESCE(:note, note)
        WHERE recordid = :id
    """, n=sapname, ev=sapevaluatedon, co=sapcompliedon, ft=followuptests,
        fu=followupuntil, doc=documentid, note=note, id=held["recordid"])
    log(conn, user, "rtd", "driver", driverid,
        {"sapname": sapname, "sapevaluatedon": str(sapevaluatedon or ""),
         "sapcompliedon": str(sapcompliedon or "")}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


# ------------------------------------------------------------------------------------------------
# The rest of the drug and alcohol program: trained supervisors, and the random draw
# ------------------------------------------------------------------------------------------------

# 49 CFR 382.603: at least sixty minutes on each, for every person who may determine reasonable
# suspicion. Held here rather than in the rule row because it is the number the screen checks
# against as somebody types.
TRAINING_MINUTES = 60
TEST_TYPES = {"drug": "Controlled substances", "alcohol": "Alcohol"}


@router.get("/company/supervisor-training")
def supervisor_training(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Who may determine reasonable suspicion here, and whether each of them is trained for it."""
    acct = user["accountid"]
    return {
        "minutes": TRAINING_MINUTES,
        # Everyone who may call a reasonable suspicion test, and whether they have signed their
        # own training record. The signature is the evidence - the durations are on the face of
        # the record they signed - so nothing here asks the office to type minutes in for
        # somebody else.
        "supervisors": rows(conn, """
            SELECT u.recordid AS userid, u.name, u.email, r.recordid AS roleid, r.since,
                   d.recordid AS signatureid, d.signedon, s.typedname
            FROM companyroles r
              JOIN users u ON u.recordid = r.userid
              LEFT JOIN documentsignatures d
                ON d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
               AND d.doctype = 'SUPERVISOR_TRAINING_RECORD'
              LEFT JOIN signatures s ON s.recordid = d.signatureid
            WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
              AND u.deleted IS NULL
            ORDER BY u.name
        """, a=acct),
    }


@router.get("/company/random-selections")
def random_selections(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """The draws made this year, against the rates FMCSA sets and the pool they were drawn from."""
    acct = user["accountid"]
    year = localnow(user["timezone"]).date().year
    drawn = rows(conn, """
        SELECT s.recordid, s.drawnon, s.testtype, s.poolsize, s.selected, s.performedby,
               s.documentid, s.note, u.name AS addedbyname
        FROM randomselections s LEFT JOIN users u ON u.recordid = s.addedby
        WHERE s.accountid = :a AND s.deleted IS NULL
        ORDER BY s.drawnon DESC, s.added DESC
    """, a=acct)
    # Who came out, and what happened to each of them. The draw is the event; this is whether
    # it was followed through, which is the half an audit actually asks about.
    for d in drawn:
        d["drivers"] = randompool.chosen(conn, acct, d["recordid"])
        d["tested"] = sum(1 for x in d["drivers"] if x["testid"])
        d["excused"] = sum(1 for x in d["drivers"] if x["excusedon"] and not x["testid"])
        d["outstanding"] = len(d["drivers"]) - d["tested"] - d["excused"]
    # The pool, from the one definition of who is in it. This used to count drivers whose
    # operation is `cdl` or `cdlheavy` and never looked at whether anybody had been enrolled -
    # a second pool, disagreeing with the one on each driver's own file.
    #
    # 382.305(b) sets the rate against the AVERAGE number of driver positions over the period,
    # not against the headcount today: a carrier running twenty drivers all year and one that
    # hired twenty in December owe very different numbers of tests, and a headcount cannot tell
    # them apart. Both are reported, because the average is what the rate is computed from and
    # the headcount is what somebody looking at the screen recognises.
    today = localnow(user["timezone"]).date()
    upto = min(today, date(year, 12, 31))
    pool = randompool.members_now(conn, acct)
    # Averaged over the period this carrier has HAD a pool, not from 1 January regardless. See
    # randompool.window: twelve days of one driver divided by a whole year reports a pool of
    # nothing, and a number nobody recognises is a number nobody trusts.
    since, upto = randompool.window(conn, acct, year, upto)
    mean = randompool.average(conn, acct, since, upto)
    thisyear = [d for d in drawn if d["drawnon"].year == year]
    done = {k: sum(d["selected"] or 0 for d in thisyear if d["testtype"] == k)
            for k in RANDOM_RATES}
    return {
        "year": year, "pool": pool, "average": round(mean, 1),
        "results": eligibility.RESULTS,
        "averagedsince": str(since) if since != date(year, 1, 1) else None,
        "rates": RANDOM_RATES, "types": TEST_TYPES,
        "selections": drawn,
        # What has been drawn this year against what the rate asks of a pool that size.
        "progress": {k: {"selected": done[k], "owed": randompool.owed(mean, RANDOM_RATES[k])}
                     for k in RANDOM_RATES},
    }


def _supervisor_record(conn: Connection, acct: str, userid: str | None,
                       claim: dict | None = None) -> tuple[dict, str]:
    """One supervisor's 382.603 record, and the filled HTML of the sheet for it.

    Keyed on the person, because the appointment is what creates the obligation - there is no
    record to point at until the supervisor makes one, and they make it by signing. With no
    user it answers the blank form: the company's own details filled in, because those are
    true of every copy, and every line about a person left ruled.

    `claim` is what the supervisor is stating as they sign, before it is stored. The form they
    read has to be the form they sign, so the same fill does both."""
    held = row(conn, """
        SELECT u.recordid AS userid, u.name AS supervisor, u.role AS supervisortitle,
               u.email AS supervisoremail, r.since AS designated,
               t.recordid, t.completedon, t.alcoholminutes, t.drugminutes, t.provider,
               t.note, t.documentid
        FROM users u
        LEFT JOIN companyroles r ON r.userid = u.recordid AND r.accountid = u.accountid
             AND r.role = 'supervisor' AND r.until IS NULL
        LEFT JOIN supervisortraining t ON t.userid = u.recordid AND t.accountid = u.accountid
             AND t.deleted IS NULL
        WHERE u.recordid = :u AND u.accountid = :a AND u.deleted IS NULL
        ORDER BY t.completedon DESC, t.added DESC LIMIT 1
    """, u=userid, a=acct) if userid else {}
    if userid and not held:
        raise HTTPException(404, "No such user")
    if claim:
        held = {**held, **claim}
    # The company's own wording if they have edited it, the published text otherwise - read the
    # same way every other policy is read. A company that rewrote this sheet signs the sheet it
    # rewrote, not the one we publish.
    mine = row(conn, "SELECT text FROM companypolicies WHERE accountid = :a AND code = :c",
               a=acct, c="SUPERVISOR_TRAINING_RECORD") or {}
    source = mine.get("text") or documents.company_policy("SUPERVISOR_TRAINING_RECORD")["text"]
    values = {**_policy_context(conn, acct, "SUPERVISOR_TRAINING_RECORD"),
              **_supervisor_blanks(held)}
    # The signing act hands its own signature in, because the copy that gets stored IS the copy
    # being signed - drawn a moment before the signature row exists, so there is nothing yet to
    # look up. Everything afterwards reads the stored copy, not this.
    #
    # Drawn in their own hand, the way every other signed document in here draws one: a web font
    # cannot be relied on wherever the sheet ends up, so the signature travels as a picture.
    drawn = claim.get("signature") if claim else None
    if drawn:
        values["supervisorsignature"] = (
            f'<img alt="{escape(drawn["typedname"])}" style="height:34px;vertical-align:middle"'
            f' src="{applicationview.signature_image(drawn["typedname"], drawn["fontkey"])}">')
        values["supervisorsignedon"] = f'{drawn["signedon"]:%m/%d/%Y}'
    return held, documents.fill_exact(source, values)


@router.get("/company/supervisor-training/{userid}/signed")
def signed_supervisor_record(userid: str, user: dict = Depends(current_user),
                             conn: Connection = Depends(get_conn)):
    """What this supervisor signed, as they signed it."""
    acct = user["accountid"]
    said = signatures.signed(conn, acct, userid, ownertype="user").get(
        "SUPERVISOR_TRAINING_RECORD")
    if not said:
        raise HTTPException(404, "They have not signed a training record")
    who = row(conn, "SELECT name FROM users WHERE recordid = :u AND accountid = :a",
              u=userid, a=acct) or {}
    return {"title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
            "who": who.get("name"), "html": _with_stamp(said["signedtext"], said),
            "signedon": str(said["signedon"]), "signedby": said["typedname"]}


# ------------------------------------------------------------------------------------------------
# The supervisor's own acknowledgment - 49 CFR 382.603.
#
# Somebody else recording that a supervisor was trained is not the supervisor saying they were.
# The person who will decide whether a driver is sent for a reasonable suspicion test signs
# their own record, and until they have, the training is on file as an assertion about them
# rather than by them.
# ------------------------------------------------------------------------------------------------

def _supervisor_owes(conn: Connection, acct: str, userid: str) -> bool:
    """Whether this user holds the supervisor appointment and has not signed for it.

    The appointment is what creates the obligation. There is nothing else to wait for: the
    office does not record the training first, because 382.603 is about the person who will
    decide whether a driver is sent for a test, and what they did is theirs to state."""
    return bool(row(conn, """
        SELECT 1 AS x FROM companyroles r
        WHERE r.accountid = :a AND r.userid = :u AND r.role = 'supervisor' AND r.until IS NULL
          AND NOT EXISTS (
            SELECT 1 FROM documentsignatures d
            WHERE d.accountid = r.accountid AND d.ownertype = 'user' AND d.ownerid = r.userid
              AND d.doctype = 'SUPERVISOR_TRAINING_RECORD')
        LIMIT 1
    """, a=acct, u=userid))


@router.get("/me/supervisor-record")
def my_supervisor_record(user: dict = Depends(current_user),
                         conn: Connection = Depends(get_conn)):
    """What this user is being asked to sign, and whether they already have."""
    acct = user["accountid"]
    held = signatures.signed(conn, acct, user["recordid"], ownertype="user")
    already = held.get("SUPERVISOR_TRAINING_RECORD")
    owed = (not user.get("platformrole")) and _supervisor_owes(conn, acct, user["recordid"])
    # Nothing to sign is an answer, and it has to SAY which answer. A dialog that opens on an
    # empty page because the person looking is not the person it is for is a dialog that looks
    # broken - which is exactly how it was read.
    if not owed and not already:
        who = rows(conn, """
            SELECT u.name FROM companyroles r JOIN users u ON u.recordid = r.userid
            WHERE r.accountid = :a AND r.role = 'supervisor' AND r.until IS NULL
              AND u.deleted IS NULL ORDER BY u.name
        """, a=acct)
        names = ", ".join(w["name"] for w in who)
        return {"owed": False, "signed": None, "html": None,
                "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
                "because": (
                    "You are signed in as TripProof staff. A supervisor signs their own "
                    f"training record - {names} must sign in and sign it." if user.get("platformrole") and names
                    else "You are signed in as TripProof staff, and nobody here holds the "
                         "supervisor appointment yet." if user.get("platformrole")
                    else f"You do not hold the supervisor appointment. {names} does - "
                         "it is theirs to sign." if names
                    else "Nobody holds the supervisor appointment, so there is no training "
                         "record to sign. Appoint somebody on Company Requirements first.")}
    body = None
    if owed:
        _, body = _supervisor_record(conn, acct, user["recordid"])
    return {
        "owed": owed,
        "html": body,
        "minutes": TRAINING_MINUTES,
        "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
        # The words that were signed, read back from the signature rather than re-rendered -
        # the record can change after it is signed, and the copy somebody put their name to
        # does not.
        "signed": ({"signedon": str(already["signedon"]), "typedname": already["typedname"],
                    "fontkey": already["fontkey"], "html": _with_stamp(already["signedtext"], already)}
                   if already else None),
    }


@router.get("/account/users/{userid}/supervisor-record")
def their_supervisor_record(userid: str, user: dict = Depends(account_admin),
                            conn: Connection = Depends(get_conn)):
    """Somebody else's signed training record, for the people who manage the roster.

    Read only, and only what was SIGNED. An admin may look at what a supervisor put their name
    to; nobody may sign it for them, so there is no unsigned copy offered here - that one is
    the supervisor's own to read and answer."""
    acct = user["accountid"]
    held = signatures.signed(conn, acct, userid, ownertype="user").get(
        "SUPERVISOR_TRAINING_RECORD")
    if not held:
        raise HTTPException(404, "They have not signed a training record")
    return {"owed": False, "html": None,
            "title": signatures.DOC_TYPES["SUPERVISOR_TRAINING_RECORD"],
            "signed": {"signedon": str(held["signedon"]), "typedname": held["typedname"],
                       "fontkey": held["fontkey"], "html": _with_stamp(held["signedtext"], held)}}


@router.post("/me/supervisor-record/sign")
async def sign_my_supervisor_record(
    request: Request,
    completedon: date = Form(...),
    alcoholminutes: int = Form(...),
    drugminutes: int = Form(...),
    provider: str | None = Form(None),
    note: str | None = Form(None),
    file: UploadFile | None = File(None),
    user: dict = Depends(current_user),
    conn: Connection = Depends(get_conn),
):
    """State the training and sign for it, in one act.

    Section 4 of the record and section 6 of it are the same statement: the supervisor says
    what they did and puts their name to it. Splitting them would put the particulars in
    somebody else's hands and leave the acknowledgment standing over an empty section."""
    acct = user["accountid"]
    # A launched session is us standing in their office, not us being them. 49 CFR 382.603 is
    # satisfied by the person who will decide whether a driver is sent for a test saying they
    # were trained - support staff cannot say it for them.
    if user.get("platformrole"):
        raise HTTPException(403, "TripProof staff cannot sign a customer's training record - "
                                 "the supervisor signs their own")
    if not _supervisor_owes(conn, acct, user["recordid"]):
        raise HTTPException(409, "You do not hold the supervisor appointment, or have already "
                                 "signed your training record.")
    sig = signatures.current(conn, acct, "user", user["recordid"])
    if not sig:
        raise HTTPException(409, "Set up your signature first, then sign this.")
    if completedon > localnow(user["timezone"]).date():
        raise HTTPException(400, "That date has not happened yet")
    # 382.603(b) sets the floor at sixty minutes each. A record stating less is a record that
    # says the training did not meet the section, so it is refused here rather than filed and
    # counted.
    if alcoholminutes < TRAINING_MINUTES or drugminutes < TRAINING_MINUTES:
        raise HTTPException(400, f"49 CFR 382.603 asks for at least {TRAINING_MINUTES} minutes "
                                 f"on alcohol misuse and {TRAINING_MINUTES} on controlled "
                                 f"substances.")
    documentid = None
    if file is not None and file.filename:
        data = await file.read()
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(413, "That file is larger than 20 MB")
        documentid = storage.keep(conn, acct, "documents", data, file.filename, file.content_type,
                                  user["recordid"], origin=storage.OFFICE)
    # Drawn before it is recorded, so the sheet carries the signature it was signed with and
    # the stamp under it agrees with the row in the table.
    when = utcnow()
    claim = {"completedon": completedon, "alcoholminutes": alcoholminutes,
             "drugminutes": drugminutes, "provider": (provider or "").strip()[:160] or None,
             "note": (note or "").strip()[:512] or None, "documentid": documentid,
             "signature": {"typedname": sig["typedname"], "fontkey": sig["fontkey"],
                           "signername": sig["signername"], "recordid": sig["recordid"],
                           "ip": client_ip(request), "signedon": when}}
    recordid = newid()
    run(conn, """
        INSERT INTO supervisortraining (recordid, accountid, userid, completedon, alcoholminutes,
                                        drugminutes, provider, documentid, note, addedby)
        VALUES (:id, :a, :u, :on, :am, :dm, :p, :doc, :n, :by)
    """, id=recordid, a=acct, u=user["recordid"], on=completedon, am=alcoholminutes,
        dm=drugminutes, p=claim["provider"], doc=documentid, n=claim["note"],
        by=user["recordid"])
    _, rendered = _supervisor_record(conn, acct, user["recordid"], claim)
    signatures.sign(conn, acct, sig["recordid"], "SUPERVISOR_TRAINING_RECORD",
                    user["recordid"], rendered, ownertype="user", signedon=when,
                    ip=client_ip(request), useragent=request.headers.get("user-agent"))
    log(conn, user, "supervisor-training-signed", "company", acct,
        {"training": recordid, "completedon": str(completedon)}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}
