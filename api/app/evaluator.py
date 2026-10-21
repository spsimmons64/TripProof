###################################################################################################
# Evaluator - stamps every leg of a set of trips with whether it could be carried, as of its pickup.
#
# Each leg is put to tripcheck.check: the same check an assignment goes through, reading the same
# rules engine as the driver's Requirements page, for the program the trip's payer belongs to and
# the state it is picked up in. There is one answer to "could this driver carry this trip", and the
# figures on the dashboard, the trips list and an audit packet are that answer, saved.
#
# For each leg, one legchecks row per thing that stops it - a requirement failed or expired on the
# day, a driver not hired, a vehicle without the lift the service needs - or one row saying it is
# clear. A leg with nobody on it is one row saying so. Each row names the rule as it stood: code,
# name, version and whether a reviewer had approved it. The run keeps the version of every rule in
# force (rulesnapshot), and old runs are never edited, so any earlier answer can be explained by the
# rules that gave it.
#
# This replaced an evaluator with its own list of fifteen requirements (rulesets, requirements),
# seven of which asked for document types that no longer exist - migration 335.
###################################################################################################
import json

from sqlalchemy.engine import Connection

from app import ruleversions, tripcheck
from app.db import newid, rows, run, run_many, utcnow

ENGINE_VERSION = "2.0"

# The checks that are not a rule in the catalog: they are facts about the leg itself.
STRUCTURAL = {
    "DRIVER": "A driver on this leg",
    "HIRED": "The driver is hired",
    "APPROVAL": "Approved for the broker's contract",
    "SECUREMENT": "Wheelchair securement training",
    "LIFT": "A lift-equipped vehicle",
    "ELIGIBLE": "Every requirement met",
}


def load_legs(conn: Connection, accountid: str, tripids: list[str] | None) -> list[dict]:
    trip_filter, params = "", {"acct": accountid}
    if tripids is not None:
        params.update({f"t{i}": t for i, t in enumerate(tripids)})
        trip_filter = "AND t.recordid IN (" + ", ".join(f":t{i}" for i in range(len(tripids))) + ")"
    return rows(conn, f"""
        SELECT l.recordid AS legid, l.tripid, l.driverid, l.vehicleid, l.pickupat, l.pickupplace,
               COALESCE(l.servicelevel, t.servicelevel) AS servicelevel,
               t.brokerid, t.payer, t.tripdate, t.billedamount
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE t.accountid = :acct AND t.deleted IS NULL {trip_filter}
    """, **params)


def _rules(conn: Connection) -> dict[str, dict]:
    """Each rule's name and whether a reviewer approved it, by code."""
    return {r["code"]: r for r in rows(conn, """
        SELECT code, name, legalreview FROM compliancerules
        WHERE effectiveto IS NULL AND accountid IS NULL
    """)}


def evaluate(conn: Connection, accountid: str, tripids: list[str] | None = None,
             userid: str | None = None, reason: str = "manual") -> dict:
    """Evaluate the given trips (all of the account's trips when tripids is None)."""
    if tripids is not None and not tripids:
        return {"runid": None, "trips": 0, "legs": 0, "failures": 0}
    legs = load_legs(conn, accountid, tripids)
    versions = ruleversions.current(conn)
    named = _rules(conn)

    runid = newid()
    run(conn, """
        INSERT INTO evaluationruns (recordid, accountid, userid, reason, engineversion, rulesnapshot)
        VALUES (:id, :acct, :uid, :reason, :ver, :snap)
    """, id=runid, acct=accountid, uid=userid, reason=reason, ver=ENGINE_VERSION,
        snap=json.dumps({"engine": "tripcheck", "versions": versions}, default=str))

    # A batch of imported trips repeats itself: the same driver, vehicle, payer and day many times
    # over. The answer cannot differ between them, so it is worked out once.
    decided: dict[tuple, dict] = {}
    checks = []
    for leg in legs:
        base = {"run": runid, "acct": accountid, "trip": leg["tripid"], "leg": leg["legid"]}
        if not leg["driverid"]:
            checks.append({**base, "id": newid(), "subject": "driver", "sid": None,
                           "outcome": "nosubject", "code": "DRIVER", "rule": "DRIVER",
                           "name": STRUCTURAL["DRIVER"], "version": None, "approved": None,
                           "reason": "Nobody is on this leg."})
            continue
        key = (leg["driverid"], leg["vehicleid"], leg["pickupat"].date() if leg["pickupat"] else None,
               leg["brokerid"], leg["payer"], leg["servicelevel"],
               tripcheck.pickup_state(leg["pickupplace"]))
        if key not in decided:
            decided[key] = tripcheck.check(conn, accountid, leg["driverid"], leg["vehicleid"],
                                           legid=leg["legid"], at=leg["pickupat"], userid=userid,
                                           record=False)
        said = decided[key]
        seen = set()
        for b in said["blockers"]:
            if b["code"] in seen:
                continue
            seen.add(b["code"])
            rule = named.get(b["code"])
            vehicle = bool(b.get("vehicle"))
            checks.append({**base, "id": newid(),
                           "subject": "vehicle" if vehicle else "driver",
                           "sid": leg["vehicleid"] if vehicle else leg["driverid"],
                           "outcome": "fail", "code": (b.get("status") or "missing")[:24],
                           "rule": b["code"][:64],
                           "name": ((rule or {}).get("name") or b.get("name")
                                    or STRUCTURAL.get(b["code"], b["code"]))[:160],
                           "version": versions.get(b["code"]),
                           "approved": None if not rule else int(rule["legalreview"] == "approved"),
                           "reason": (b.get("reason") or "")[:255] or None})
        if not said["blockers"]:
            checks.append({**base, "id": newid(), "subject": "driver", "sid": leg["driverid"],
                           "outcome": "pass", "code": said["decision"][:24], "rule": "ELIGIBLE",
                           "name": STRUCTURAL["ELIGIBLE"], "version": None, "approved": None,
                           "reason": ("Clear to carry." if said["decision"] == "eligible" else
                                      "Clear, with something waiting on review: "
                                      + "; ".join(filter(None, (w.get("name") or w.get("reason")
                                                                for w in said["warnings"])))[:200])})

    run_many(conn, """
        INSERT INTO legchecks (recordid, runid, accountid, tripid, legid, requirementid, rulecode,
                               rulename, ruleversion, approved, subject, subjectid, outcome,
                               reasoncode, reason)
        VALUES (:id, :run, :acct, :trip, :leg, NULL, :rule, :name, :version, :approved, :subject,
                :sid, :outcome, :code, :reason)
    """, checks)

    evaluated = sorted({l["tripid"] for l in legs})
    for i in range(0, len(evaluated), 500):
        chunk = evaluated[i:i + 500]
        p = {f"t{n}": t for n, t in enumerate(chunk)}
        run(conn, f"UPDATE trips SET lastrunid = :run, updated = :now WHERE accountid = :acct AND recordid IN ("
                  + ", ".join(f":t{n}" for n in range(len(chunk))) + ")", run=runid, now=utcnow(), acct=accountid, **p)

    failures = sum(1 for c in checks if c["outcome"] != "pass")
    run(conn, """
        UPDATE evaluationruns SET tripcount = :tc, legcount = :lc, failcount = :fc, finished = :now
        WHERE recordid = :id
    """, tc=len(evaluated), lc=len(legs), fc=failures, now=utcnow(), id=runid)
    return {"runid": runid, "trips": len(evaluated), "legs": len(legs), "failures": failures}
