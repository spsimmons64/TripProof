###################################################################################################
# Evaluator - stamps every leg of a set of trips with the credential state at its pickup time.
#
# For each leg:
#   1. Pick the PUBLISHED rule sets in force on the pickup date, in layers:
#        law      federal (state 'US'), the account's state, its county and city - every trip
#        program  the Medicaid baseline for the state plus the paying broker's set - broker trips only.
#                 A broker version that includes the baseline (includesbase: the baseline imported,
#                 then edited) is the whole program list for that broker's trips; older broker
#                 versions add to the baseline. The law layers are never replaced.
#      Obligations (legal duties with nothing to check per trip) and conditional rules are not
#      checked per trip. Drafts are never evaluated.
#   2. For each requirement (skipping ones limited to other service levels), find the subject
#      (driver / vehicle / company / the trip leg itself) and ask the matching verdict in validity.py.
#   3. Save one legchecks row per (leg, requirement) under a new evaluation run.
# Then trips.lastrunid moves to the new run, which is what makes these checks "current".
#
# A run stores the requirements it used (rulesnapshot) and never edits old runs, so any earlier
# answer can be reproduced exactly.
###################################################################################################
import json
from collections import defaultdict
from decimal import Decimal

from sqlalchemy.engine import Connection

from app.db import newid, rows, run, run_many, utcnow
from app import eligibility, vehicleclass
from app.validity import (CredentialFact, annual_review_verdict, credential_as_of, driver_age_verdict,
                          eligibility_verdict, license_class_verdict, license_years_verdict,
                          trip_evidence_verdict, vehicle_age_verdict, vehicle_mileage_verdict)

ENGINE_VERSION = "1.1"


def load_requirements(conn: Connection, state: str, status: str = "published", rulesetid: str | None = None,
                      accountid: str | None = None) -> list[dict]:
    """Requirements of the rule sets for a state (its own plus the federal layer) with the given
    status, or of one specific rule set.

    An account's own set comes with them: what that company requires of its drivers, generated from
    its qualification list. Nobody else's account set is ever loaded - a rule set with an accountid
    belongs to that account alone."""
    where = "r.recordid = :rs" if rulesetid else (
        "((r.accountid IS NULL AND r.state IN (:state, 'US') AND r.status = :status)"
        " OR (r.accountid IS NOT NULL AND r.accountid = :acct))")
    reqs = rows(conn, f"""
        SELECT q.recordid, q.code, q.kind, q.status AS reqstatus, q.subject, q.credentialtypeid, q.gracedays, q.servicelevels,
               q.params, q.description, CASE WHEN q.noagelimit = 1 THEN NULL ELSE COALESCE(q.maxagedays, t.maxagedays) END AS maxagedays,
               t.defaultvaliddays, t.name AS typename, t.code AS typecode,
               r.recordid AS rulesetid, r.family, r.version, r.brokerid, r.includesbase, r.effectivefrom, r.effectiveto,
               r.level, r.county, r.city,
               r.verified, r.status
        FROM requirements q
        JOIN rulesets r ON r.recordid = q.rulesetid
        LEFT JOIN credentialtypes t ON t.recordid = q.credentialtypeid
        WHERE {where}
    """, state=state, status=status, rs=rulesetid, acct=accountid)
    for q in reqs:
        q["servicelevels"] = [s.lower() for s in json.loads(q["servicelevels"])] if q["servicelevels"] else None
        q["params"] = json.loads(q["params"]) if q["params"] else {}
    return reqs


def _same(a, b) -> bool:
    return (a or "").strip().lower() == (b or "").strip().lower()


def applicable(reqs: list[dict], brokerid: str | None, pickupdate, servicelevel: str | None,
               ignore_dates: bool = False, county: str | None = None, city: str | None = None) -> list[dict]:
    out = []
    for q in reqs:
        level = q.get("level") or "program"
        # 'account' is the company's own policy: no broker, county or city narrows it.
        if q.get("kind") == "obligation":
            continue
        if q.get("reqstatus") in ("CONDITIONAL", "NO_REQUIREMENT_FOUND"):
            continue
        if level == "county" and not _same(q.get("county"), county):
            continue
        if level == "city" and not _same(q.get("city"), city):
            continue
        if level == "program":
            if q["brokerid"] is not None and q["brokerid"] != brokerid:
                continue
            if q["brokerid"] is None and brokerid is None:      # Medicaid rules are for broker (Medicaid) trips
                continue
        if not ignore_dates and (q["effectivefrom"] > pickupdate or (q["effectiveto"] and q["effectiveto"] < pickupdate)):
            continue
        # A requirement limited to certain service levels applies to trips of those levels, and to
        # trips whose level the export did not say - an unknown level is not a reason to skip a check.
        if q["servicelevels"] and servicelevel and servicelevel.lower() not in q["servicelevels"]:
            continue
        out.append(q)
    if any(q["brokerid"] is not None and q.get("includesbase") for q in out):
        out = [q for q in out if not ((q.get("level") or "program") == "program" and q["brokerid"] is None)]
    return out


class Facts:
    """Everything about one account the checks read, loaded once per run."""

    def __init__(self, conn: Connection, accountid: str):
        self.accountid = accountid
        self.creds: dict[tuple, list[CredentialFact]] = defaultdict(list)
        for c in rows(conn, """
            SELECT recordid, subject, subjectid, credentialtypeid, issuedon, expireson, revokedon,
                   revokereason, amount, exempt
            FROM credentials WHERE accountid = :acct AND deleted IS NULL
        """, acct=accountid):
            self.creds[(c["subject"], c["subjectid"], c["credentialtypeid"])].append(
                CredentialFact(c["recordid"], c["issuedon"], c["expireson"], c["revokedon"],
                               c["revokereason"], c["amount"], bool(c["exempt"])))
        self.vehicles = {v["recordid"]: v for v in rows(
            conn, "SELECT recordid, modelyear, odometer, seats, gvwr FROM vehicles WHERE accountid = :acct",
            acct=accountid)}
        self.drivers = {d["recordid"]: d for d in rows(
            conn, "SELECT recordid, dob, licensesince, licenseclass, endorsements, operatescmv "
                  "FROM drivers WHERE accountid = :acct", acct=accountid)}
        # Two records are read as dates rather than as documents: the driving record obtained, and
        # the review of it.
        self.dated: dict[tuple, list] = defaultdict(list)
        for c in rows(conn, """
            SELECT c.subjectid, t.code, c.issuedon, c.added
            FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
            WHERE c.accountid = :acct AND c.subject = 'driver' AND c.deleted IS NULL
              AND c.revokedon IS NULL AND t.code IN ('MVR', 'ANNUAL_REVIEW')
        """, acct=accountid):
            # The date it carries, and the moment it landed - the second decides which of two
            # records dated the same day the reviewer actually had in front of them.
            self.dated[(c["subjectid"], c["code"])].append((c["issuedon"], c["added"]))
        # What each review found, so a trip is not merely checked for a review having happened.
        self.findings: dict[str, list] = defaultdict(list)
        for r in rows(conn, """
            SELECT driverid, reviewedon, createdon, finding FROM annualreviews WHERE accountid = :acct
        """, acct=accountid):
            self.findings[r["driverid"]].append((r["reviewedon"], r["createdon"], r["finding"]))
        # A bar on safety-sensitive work is not a document, so it is not in creds: it is a span of
        # days during which this driver may not drive a covered vehicle at all.
        self.barred: dict[str, list] = defaultdict(list)
        for r in rows(conn, """
            SELECT driverid, startedon, reason, clearedon FROM driverprohibitions
            WHERE accountid = :acct AND withdrawn IS NULL
        """, acct=accountid):
            self.barred[r["driverid"]].append((r["startedon"], r["reason"], r["clearedon"]))


def check(q: dict, leg: dict, facts: Facts):
    """One requirement against one leg. Returns (subjectid, Verdict) - Verdict None means no subject."""
    subjectid = {"driver": leg["driverid"], "vehicle": leg["vehicleid"], "company": facts.accountid,
                 "trip": leg["legid"]}[q["subject"]]
    if subjectid is None:
        return None, None
    at, p = leg["pickupat"], q["params"]
    kind = q["kind"]
    if kind == "vehicleage":
        return subjectid, vehicle_age_verdict(facts.vehicles.get(subjectid, {}).get("modelyear"), at, int(p.get("maxyears", 10)))
    if kind == "vehiclemileage":
        return subjectid, vehicle_mileage_verdict(facts.vehicles.get(subjectid, {}).get("odometer"), int(p["maxmiles"]))
    if kind == "driverage":
        return subjectid, driver_age_verdict(facts.drivers.get(subjectid, {}).get("dob"), at, int(p["minyears"]))
    if kind == "licenseyears":
        return subjectid, license_years_verdict(facts.drivers.get(subjectid, {}).get("licensesince"), at, int(p["minyears"]))
    if kind == "licenseclass":
        # The vehicle says what license it takes; the driver says what they hold. Neither is a
        # judgement about the company's program - only about the seat that was filled.
        if leg["vehicleid"] is None:
            return subjectid, None
        driver = facts.drivers.get(subjectid, {})
        needed = vehicleclass.license_for(facts.vehicles.get(leg["vehicleid"], {}))
        return subjectid, license_class_verdict(needed, driver.get("licenseclass"), driver.get("endorsements"))
    if kind == "eligibility":
        # Part 382 reaches commercial drivers, and what counts as one is settled in one place:
        # the company's own answer where they have given it, the license class otherwise.
        if not eligibility.covered(facts.drivers.get(subjectid, {})):
            return subjectid, None
        held = [b for b in facts.barred.get(subjectid, []) if b[0] <= at.date()
                and (b[2] is None or b[2] > at.date())]
        return subjectid, eligibility_verdict(max(held) if held else None, at)
    if kind == "annualreview":
        # Only a driver the carrier runs under Part 391 owes one.
        driver = facts.drivers.get(subjectid, {})
        if not driver.get("operatescmv") and (driver.get("licenseclass") or "").upper() not in ("A", "B", "C"):
            return subjectid, None
        def newest(code):
            seen = [d for d in facts.dated.get((subjectid, code), []) if d[0] <= at.date()]
            return max(seen) if seen else (None, None)
        mvr_on, mvr_added = newest("MVR")
        review_on, review_added = newest("ANNUAL_REVIEW")
        made = [f for f in facts.findings.get(subjectid, []) if f[0] <= at.date()]
        finding = max(made)[2] if made else None
        return subjectid, annual_review_verdict(mvr_on, review_on, at, mvr_added=mvr_added,
                                                review_added=review_added, finding=finding)
    if kind == "tripevidence":
        return subjectid, trip_evidence_verdict(bool(leg.get(p["field"])), p["field"])
    minamount = Decimal(str(p["minamount"])) if p.get("minamount") is not None else None
    return subjectid, credential_as_of(facts.creds.get((q["subject"], subjectid, q["credentialtypeid"]), []), at,
                                       q["typename"], q["maxagedays"], q["gracedays"], q["defaultvaliddays"], minamount)


def load_legs(conn: Connection, accountid: str, tripids: list[str] | None) -> list[dict]:
    trip_filter, params = "", {"acct": accountid}
    if tripids is not None:
        params.update({f"t{i}": t for i, t in enumerate(tripids)})
        trip_filter = "AND t.recordid IN (" + ", ".join(f":t{i}" for i in range(len(tripids))) + ")"
    return rows(conn, f"""
        SELECT l.recordid AS legid, l.tripid, l.driverid, l.vehicleid, l.pickupat, l.signature, l.gps,
               t.brokerid, t.servicelevel, t.billedamount
        FROM triplegs l JOIN trips t ON t.recordid = l.tripid
        WHERE t.accountid = :acct AND t.deleted IS NULL {trip_filter}
    """, **params)


def evaluate(conn: Connection, accountid: str, tripids: list[str] | None = None,
             userid: str | None = None, reason: str = "manual") -> dict:
    """Evaluate the given trips (all of the account's trips when tripids is None)."""
    if tripids is not None and not tripids:
        return {"runid": None, "trips": 0, "legs": 0, "failures": 0}
    account = rows(conn, "SELECT state, county, city FROM accounts WHERE recordid = :id", id=accountid)[0]
    reqs = load_requirements(conn, account["state"], accountid=accountid)
    legs = load_legs(conn, accountid, tripids)
    facts = Facts(conn, accountid)

    runid = newid()
    run(conn, """
        INSERT INTO evaluationruns (recordid, accountid, userid, reason, engineversion, rulesnapshot)
        VALUES (:id, :acct, :uid, :reason, :ver, :snap)
    """, id=runid, acct=accountid, uid=userid, reason=reason, ver=ENGINE_VERSION,
        snap=json.dumps(reqs, default=str))

    checks = []
    for leg in legs:
        for q in applicable(reqs, leg["brokerid"], leg["pickupat"].date(), leg["servicelevel"],
                            county=account["county"], city=account["city"]):
            subjectid, v = check(q, leg, facts)
            base = {"id": newid(), "run": runid, "acct": accountid, "trip": leg["tripid"], "leg": leg["legid"],
                    "req": q["recordid"], "subject": q["subject"], "sid": subjectid}
            if v is None:
                checks.append({**base, "outcome": "nosubject", "code": "nosubject",
                               "reason": f"No {q['subject']} matched on this leg", "cred": None, "ws": None, "we": None})
            else:
                checks.append({**base, "outcome": v.outcome, "code": v.reasoncode, "reason": v.reason,
                               "cred": v.credentialid,
                               "ws": v.window.start if v.window else None, "we": v.window.end if v.window else None})

    run_many(conn, """
        INSERT INTO legchecks (recordid, runid, accountid, tripid, legid, requirementid, subject, subjectid,
                               outcome, reasoncode, reason, credentialid, windowstart, windowend)
        VALUES (:id, :run, :acct, :trip, :leg, :req, :subject, :sid, :outcome, :code, :reason, :cred, :ws, :we)
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


