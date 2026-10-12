###################################################################################################
# Exposure dashboard - "You have $X in trips at audit risk." Every figure is computed from the
# current checks (trips.lastrunid), never from credential dates directly, so the dashboard and the
# audit packet can never disagree.
###################################################################################################
from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.engine import Connection

from app.db import get_conn, localnow, row, rows
from app.security import current_user

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    a = user["accountid"]
    totals = row(conn, """
        SELECT COUNT(*) AS trips, COALESCE(SUM(billedamount), 0) AS billed,
               MIN(tripdate) AS firstdate, MAX(tripdate) AS lastdate
        FROM trips WHERE accountid = :a AND deleted IS NULL
    """, a=a)
    risk = row(conn, """
        SELECT COUNT(*) AS trips, COALESCE(SUM(billedamount), 0) AS amount,
               COALESCE(SUM(billingstatus = 'unbilled'), 0) AS unbilledtrips,
               COALESCE(SUM(CASE WHEN billingstatus = 'unbilled' THEN billedamount END), 0) AS unbilledamount
        FROM tripexposure WHERE accountid = :a
    """, a=a)
    # A trip failing two ways is counted under both reasons; the headline figure above counts it once.
    # The inner DISTINCT keeps a trip with several failing legs from being summed more than once.
    byreason = rows(conn, """
        SELECT x.code, x.description, COUNT(*) AS trips, SUM(x.billedamount) AS amount
        FROM (SELECT DISTINCT q.code, q.description, e.tripid, e.billedamount
              FROM tripexposure e
              JOIN legchecks c ON c.tripid = e.tripid AND c.runid = e.runid AND c.outcome <> 'pass'
              JOIN requirements q ON q.recordid = c.requirementid
              WHERE e.accountid = :a) x
        GROUP BY x.code, x.description
        ORDER BY trips DESC
    """, a=a)
    drivers = rows(conn, """
        SELECT d.recordid, CONCAT(d.firstname, ' ', d.lastname) AS name, d.stub,
               COUNT(DISTINCT e.tripid) AS trips, SUM(e.billedamount) AS amount
        FROM (SELECT DISTINCT e.tripid, e.billedamount, l.driverid
              FROM tripexposure e
              JOIN legchecks c ON c.tripid = e.tripid AND c.runid = e.runid AND c.outcome <> 'pass' AND c.subject = 'driver'
              JOIN triplegs l ON l.recordid = c.legid
              WHERE e.accountid = :a) e
        JOIN drivers d ON d.recordid = e.driverid
        GROUP BY d.recordid, d.firstname, d.lastname, d.stub
        ORDER BY amount DESC LIMIT 10
    """, a=a)
    vehicles = rows(conn, """
        SELECT v.recordid, COALESCE(v.externalid, v.vin) AS name, v.stub,
               COUNT(DISTINCT e.tripid) AS trips, SUM(e.billedamount) AS amount
        FROM (SELECT DISTINCT e.tripid, e.billedamount, l.vehicleid
              FROM tripexposure e
              JOIN legchecks c ON c.tripid = e.tripid AND c.runid = e.runid AND c.outcome <> 'pass' AND c.subject = 'vehicle'
              JOIN triplegs l ON l.recordid = c.legid
              WHERE e.accountid = :a) e
        JOIN vehicles v ON v.recordid = e.vehicleid
        GROUP BY v.recordid, v.externalid, v.vin, v.stub
        ORDER BY amount DESC LIMIT 10
    """, a=a)
    monthly = rows(conn, """
        SELECT DATE_FORMAT(t.tripdate, '%Y-%m') AS month, COUNT(*) AS trips, SUM(t.billedamount) AS billed,
               COALESCE(SUM(CASE WHEN e.tripid IS NOT NULL THEN t.billedamount END), 0) AS atrisk,
               SUM(e.tripid IS NOT NULL) AS risktrips
        FROM trips t LEFT JOIN tripexposure e ON e.tripid = t.recordid
        WHERE t.accountid = :a AND t.deleted IS NULL
        GROUP BY month ORDER BY month
    """, a=a)

    # What will lapse soon - the forward-looking side of the same question.
    today = localnow(user["timezone"]).date()
    horizon = today + timedelta(days=30)
    expiring = rows(conn, """
        SELECT c.recordid, c.subject, c.subjectid, t.name AS typename, c.expireson,
               CASE c.subject WHEN 'driver' THEN CONCAT(d.firstname, ' ', d.lastname)
                              WHEN 'vehicle' THEN COALESCE(v.externalid, v.vin)
                              ELSE 'Company' END AS holder
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        LEFT JOIN drivers d ON c.subject = 'driver' AND d.recordid = c.subjectid
        LEFT JOIN vehicles v ON c.subject = 'vehicle' AND v.recordid = c.subjectid
        WHERE c.accountid = :a AND c.deleted IS NULL AND c.revokedon IS NULL
          AND c.expireson BETWEEN :today AND :horizon
          AND NOT EXISTS (SELECT 1 FROM credentials n
                          WHERE n.accountid = c.accountid AND n.subject = c.subject AND n.subjectid = c.subjectid
                            AND n.credentialtypeid = c.credentialtypeid AND n.deleted IS NULL
                            AND n.issuedon > c.issuedon)
        ORDER BY c.expireson LIMIT 25
    """, a=a, today=today, horizon=horizon)
    unverified = rows(conn, """
        SELECT DISTINCT r.family, r.version, r.name FROM rulesets r
        JOIN requirements q ON q.rulesetid = r.recordid
        JOIN legchecks c ON c.requirementid = q.recordid
        JOIN trips t ON t.recordid = c.tripid AND t.lastrunid = c.runid
        WHERE t.accountid = :a AND r.verified = 0
    """, a=a)
    stubs = row(conn, """
        SELECT (SELECT COUNT(*) FROM drivers WHERE accountid = :a AND stub = 1 AND deleted IS NULL) AS drivers,
               (SELECT COUNT(*) FROM vehicles WHERE accountid = :a AND stub = 1 AND deleted IS NULL) AS vehicles
    """, a=a)
    # No published rule set for the account's state: nothing can fail, so a clean result would mislead.
    # The account's own set does not count here: it is their policy, not the rules for their state,
    # and a clean result with no state rules loaded would still mislead.
    norules = not row(conn, "SELECT 1 AS x FROM rulesets WHERE state = :s AND status = 'published' "
                            "AND accountid IS NULL LIMIT 1", s=user["state"])
    return {"totals": totals, "risk": risk, "byreason": byreason, "drivers": drivers, "vehicles": vehicles,
            "monthly": monthly, "expiring": expiring, "unverifiedrules": unverified, "stubs": stubs,
            "norules": norules, "state": user["state"]}
