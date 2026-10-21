###################################################################################################
# The company's operating profile: where it operates, how it engages drivers, and what has been
# determined about its vehicles. Also the payer lines - who it carries for, where, under which
# program and contract - which are kept from the Payers page and decide its programs.
#
# These are the facts the rules read to decide what a driver owes. They are records with dates, and
# every change to the profile is kept as a version - a qualification decided last month has to be
# explainable from the profile as it stood last month.
#
# Unknown is not exempt. Whatever has not been decided is listed as an open question, and the rules
# that depend on it say so instead of quietly not applying.
###################################################################################################
import json
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import payerlines
from app.activity import log
from app.db import get_conn, newid, row, rows, run, saved, utcnow
from app.security import account_admin, client_ip, current_user

router = APIRouter(prefix="/api/company/operating-profile", tags=["operating"])
manager = account_admin

PROGRAMS = {
    "privatepay": "Private Pay",
    "medicaid": "Medicaid NEMT",
    "medicareadvantage": "Medicare Advantage",
    "commercialinsurance": "Commercial Insurance",
    "workerscomp": "Workers' Compensation",
    "facility": "Facility Contracts",
    "dhscoordinated": "DHS Coordinated Transportation",
}
EMPLOYMENT = {"employee": "Employees (W-2)", "contractor": "Independent contractors (1099)",
              "mixed": "Both"}
DETERMINATION = {"covered": "Covered", "notcovered": "Not covered", "review": "Needs review"}
SERVICES = ("ambulatory", "wheelchair", "stretcher")
STATUSES = ("active", "planned", "ended")
# The programs each kind of payer can carry, the first being what a new line starts on. A broker
# administers a benefit - Medicaid, a Medicare Advantage plan's, a workers' compensation
# carrier's, a DHS program - and never a facility's; a Medicaid agency and a facility carry one.
CATEGORY_PROGRAMS = {
    "broker": ["medicaid", "medicareadvantage", "workerscomp", "dhscoordinated"],
    "medicaid": ["medicaid"],
    "commercial": ["commercialinsurance", "medicareadvantage", "workerscomp"],
    "flatcontract": ["facility"],
}
CATEGORY_PROGRAM = {k: v[0] for k, v in CATEGORY_PROGRAMS.items()}


def _open_questions(profile: dict, contracts: list[dict], vehicles: list[dict],
                    transit: list[dict]) -> list[str]:
    """What has not been decided. Each one leaves some rule unable to say whether it applies."""
    out = []
    if not profile.get("operatingstates"):
        out.append("Operating states have not been recorded.")
    if not profile.get("employmentmodel"):
        out.append("The employment model has not been recorded, so whether the I-9 and the W-4 "
                   "apply cannot be decided for drivers without their own classification.")
    elif profile["employmentmodel"] == "mixed":
        out.append("The employment model is mixed, so each driver needs their own classification "
                   "(Driver Information).")
    for t in transit:
        if t["determination"] in (None, "review"):
            out.append(f'The {t["name"]} ({t["citation"]}) determination is not settled, so the '
                       f'requirements that depend on it stay under review.')
    contracts = [c for c in contracts if c["payeractive"]]
    if not [c for c in contracts if c["status"] == "active" and not c.get("ended")]:
        out.append("No payer is recorded as active on the Payers page.")
    for c in contracts:
        # Private pay has no contract to read.
        if c["payerid"] and not c["reviewed"] and c["status"] != "ended" and not c.get("ended"):
            out.append(f'The {c["broker"]}{" " + c["state"] if c["state"] else ""} contract has not '
                       f'been reviewed for its driver requirements.')
    undecided = [v for v in vehicles if not v.get("fmcsa") or v["fmcsa"] == "review"]
    if undecided:
        out.append(f"{len(undecided)} vehicle{'' if len(undecided) == 1 else 's'} without an FMCSA "
                   f"coverage determination.")
    return out


def _profile(conn: Connection, acct: str) -> dict:
    return row(conn, """
        SELECT p.operatingstates, p.employmentmodel, p.fdot1490, p.compliancecontact,
               p.enforcetripcheck, p.updated, u.name AS updatedbyname
        FROM companyprofiles p LEFT JOIN users u ON u.recordid = p.updatedby
        WHERE p.accountid = :a
    """, a=acct) or {}


def _transit(conn: Connection, acct: str, profile: dict) -> list[dict]:
    """The transit safety programs that touch this company - federal ones always, and those of its
    home state and the states it operates in - with the company's determination of each."""
    home = (row(conn, "SELECT state FROM accounts WHERE recordid = :a", a=acct) or {}).get("state")
    states = {s for s in (profile.get("operatingstates") or "").split(",") if s} | {home, "US"}
    return [t for t in rows(conn, """
        SELECT p.code, p.state, p.name, p.authority, p.citation, p.description, p.vehicles,
               c.determination,
               c.determinedon, u.name AS determinedbyname
        FROM transitsafetyprograms p
        LEFT JOIN companytransitprograms c ON c.programcode = p.code AND c.accountid = :a
        LEFT JOIN users u ON u.recordid = c.determinedby
        WHERE p.active = 1 ORDER BY p.state = 'US' DESC, p.state, p.sortorder
    """, a=acct) if t["state"] in states]


class TransitIn(BaseModel):
    determination: str | None = None


@router.put("/transit/{code}")
def determine_transit(code: str, body: TransitIn, request: Request, user: dict = Depends(manager),
                      conn: Connection = Depends(get_conn)):
    """Whether this company's operation is covered by one transit safety program."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM transitsafetyprograms WHERE code = :c AND active = 1", c=code):
        raise HTTPException(404, "No such program")
    if body.determination and body.determination not in DETERMINATION:
        raise HTTPException(400, "Unknown determination")
    if body.determination:
        run(conn, """
            INSERT INTO companytransitprograms (accountid, programcode, determination, determinedon,
                                                determinedby)
            VALUES (:a, :c, :d, :now, :u)
            ON DUPLICATE KEY UPDATE determination = :d, determinedon = :now, determinedby = :u
        """, a=acct, c=code, d=body.determination, now=utcnow(), u=user["recordid"])
    else:
        run(conn, "DELETE FROM companytransitprograms WHERE accountid = :a AND programcode = :c",
            a=acct, c=code)
    # Kept with the profile's history, as every other change to what the company does is.
    run(conn, """
        INSERT INTO companyprofilehistory (recordid, accountid, snapshot, savedon, savedby)
        VALUES (:id, :a, :snap, :now, :u)
    """, id=newid(), a=acct, now=utcnow(), u=user["recordid"],
        snap=json.dumps({"transit": {code: body.determination}}))
    log(conn, user, "update", "transitprogram", code, {"determination": body.determination},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


def lines(conn: Connection, acct: str) -> list[dict]:
    """Who the company carries for: one line per payer and state, with its program, dates and
    contract, and what that contract asks of drivers. Private pay is a line with no payer."""
    today = date.today()
    out = rows(conn, f"""
        SELECT c.recordid, c.broker, c.payerid, c.state, c.contractref, c.program, c.status,
               c.scheduleid, s.name AS schedulename,
               {payerlines.live("c")} AS payeractive,
               c.services, c.requiresapproval, c.effectivefrom, c.effectiveto, c.reviewed,
               c.reviewedon, c.note, u.name AS reviewedbyname
        FROM companycontracts c LEFT JOIN users u ON u.recordid = c.reviewedby
        LEFT JOIN payerschedules s ON s.recordid = c.scheduleid
        WHERE c.accountid = :a ORDER BY c.broker, c.state
    """, a=acct)
    asked = rows(conn, """
        SELECT r.recordid, r.contractid, r.qualificationcode, q.name AS qualification,
               r.renewaldays, r.clause
        FROM contractrequirements r LEFT JOIN qualificationcatalog q ON q.code = r.qualificationcode
        WHERE r.accountid = :a AND r.endedon IS NULL ORDER BY q.sortorder
    """, a=acct)
    for c in out:
        c["ended"] = bool(c["effectiveto"] and c["effectiveto"] < today)
        c["requirements"] = [r for r in asked if r["contractid"] == c["recordid"]]
    return out


@router.get("")
def operating_profile(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    profile = _profile(conn, acct)
    contracts = lines(conn, acct)
    vehicles = rows(conn, """
        SELECT v.recordid, v.externalid, v.make, v.model, v.seats, v.gvwr, v.lift,
               a.fmcsa, a.note, a.assessedon
        FROM vehicles v LEFT JOIN vehicleassessments a ON a.vehicleid = v.recordid
        WHERE v.accountid = :a AND v.deleted IS NULL AND v.stub = 0
        ORDER BY v.externalid
    """, a=acct)
    history = rows(conn, """
        SELECT h.savedon, h.snapshot, u.name AS savedbyname FROM companyprofilehistory h
        LEFT JOIN users u ON u.recordid = h.savedby
        WHERE h.accountid = :a ORDER BY h.savedon DESC
    """, a=acct)
    for h in history:
        h["snapshot"] = json.loads(h["snapshot"]) if isinstance(h["snapshot"], str) else h["snapshot"]
    users = rows(conn, "SELECT recordid, name FROM users WHERE accountid = :a AND deleted IS NULL "
                       "ORDER BY name", a=acct)
    # What the trip check would have refused had it been on - the comparison that has to come out
    # clean before enforcement is switched on.
    shadow = rows(conn, """
        SELECT e.recordid, e.evaluatedon, e.evaluatedfor, e.decision, e.program, e.blockers,
               e.warnings, d.firstname, d.lastname, e.legid
        FROM tripeligibility e LEFT JOIN drivers d ON d.recordid = e.driverid
        WHERE e.accountid = :a AND e.shadow = 1 AND e.decision <> 'eligible'
          AND e.evaluatedon >= UTC_TIMESTAMP() - INTERVAL 30 DAY
        ORDER BY e.evaluatedon DESC LIMIT 100
    """, a=acct)
    for e in shadow:
        e["blockers"] = json.loads(e["blockers"] or "[]")
        e["warnings"] = json.loads(e["warnings"] or "[]")
    transit = _transit(conn, acct, profile)
    # Each vehicle's determination under every program that governs vehicles and touches the
    # company - one column each, so a Georgia company is not asked Florida's question.
    held = {}
    for r in rows(conn, "SELECT vehicleid, programcode, determination FROM vehicletransitprograms "
                        "WHERE accountid = :a", a=acct):
        held.setdefault(r["vehicleid"], {})[r["programcode"]] = r["determination"]
    for v in vehicles:
        v["transit"] = held.get(v["recordid"], {})
    return {"profile": profile, "vehicles": vehicles, "history": history, "users": users,
            "shadow": shadow,
            "open": _open_questions(profile, contracts, vehicles, transit),
            "transit": transit,
            "vehicleprograms": [t for t in transit if t["vehicles"]],
            "choices": {"programs": PROGRAMS, "employment": EMPLOYMENT,
                        "determination": DETERMINATION, "services": list(SERVICES)}}


class ProfileIn(BaseModel):
    operatingstates: list[str] = []
    employmentmodel: str | None = None
    fdot1490: str | None = None
    compliancecontact: str | None = None
    enforcetripcheck: bool = False


@router.put("")
def save_profile(body: ProfileIn, request: Request, user: dict = Depends(manager),
                 conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if body.employmentmodel and body.employmentmodel not in EMPLOYMENT:
        raise HTTPException(400, "Unknown employment model")
    if body.fdot1490 and body.fdot1490 not in DETERMINATION:
        raise HTTPException(400, "Unknown Chapter 14-90 determination")
    states = ",".join(sorted({s.strip().upper()[:2] for s in body.operatingstates if s.strip()}))
    run(conn, """
        INSERT INTO companyprofiles (accountid, operatingstates, employmentmodel, fdot1490,
                                     compliancecontact, enforcetripcheck, updated, updatedby)
        VALUES (:a, :s, :m, :f, :c, :e, :now, :u)
        ON DUPLICATE KEY UPDATE operatingstates = :s, employmentmodel = :m, fdot1490 = :f,
                                compliancecontact = :c, enforcetripcheck = :e, updated = :now,
                                updatedby = :u
    """, a=acct, s=states or None, m=body.employmentmodel or None, f=body.fdot1490 or None,
        c=body.compliancecontact or None, e=int(body.enforcetripcheck), now=utcnow(),
        u=user["recordid"])
    # Every version kept. A determination made last month is read against last month's profile.
    run(conn, """
        INSERT INTO companyprofilehistory (recordid, accountid, snapshot, savedon, savedby)
        VALUES (:id, :a, :snap, :now, :u)
    """, id=newid(), a=acct, now=utcnow(), u=user["recordid"], snap=json.dumps({
        "operatingstates": states, "employmentmodel": body.employmentmodel,
        "fdot1490": body.fdot1490, "compliancecontact": body.compliancecontact,
        "enforcetripcheck": body.enforcetripcheck}))
    log(conn, user, "update", "operatingprofile", acct, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class ContractIn(BaseModel):
    state: str | None = None
    contractref: str | None = None
    program: str | None = None
    status: str = "active"
    # The fee schedule this payer pays under in this state.
    scheduleid: str | None = None
    services: list[str] = []
    effectivefrom: date | None = None
    effectiveto: date | None = None
    reviewed: bool = False
    note: str | None = None
    payerid: str | None = None
    requiresapproval: bool = False


def _contract_values(conn: Connection, acct: str, body: ContractIn) -> dict:
    """A line names a payer, or is private pay and names none. Its program is the payer's kind
    unless somebody chose another."""
    if body.program and body.program not in PROGRAMS:
        raise HTTPException(400, "Unknown program")
    if body.status not in STATUSES:
        raise HTTPException(400, "Unknown status")
    if body.payerid:
        payer = row(conn, "SELECT name, category FROM payers WHERE recordid = :p "
                          "AND (accountid IS NULL OR accountid = :a)", p=body.payerid, a=acct)
        if not payer:
            raise HTTPException(404, "No such payer")
        allowed = CATEGORY_PROGRAMS.get(payer["category"], list(PROGRAMS))
        if body.program and body.program not in allowed:
            raise HTTPException(400, "That program is not one this kind of payer carries")
        name, program = payer["name"], body.program or allowed[0]
    else:
        name, program = "PRIVATE PAY", "privatepay"
    if not body.state:
        raise HTTPException(400, "Choose the state")
    if body.scheduleid:
        # A state paid differently: a schedule of the payer's own type, and active.
        from app import rates
        held = row(conn, "SELECT privatepay, payerkinds, active FROM payerschedules "
                         "WHERE recordid = :s AND accountid = :a", s=body.scheduleid, a=acct)
        if not held or not held["active"]:
            raise HTTPException(404, "No such active fee schedule")
        kind = "private" if not body.payerid else row(
            conn, "SELECT category FROM payers WHERE recordid = :p", p=body.payerid)["category"]
        if rates.kind_of(held) != kind:
            raise HTTPException(400, "That fee schedule is for a different payer type")
    return {"b": name.strip().upper()[:64], "s": body.state.upper()[:2], "st": body.status,
            "r": (body.contractref or "").strip().upper()[:64] or None, "p": program,
            "sc": body.scheduleid or None,
            "sv": ",".join(x for x in body.services if x in SERVICES) or None,
            "f": body.effectivefrom, "t": body.effectiveto,
            "n": (body.note or "").strip().upper()[:512] or None,
            "py": body.payerid or None, "ra": int(body.requiresapproval)}


@router.post("/contracts")
def add_contract(body: ContractIn, request: Request, user: dict = Depends(manager),
                 conn: Connection = Depends(get_conn)):
    v = _contract_values(conn, user["accountid"], body)
    cid = newid()
    run(conn, """
        INSERT INTO companycontracts (recordid, accountid, broker, payerid, state, contractref,
                                      program, status, scheduleid, services, requiresapproval,
                                      effectivefrom, effectiveto, reviewed, reviewedby, reviewedon,
                                      note, added, addedby)
        VALUES (:id, :a, :b, :py, :s, :r, :p, :st, :sc, :sv, :ra, :f, :t, :rev, :rby, :ron, :n,
                :now, :u)
    """, id=cid, a=user["accountid"], rev=int(body.reviewed),
        rby=user["recordid"] if body.reviewed else None, ron=utcnow() if body.reviewed else None,
        now=utcnow(), u=user["recordid"], **v)
    log(conn, user, "create", "companycontract", cid, {"broker": v["b"]}, ip=client_ip(request))
    saved(conn)
    return {"recordid": cid}


@router.put("/contracts/{contractid}")
def update_contract(contractid: str, body: ContractIn, request: Request,
                    user: dict = Depends(manager), conn: Connection = Depends(get_conn)):
    v = _contract_values(conn, user["accountid"], body)
    held = row(conn, "SELECT reviewed FROM companycontracts WHERE recordid = :id AND accountid = :a",
               id=contractid, a=user["accountid"])
    if not held:
        raise HTTPException(404, "No such contract")
    # The reviewer and date are stamped when it becomes reviewed, and kept while it stays so.
    newly = body.reviewed and not held["reviewed"]
    run(conn, """
        UPDATE companycontracts SET broker = :b, payerid = :py, state = :s, contractref = :r,
               program = :p, status = :st, scheduleid = :sc, services = :sv, requiresapproval = :ra, effectivefrom = :f,
               effectiveto = :t, note = :n, reviewed = :rev,
               reviewedby = CASE WHEN :rev = 0 THEN NULL WHEN :newly = 1 THEN :u ELSE reviewedby END,
               reviewedon = CASE WHEN :rev = 0 THEN NULL WHEN :newly = 1 THEN :now ELSE reviewedon END
        WHERE recordid = :id AND accountid = :a
    """, id=contractid, a=user["accountid"], rev=int(body.reviewed), newly=int(newly),
        u=user["recordid"], now=utcnow(), **v)
    log(conn, user, "update", "companycontract", contractid, {"reviewed": body.reviewed},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.delete("/contracts/{contractid}")
def remove_contract(contractid: str, request: Request, user: dict = Depends(manager),
                    conn: Connection = Depends(get_conn)):
    """A line added by mistake. Once a driver has been approved for it or it has asked something
    of drivers it is ended instead, so what it asked stays known."""
    acct = user["accountid"]
    if row(conn, """
        SELECT 1 AS x FROM driverauthorizations WHERE contractid = :c AND accountid = :a
        UNION ALL SELECT 1 FROM contractrequirements WHERE contractid = :c AND accountid = :a
        LIMIT 1
    """, c=contractid, a=acct):
        raise HTTPException(409, "Drivers have been approved for this line or it lists driver "
                                 "requirements. Set it to Ended instead.")
    if not run(conn, "DELETE FROM companycontracts WHERE recordid = :c AND accountid = :a",
               c=contractid, a=acct).rowcount:
        raise HTTPException(404, "No such line")
    log(conn, user, "delete", "companycontract", contractid, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class AssessmentIn(BaseModel):
    fmcsa: str | None = None
    note: str | None = None


@router.put("/vehicles/{vehicleid}")
def assess_vehicle(vehicleid: str, body: AssessmentIn, request: Request,
                   user: dict = Depends(manager), conn: Connection = Depends(get_conn)):
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM vehicles WHERE recordid = :v AND accountid = :a "
                     "AND deleted IS NULL", v=vehicleid, a=acct):
        raise HTTPException(404, "No such vehicle")
    if body.fmcsa and body.fmcsa not in DETERMINATION:
        raise HTTPException(400, "Unknown determination")
    run(conn, """
        INSERT INTO vehicleassessments (vehicleid, accountid, fmcsa, note, assessedby, assessedon)
        VALUES (:v, :a, :f, :n, :u, :now)
        ON DUPLICATE KEY UPDATE fmcsa = :f, note = :n, assessedby = :u, assessedon = :now
    """, v=vehicleid, a=acct, f=body.fmcsa or None,
        n=(body.note or "").strip().upper()[:512] or None, u=user["recordid"], now=utcnow())
    log(conn, user, "update", "vehicleassessment", vehicleid, {"fmcsa": body.fmcsa},
        ip=client_ip(request))
    saved(conn)
    return {"ok": True}


@router.put("/vehicles/{vehicleid}/transit/{code}")
def determine_vehicle_transit(vehicleid: str, code: str, body: TransitIn, request: Request,
                              user: dict = Depends(manager), conn: Connection = Depends(get_conn)):
    """Whether one vehicle operates under one transit safety program. Unset is unknown."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM vehicles WHERE recordid = :v AND accountid = :a "
                     "AND deleted IS NULL", v=vehicleid, a=acct):
        raise HTTPException(404, "No such vehicle")
    if not row(conn, "SELECT 1 AS x FROM transitsafetyprograms WHERE code = :c AND active = 1 "
                     "AND vehicles = 1", c=code):
        raise HTTPException(404, "No such program")
    if body.determination and body.determination not in DETERMINATION:
        raise HTTPException(400, "Unknown determination")
    if body.determination:
        run(conn, """
            INSERT INTO vehicletransitprograms (accountid, vehicleid, programcode, determination,
                                                determinedon, determinedby)
            VALUES (:a, :v, :c, :d, :now, :u)
            ON DUPLICATE KEY UPDATE determination = :d, determinedon = :now, determinedby = :u
        """, a=acct, v=vehicleid, c=code, d=body.determination, now=utcnow(), u=user["recordid"])
    else:
        run(conn, "DELETE FROM vehicletransitprograms WHERE vehicleid = :v AND programcode = :c "
                  "AND accountid = :a", v=vehicleid, c=code, a=acct)
    log(conn, user, "update", "vehicletransitprogram", vehicleid,
        {"program": code, "determination": body.determination}, ip=client_ip(request))
    saved(conn)
    return {"ok": True}


class ContractRequirementIn(BaseModel):
    qualificationcode: str
    renewaldays: int | None = None
    clause: str | None = None


@router.post("/contracts/{contractid}/requirements")
def add_contract_requirement(contractid: str, body: ContractRequirementIn, request: Request,
                             user: dict = Depends(manager), conn: Connection = Depends(get_conn)):
    """One thing the contract asks of its drivers, pointing at a catalog qualification."""
    acct = user["accountid"]
    if not row(conn, "SELECT 1 AS x FROM companycontracts WHERE recordid = :c AND accountid = :a",
               c=contractid, a=acct):
        raise HTTPException(404, "No such contract")
    if not row(conn, "SELECT 1 AS x FROM qualificationcatalog WHERE code = :q",
               q=body.qualificationcode):
        raise HTTPException(400, "Unknown qualification")
    if body.renewaldays is not None and not 1 <= body.renewaldays <= 3650:
        raise HTTPException(400, "Renewal is a number of days between 1 and 3650")
    rid = newid()
    run(conn, """
        INSERT INTO contractrequirements (recordid, accountid, contractid, qualificationcode,
                                          renewaldays, clause, added, addedby)
        VALUES (:id, :a, :c, :q, :d, :cl, :now, :u)
    """, id=rid, a=acct, c=contractid, q=body.qualificationcode, d=body.renewaldays,
        cl=(body.clause or "").strip().upper()[:128] or None, now=utcnow(), u=user["recordid"])
    log(conn, user, "create", "contractrequirement", rid,
        {"contract": contractid, "qualification": body.qualificationcode}, ip=client_ip(request))
    saved(conn)
    return {"recordid": rid}


@router.post("/contracts/{contractid}/requirements/{requirementid}/end")
def end_contract_requirement(contractid: str, requirementid: str, request: Request,
                             user: dict = Depends(manager), conn: Connection = Depends(get_conn)):
    """Taken off the contract - ended rather than deleted, so what it asked before stays known."""
    n = run(conn, """
        UPDATE contractrequirements SET endedon = :now
        WHERE recordid = :r AND contractid = :c AND accountid = :a AND endedon IS NULL
    """, now=utcnow(), r=requirementid, c=contractid, a=user["accountid"]).rowcount
    if not n:
        raise HTTPException(404, "No such requirement")
    log(conn, user, "end", "contractrequirement", requirementid, ip=client_ip(request))
    saved(conn)
    return {"ok": True}
