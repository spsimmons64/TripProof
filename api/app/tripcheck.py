###################################################################################################
# May this driver, in this vehicle, take this trip?
#
# The fourth of the four questions (see app/qualification.py), and the only one asked about a
# particular trip. The requirements are evaluated AS OF THE PICKUP, not today - a license that runs
# out tonight leaves the driver qualified for this afternoon and not for tomorrow morning - and
# only those that reach the trip's program count. HR obligations never do.
#
#   notqualified  something that may refuse the trip - an approved rule or a structural fact - is
#                 failed, lapsed or missing
#   needsreview   something is waiting to be read, nobody can yet say whether a rule applies, or
#                 a rule still in draft finds a shortfall it is not yet allowed to refuse for
#   eligible      everything that reaches this trip is met
#
# Every check is kept, with the rules it read, so an assignment can be explained afterwards from the
# answer it was given. A check made in shadow is recorded and not enforced.
###################################################################################################
import json
import re
from datetime import date, datetime

from sqlalchemy.engine import Connection

from app import facts as factset
from app import payerlines, rules
from app.engine import ENGINE_VERSION
from app.db import newid, row, rows, run, utcnow

FAILING = ("failed", "expired", "overdue", "pending")
WAITING = ("review", "ordered")

# Facts that stop a trip whatever the review status of the rule that states them. A rule waits for
# a reviewer because its wording or its reach is a matter of interpretation; these are not. A
# driver with a DOT positive and no return to duty is barred by 49 CFR 382.501, and a vehicle with
# an uncorrected defect may not be dispatched by 396.11(a)(3) - the record says so, and there is
# nothing for a reviewer to read into it. So they block while their rule is still Draft, the way
# not hired and no lift always have.
ALWAYS_ENFORCED = ("DA_PROHIBITION", "DVIR")


def enforceable(item: dict) -> bool:
    """Whether a shortfall may refuse a trip: a rule a reviewer approved, or one of the facts above."""
    return item.get("code") in ALWAYS_ENFORCED or any(
        s.get("legalreview") == "approved" for s in (item.get("sources") or [item]))

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


def trip_states(leg: dict | None) -> list[str]:
    """The states a leg is in, pickup first: one where it starts and ends in the same state, two
    where it crosses a line. A Georgia pickup for a Florida doctor is held to both."""
    found = (pickup_state((leg or {}).get("pickupplace")),
             pickup_state((leg or {}).get("dropoffplace")))
    return list(dict.fromkeys(s for s in found if s))


# Wheelchair securement is what a wheelchair trip asks of the driver; which levels need a lift is
# dispatch's own table, read rather than restated.
SECUREMENT = "TRN-003"
WHEELCHAIR_LEVELS = ("wheelchair", "bariwheelchair")


def leg_context(conn: Connection, accountid: str, legid: str) -> dict | None:
    return row(conn, """
        SELECT l.recordid, l.driverid, l.vehicleid, l.pickupat, t.payer, t.tripdate,
               t.brokerid, COALESCE(l.servicelevel, t.servicelevel) AS servicelevel,
               l.pickupplace, l.dropoffplace,
               -- Where the trip began: its payer line is the one for that state on every leg,
               -- the return included, as its price is.
               (SELECT f.pickupplace FROM triplegs f WHERE f.tripid = l.tripid
                ORDER BY f.legnumber LIMIT 1) AS originplace
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE l.recordid = :l AND l.accountid = :a
    """, l=legid, a=accountid)


def line_state(conn: Connection, accountid: str, state: str | None) -> str | None:
    """The state a trip's payer line is read for: where it was picked up, or the company's home
    state where the address does not say - as the fee schedule is (app/rates.py in_force)."""
    return (state or (row(conn, "SELECT state FROM accounts WHERE recordid = :a",
                          a=accountid) or {}).get("state") or "").upper()[:2] or None


def contract_for(conn: Connection, accountid: str, payerid: str | None, on,
                 state: str | None = None) -> dict | None:
    """The payer line a trip billed to this payer falls under: the one for the state the trip
    began in, or a line for every state. None where the payer is not carried for there."""
    if not payerid:
        return None
    return row(conn, f"""
        SELECT recordid, broker, state, program, reviewed, requiresapproval FROM companycontracts c
        WHERE accountid = :a AND payerid = :p AND status = 'active' AND {payerlines.live("c")}
          AND (c.state IS NULL OR c.state = :st)
          AND (effectivefrom IS NULL OR effectivefrom <= :on)
          AND (effectiveto IS NULL OR effectiveto >= :on)
        ORDER BY c.state IS NOT NULL DESC, reviewed DESC, effectivefrom DESC LIMIT 1
    """, a=accountid, p=payerid, st=line_state(conn, accountid, state), on=on)


def no_line(conn: Connection, accountid: str, payerid: str, state: str | None) -> str:
    """What to say when a payer has no line where the trip begins."""
    name = (row(conn, "SELECT name FROM payers WHERE recordid = :p", p=payerid) or {}).get("name")
    where = line_state(conn, accountid, state) or "this state"
    return (f"{name or 'This payer'} is not set up for {where}. "
            f"Add {_a(where)} {where} line on the Payers page.")


def _a(word: str) -> str:
    """"a" or "an" before a word as it is said: a state's code is read out letter by letter, so it
    is "an AL line" and "a GA line"; a name is read as a word, so "an Alabama line"."""
    if len(word) == 2 and word.isupper():
        return "an" if word[0] in "AEFHILMNORSX" else "a"
    return "an" if word[:1].lower() in "aeiou" else "a"


# What judge_items reads of a requirement, and all it reads - kept with every decision so the same
# judgement can be made again from the record alone (replay, below).
ITEM_KEYS = ("code", "qualificationcode", "name", "status", "why", "applies", "blocking", "dueon",
             "enforcement", "program", "legalreview", "restricted", "documentid", "recordid",
             "expireson")
SOURCE_KEYS = ("code", "status", "applies", "why", "program", "legalreview", "restricted")


def kept_item(i: dict) -> dict:
    out = {k: i.get(k) for k in ITEM_KEYS}
    if i.get("sources"):
        out["sources"] = [{k: s.get(k) for k in SOURCE_KEYS} for s in i["sources"]]
    return out


def judge_items(items: list[dict], program: str, at: datetime) -> tuple[list, list, list]:
    """What the requirements on file mean for one trip: what refuses it, what is said about it, and
    what an owner or admin has to accept. Pure - reads nothing but its arguments - so a decision can
    be made again from what was kept with it."""
    blockers, warnings, holds = [], [], []
    day = at.date() if isinstance(at, datetime) else at
    for i in items:
        if i.get("enforcement") == "hr":
            continue
        # The row as this trip's program sees it, so another program's shortfall cannot block it.
        i = rules.for_program(i, program)
        if not i:
            continue
        due = i.get("dueon")
        if isinstance(due, str):
            due = date.fromisoformat(due[:10])
        # Only a rule a reviewer approved may be enforced. Anything else is recorded.
        said = {"qualification": i.get("qualificationcode"), "code": i["code"],
                "name": i["name"], "status": i["status"], "reason": i.get("why"),
                "enforceable": enforceable(i)}
        if i["applies"] is None:
            warnings.append({**said, "reason": f'Applicability undecided - {i.get("why")}'})
        # Missing but not yet due by the day of the trip - a training allowed 90 days from
        # hire - is a warning, not a bar.
        elif (i["applies"] is True and i.get("blocking") and i["status"] == "pending"
              and due and due > day):
            warnings.append({**said, "reason": f'Due by {due:%m/%d/%Y}.'})
        elif i["applies"] is True and i.get("blocking") and i["status"] in FAILING:
            blockers.append(said)
        # A driving record read as restricting what the driver may do. TripProof cannot judge a
        # trip against the restriction's terms, so it holds the trip for a person: under an
        # approved rule an owner or admin accepts it for this trip, with the reason, or the
        # driver is not put on it.
        elif i["applies"] is True and i["status"] == "review" and any(
                s.get("restricted") for s in (i.get("sources") or [i])):
            hold = {**said, "hold": "restricted",
                    "reason": f'{i.get("why")} An owner or admin has to accept it for this trip.'}
            (holds if said["enforceable"] else warnings).append(hold)
        elif i["applies"] is True and i.get("blocking") and i["status"] in WAITING:
            warnings.append(said)
        elif i["applies"] is True and i["status"] == "expiring":
            warnings.append(said)
    return blockers, warnings, holds


def replay(conn: Connection, accountid: str, evaluationid: str) -> dict:
    """Make a recorded decision again from what was kept with it - the requirements as they stood,
    the trip's program and day - and nothing read live. Says whether the rule-based part comes out
    the same, and whether the engine that made it is the engine replaying it, and confirms that
    every rule it read can still be recovered, by version and hash, from the rule history."""
    kept = row(conn, """
        SELECT program, evaluatedfor, blockers, warnings, rulesread, standingread, engineversion
        FROM tripeligibility WHERE recordid = :i AND accountid = :a
    """, i=evaluationid, a=accountid)
    if not kept or kept["standingread"] is None:
        return {"replayable": False, "why": "No inputs were kept with this decision."}
    items = json.loads(kept["standingread"])
    b, w, h = judge_items(items, kept["program"], kept["evaluatedfor"])
    codes = {i["code"] for i in items}
    def rulebased(found):
        return sorted({(x["code"], x.get("hold") or "") for x in found if x["code"] in codes})
    recorded_b = json.loads(kept["blockers"] or "[]")
    recorded_w = json.loads(kept["warnings"] or "[]")
    read = json.loads(kept["rulesread"] or "[]")
    missing = [r["code"] for r in read if r.get("version") and not row(conn, """
        SELECT 1 AS x FROM compliancerulesversions WHERE rulecode = :c AND version = :v
          AND snapshotsha = :h AND accountid IS NULL""", c=r["code"], v=r["version"], h=r.get("sha"))]
    return {
        "replayable": True,
        "engine": kept["engineversion"], "sameengine": kept["engineversion"] == ENGINE_VERSION,
        "matches": rulebased(b) == rulebased(recorded_b) and rulebased(w + h) == rulebased(recorded_w),
        "rulesrecoverable": not missing, "missing": missing,
        "blockers": b, "warnings": w, "holds": h,
    }


def what_if(conn: Connection, accountid: str, codes: list[str], since=None) -> dict:
    """Before rules are approved: which recorded decisions they would have refused. Each decision is
    judged again from what was kept with it (as replay does), with these rules taken as approved -
    the shadow-against-enforced comparison to read before switching a stage of rules on."""
    codes = set(codes)
    held = rows(conn, f"""
        SELECT recordid, driverid, legid, program, evaluatedfor, standingread FROM tripeligibility
        WHERE accountid = :a AND standingread IS NOT NULL {"AND evaluatedon >= :s" if since else ""}
        ORDER BY evaluatedon
    """, a=accountid, s=since)
    refused, byrule = [], {}
    for d in held:
        items = json.loads(d["standingread"])
        for i in items:
            for s in i.get("sources") or []:
                if s["code"] in codes:
                    s["legalreview"] = "approved"
            if i["code"] in codes:
                i["legalreview"] = "approved"
        b, _w, h = judge_items(items, d["program"], d["evaluatedfor"])
        newly = sorted({x["code"] for x in b + h if x["enforceable"] and (
            x["code"] in codes or any(s.get("code") in codes for s in next(
                (i.get("sources") or [] for i in items if i["code"] == x["code"]), [])))})
        if newly:
            refused.append({"evaluationid": d["recordid"], "driverid": d["driverid"],
                            "legid": d["legid"], "rules": newly})
            for c in newly:
                byrule[c] = byrule.get(c, 0) + 1
    return {"decisions": len(held), "refused": len(refused), "byrule": byrule, "which": refused}


def program_of(conn: Connection, accountid: str, leg: dict | None, at: datetime,
               program: str | None = None) -> tuple[str, dict | None, str | None]:
    """The trip's program, the payer line it falls under, and the state it began in. The line's own
    program, where it names one, decides; otherwise the payer's kind; no payer is the passenger."""
    origin = pickup_state((leg or {}).get("originplace") or (leg or {}).get("pickupplace"))
    contract = (contract_for(conn, accountid, leg.get("brokerid"), at.date(), origin)
                if leg else None)
    if leg:
        program = program or (contract or {}).get("program") or PAYER_PROGRAM.get(
            leg.get("payer") or "private", "privatepay")
    return program or "privatepay", contract, origin


def vehicle_blockers(conn: Connection, accountid: str, vehicleid: str, service: str | None,
                     at: datetime, states: list[str] | None = None,
                     program: str | None = None, contract: dict | None = None) -> list[dict]:
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
    vfacts = factset.assemble(conn, accountid, None, vehicleid, states=states)["facts"]
    # On a Medicaid trip, only the state of the trip's own line: a Florida trip in a vehicle the
    # Georgia broker also uses is not held to Georgia's inspection.
    # And only through an approval for THIS line: a vehicle another Georgia broker approved is not
    # thereby in this broker's service.
    if contract and contract.get("program") == "medicaid" and vfacts.get("vehicle.medicaidstates"):
        line = (contract.get("state") or "").upper()
        vfacts["vehicle.medicaidstates"] = (
            [line] if contract["recordid"] in (vfacts.get("vehicle.contracts") or []) else [])
    for v in rules.for_vehicle(conn, accountid, vehicleid, vfacts, today=at.date()):
        # Another program's rule does not stop this trip: a Georgia Medicaid inspection says
        # nothing about a private pay run.
        if program and v.get("program") not in (None, program):
            continue
        # The same shortfalls that stop a driver - a vehicle with no registration on file is no more
        # fit to go out than one whose registration lapsed - and enforceable on the same terms:
        # only a rule a reviewer approved.
        if v["applies"] is True and v.get("blocking") and v["status"] in FAILING:
            out.append({"code": v["code"], "name": v["name"], "status": v["status"],
                        "reason": v.get("why"), "vehicle": True,
                        "enforceable": enforceable(v)})
    # A line that approves its vehicles, and this one is not approved for it. Refused, the same as a
    # driver the line has not approved: a broker that vets vehicles does not pay for a trip in one
    # it never vetted (MODIVTEST CF-3, where Georgia trips ran in vans approved for Florida only).
    # Here rather than in check() alone, so the dispatch list greys the vehicle out instead of
    # offering it and the assignment then refusing it.
    if contract and contract.get("requiresapproval") and not row(conn, """
            SELECT 1 AS x FROM vehicleauthorizations WHERE accountid = :a AND vehicleid = :v
              AND contractid = :c AND endedon IS NULL""", a=accountid, v=vehicleid,
            c=contract["recordid"]):
        out.append({"code": "VEHICLEAPPROVAL", "vehicle": True, "enforceable": True,
                    "reason": "The vehicle is not approved for the "
                    + " ".join(x for x in (contract["broker"], contract.get("state")) if x)
                    + " line."})
    return out


def check(conn: Connection, accountid: str, driverid: str, vehicleid: str | None = None, *,
          legid: str | None = None, program: str | None = None, at: datetime | None = None,
          userid: str | None = None, shadow: bool = False, record: bool = True,
          proposed: dict | None = None) -> dict:
    """Decide, record, and return the decision with its reasons.

    `record=False` decides without keeping it - dispatch trying candidates for a leg, or the
    evaluator judging a batch of imported trips. Only an actual assignment is a decision on file.

    `proposed` is a leg not yet booked - payer, places, pickup time - asked about before it exists."""
    leg = leg_context(conn, accountid, legid) if legid else proposed
    if leg:
        vehicleid = vehicleid or leg["vehicleid"]
        at = at or leg["pickupat"] or (datetime.combine(leg["tripdate"], datetime.min.time())
                                       if leg["tripdate"] else None)
    at = at or utcnow()
    program, contract, origin = program_of(conn, accountid, leg, at, program)
    service = (leg or {}).get("servicelevel")
    states = trip_states(leg)
    from app import ruleversions
    versions = ruleversions.current_snapshots(conn)

    blockers, warnings, read, holds = [], [], [], []
    # What the decision was made FROM, kept with it: the facts as assembled for this trip, and where
    # each requirement stood and on which record. With the rule hashes in `read`, a decision can be
    # replayed - the same rules, the same facts, the same evidence.
    seenfacts, standing = {}, []
    # About the trip, not the driver: a payer not carried for where it begins cannot be billed.
    if leg and leg.get("brokerid") and not contract:
        blockers.append({"code": "PAYERLINE", "enforceable": True,
                         "reason": no_line(conn, accountid, leg["brokerid"], origin)})
    driver = row(conn, "SELECT status FROM drivers WHERE recordid = :d AND accountid = :a "
                       "AND deleted IS NULL", d=driverid, a=accountid)
    if not driver:
        blockers.append({"code": "DRIVER", "enforceable": True,
                         "reason": "No such driver on this account."})
    elif driver["status"] != "hired":
        blockers.append({"code": "HIRED", "enforceable": True,
                         "reason": "The driver has not been hired."})
    else:
        # Held to the rules of every state the trip is in, and to the federal ones if it crosses.
        facts = factset.assemble(conn, accountid, driverid, vehicleid, states=states)["facts"]
        # A Medicaid trip is held to the program of the state its payer line is for, and no other:
        # a Florida member driven into Georgia is a Florida Medicaid trip.
        if contract and contract.get("program") == "medicaid":
            facts["company.medicaidstates"] = [(contract.get("state") or origin or "").upper()]
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
        seenfacts = facts
        standing = [kept_item(i) for i in items]
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
            seen = rules.for_program(i, program)
            for src in (seen or {}).get("sources") or []:
                held = versions.get(src["code"]) or {}
                read.append({"code": src["code"], "legalreview": src.get("legalreview"),
                             "version": held.get("version"), "sha": held.get("sha")})
        b, w, h = judge_items(items, program, at)
        blockers += b
        warnings += w
        holds += h
    if vehicleid:
        blockers += vehicle_blockers(conn, accountid, vehicleid, service, at, states, program,
                                     contract)


    undecided = bool(holds) or any(w.get("code") == "CONTRACT" or w.get("status") in WAITING
                    or str(w.get("reason") or "").startswith("Applicability undecided")
                    for w in warnings)
    # Not qualified only for what may actually refuse the trip. A shortfall under a rule still in
    # draft is said - it is on the record and in `blockers` - but nothing is refused for it, and a
    # label that called it "not qualified" counted every draft shortfall as a refusal (MODIVTEST
    # B-03: the same 436 "not qualified" with every rule in draft as with every rule approved).
    refusing = [b for b in blockers if b.get("enforceable")]
    decision = ("notqualified" if refusing
                else "needsreview" if undecided or blockers else "eligible")
    evalid = newid() if record else None
    if record:
        run(conn, """
            INSERT INTO tripeligibility (recordid, accountid, driverid, vehicleid, legid, program,
                                         evaluatedfor, evaluatedon, evaluatedby, decision, blockers,
                                         warnings, rulesread, shadow, engineversion, factsread,
                                         standingread)
            VALUES (:id, :a, :d, :v, :l, :p, :for, :now, :by, :dec, :b, :w, :r, :s, :e, :f, :st)
        """, id=evalid, a=accountid, d=driverid, v=vehicleid, l=legid, p=program, now=utcnow(),
            by=userid, dec=decision, b=json.dumps(blockers, default=str),
            # Holds are kept with the warnings, marked as holds, so the record shows what an owner
            # or admin was asked to accept.
            w=json.dumps(warnings + holds, default=str), r=json.dumps(read), s=int(shadow),
            e=ENGINE_VERSION, f=json.dumps(seenfacts, default=str, sort_keys=True),
            st=json.dumps(standing, default=str), **{"for": at})
    return {"evaluationid": evalid, "eligible": decision == "eligible", "decision": decision,
            "program": program, "service": service, "evaluatedfor": at, "blockers": blockers,
            "state": states[0] if states else None, "states": states,
            "warnings": warnings, "rulesread": read, "shadow": shadow,
            # Held for an owner or admin to accept, trip by trip - see the restricted record above.
            "holds": holds,
            "engineversion": ENGINE_VERSION,
            # What may actually be refused: approved rules and the structural facts.
            "enforceable": [b for b in blockers if b.get("enforceable")]}
