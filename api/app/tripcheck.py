###################################################################################################
# May this driver, in this vehicle, take this trip?
#
# The fourth of the four questions (see app/qualification.py), and the only one asked about a
# particular trip. The requirements are evaluated AS OF THE PICKUP, not today - a license that runs
# out tonight leaves the driver qualified for this afternoon and not for tomorrow morning - and
# only those that reach the trip's program count. HR obligations never do.
#
#   notqualified  something the trip's program requires is failed, lapsed or missing
#   needsreview   something is waiting to be read, or nobody can yet say whether a rule applies
#   eligible      everything that reaches this trip is met
#
# Every check is kept, with the rules it read, so an assignment can be explained afterwards from the
# answer it was given. A check made in shadow is recorded and not enforced.
###################################################################################################
import json
import re
from datetime import datetime

from sqlalchemy.engine import Connection

from app import facts as factset
from app import payerlines, rules
from app.db import newid, row, run, utcnow

FAILING = ("failed", "expired", "overdue", "pending")
WAITING = ("review", "ordered")

# Which program a payer's trip belongs to. A transportation broker is taken to be administering
# Medicaid transportation, which is what an NEMT broker does; a contract record can say otherwise.
PAYER_PROGRAM = {"medicaid": "medicaid", "broker": "medicaid", "commercial": "commercialinsurance",
                 "flatcontract": "facility", "private": "privatepay"}


# The state a pickup is in, read off its address: "..., Tampa, FL 33602". None where the address
# does not say, and then the company's own states decide, as for the driver's file.
STATE_IN_ADDRESS = re.compile(r"\b([A-Z]{2})\s+\d{5}(?:-\d{4})?\b")


def pickup_state(place: str | None) -> str | None:
    found = STATE_IN_ADDRESS.findall((place or "").upper())
    return found[-1] if found else None


# Wheelchair securement is what a wheelchair trip asks of the driver; which levels need a lift is
# dispatch's own table, read rather than restated.
SECUREMENT = "TRN-003"
WHEELCHAIR_LEVELS = ("wheelchair", "bariwheelchair")


def leg_context(conn: Connection, accountid: str, legid: str) -> dict | None:
    return row(conn, """
        SELECT l.recordid, l.driverid, l.vehicleid, l.pickupat, t.payer, t.tripdate,
               t.brokerid, COALESCE(l.servicelevel, t.servicelevel) AS servicelevel,
               l.pickupplace
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=legid, a=accountid)


def contract_for(conn: Connection, accountid: str, payerid: str | None, on) -> dict | None:
    """The current broker contract a trip billed to this payer falls under, if any."""
    if not payerid:
        return None
    return row(conn, f"""
        SELECT recordid, broker, state, program, reviewed, requiresapproval FROM companycontracts c
        WHERE accountid = :a AND payerid = :p AND status = 'active' AND {payerlines.live("c")}
          AND (effectivefrom IS NULL OR effectivefrom <= :on)
          AND (effectiveto IS NULL OR effectiveto >= :on)
        ORDER BY reviewed DESC, effectivefrom DESC LIMIT 1
    """, a=accountid, p=payerid, on=on)


def vehicle_blockers(conn: Connection, accountid: str, vehicleid: str, service: str | None,
                     at: datetime) -> list[dict]:
    """What stops this vehicle carrying this trip: a lift the service needs and it lacks, and any
    blocking vehicle requirement failed or expired on the day."""
    out = []
    if service:
        from app.dispatch import SERVICE
        if (SERVICE.get(service) or {}).get("lift") and not (row(conn, "SELECT lift FROM vehicles "
                                                                  "WHERE recordid = :v", v=vehicleid)
                                                              or {}).get("lift"):
            out.append({"code": "LIFT", "enforceable": True, "vehicle": True,
                        "reason": f"A {SERVICE[service]['label'].lower()} trip needs a "
                                  f"lift-equipped vehicle."})
    vfacts = factset.assemble(conn, accountid, None, vehicleid)["facts"]
    for v in rules.for_vehicle(conn, accountid, vehicleid, vfacts, today=at.date()):
        if v["applies"] is True and v.get("blocking") and v["status"] in ("failed", "expired"):
            out.append({"code": v["code"], "name": v["name"], "status": v["status"],
                        "reason": v.get("why"), "vehicle": True})
    return out


def check(conn: Connection, accountid: str, driverid: str, vehicleid: str | None = None, *,
          legid: str | None = None, program: str | None = None, at: datetime | None = None,
          userid: str | None = None, shadow: bool = False, record: bool = True) -> dict:
    """Decide, record, and return the decision with its reasons.

    `record=False` decides without keeping it - dispatch trying candidates for a leg, or the
    evaluator judging a batch of imported trips. Only an actual assignment is a decision on file."""
    leg = leg_context(conn, accountid, legid) if legid else None
    if leg:
        vehicleid = vehicleid or leg["vehicleid"]
        at = at or leg["pickupat"] or (datetime.combine(leg["tripdate"], datetime.min.time())
                                       if leg["tripdate"] else None)
    at = at or utcnow()
    contract = contract_for(conn, accountid, (leg or {}).get("brokerid"), at.date()) if leg else None
    if leg:
        # The contract's own program, where it names one, decides; otherwise the payer's kind.
        program = program or (contract or {}).get("program") or PAYER_PROGRAM.get(
            leg["payer"] or "private", "privatepay")
    program = program or "privatepay"
    service = (leg or {}).get("servicelevel")
    from app import ruleversions
    versions = ruleversions.current(conn)

    blockers, warnings, read = [], [], []
    driver = row(conn, "SELECT status FROM drivers WHERE recordid = :d AND accountid = :a "
                       "AND deleted IS NULL", d=driverid, a=accountid)
    if not driver:
        blockers.append({"code": "DRIVER", "enforceable": True,
                         "reason": "No such driver on this account."})
    elif driver["status"] != "hired":
        blockers.append({"code": "HIRED", "enforceable": True,
                         "reason": "The driver has not been hired."})
    else:
        facts = factset.assemble(conn, accountid, driverid, vehicleid)["facts"]
        # Where the trip happens decides which state's rules reach it - not where the company is
        # headquartered. A Florida company's Georgia trip is held to Georgia's rules.
        here = pickup_state((leg or {}).get("pickupplace"))
        if here:
            facts["company.state"] = here
            facts["company.operatingstates"] = [here]
            facts["trip.state"] = here
        if contract:
            # The trip itself brings the contract's requirements with it.
            facts["trip.contract"] = contract["recordid"]
            if not contract["reviewed"]:
                warnings.append({"code": "CONTRACT", "reason":
                                 f'The {contract["broker"]} contract has not been reviewed for its '
                                 f'driver requirements, so what it asks cannot be checked.'})
            if contract["requiresapproval"] and contract["recordid"] not in (
                    facts.get("driver.contracts") or []):
                blockers.append({"code": "APPROVAL", "enforceable": True, "reason":
                                 f'The driver is not approved for the {contract["broker"]} contract.'})
        items = rules.for_driver(conn, accountid, driverid, facts, today=at.date())
        if service in WHEELCHAIR_LEVELS:
            held = next((i for i in items if i.get("qualificationcode") == SECUREMENT), None)
            if not held or held["applies"] is not True or held["status"] not in ("satisfied",
                                                                                  "expiring"):
                blockers.append({"code": "SECUREMENT", "qualification": SECUREMENT,
                                 "enforceable": True,
                                 "reason": "A wheelchair trip needs wheelchair securement training "
                                           "on file and current."})
        for i in items:
            if i.get("enforcement") == "hr":
                continue
            # The row as this trip's program sees it, so another program's shortfall cannot block it.
            i = rules.for_program(i, program)
            if not i:
                continue
            for s in i.get("sources") or []:
                read.append({"code": s["code"], "legalreview": s.get("legalreview"),
                             "version": versions.get(s["code"])})
            # Only a rule a reviewer approved may be enforced. Anything else is recorded.
            said = {"qualification": i.get("qualificationcode"), "code": i["code"],
                    "name": i["name"], "status": i["status"], "reason": i.get("why"),
                    "enforceable": any(s.get("legalreview") == "approved"
                                       for s in (i.get("sources") or [i]))}
            if i["applies"] is None:
                warnings.append({**said, "reason": f'Applicability undecided - {i.get("why")}'})
            # Missing but not yet due by the day of the trip - a training allowed 90 days from
            # hire - is a warning, not a bar.
            elif (i["applies"] is True and i.get("blocking") and i["status"] == "pending"
                  and i.get("dueon") and i["dueon"] > at.date()):
                warnings.append({**said, "reason": f'Due by {i["dueon"]:%m/%d/%Y}.'})
            elif i["applies"] is True and i.get("blocking") and i["status"] in FAILING:
                blockers.append(said)
            elif i["applies"] is True and i.get("blocking") and i["status"] in WAITING:
                warnings.append(said)
            elif i["applies"] is True and i["status"] == "expiring":
                warnings.append(said)
    if vehicleid:
        blockers += vehicle_blockers(conn, accountid, vehicleid, service, at)

    undecided = any(w.get("code") == "CONTRACT" or w.get("status") in WAITING
                    or str(w.get("reason") or "").startswith("Applicability undecided")
                    for w in warnings)
    decision = "notqualified" if blockers else "needsreview" if undecided else "eligible"
    evalid = newid() if record else None
    if record:
        run(conn, """
            INSERT INTO tripeligibility (recordid, accountid, driverid, vehicleid, legid, program,
                                         evaluatedfor, evaluatedon, evaluatedby, decision, blockers,
                                         warnings, rulesread, shadow)
            VALUES (:id, :a, :d, :v, :l, :p, :for, :now, :by, :dec, :b, :w, :r, :s)
        """, id=evalid, a=accountid, d=driverid, v=vehicleid, l=legid, p=program, now=utcnow(),
            by=userid, dec=decision, b=json.dumps(blockers, default=str),
            w=json.dumps(warnings, default=str), r=json.dumps(read), s=int(shadow), **{"for": at})
    return {"evaluationid": evalid, "eligible": decision == "eligible", "decision": decision,
            "program": program, "service": service, "evaluatedfor": at, "blockers": blockers,
            "state": pickup_state((leg or {}).get("pickupplace")),
            "warnings": warnings, "rulesread": read, "shadow": shadow,
            # What may actually be refused: approved rules and the structural facts.
            "enforceable": [b for b in blockers if b.get("enforceable")]}
