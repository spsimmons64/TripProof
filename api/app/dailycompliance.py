###################################################################################################
# The daily reconciliation.
#
# The engine answers live, so nothing has to be recomputed for the screens. What a live answer
# cannot do is say what the file looked like last Tuesday, or notice that a driver booked for
# Thursday stopped qualifying overnight because something lapsed. So once a day:
#
#   1. each pending and hired driver's standing per program is kept as a snapshot;
#   2. every assigned trip in the next seven days is checked again against the file as it stands,
#      and the check is kept - the bell reads the newest one per leg.
###################################################################################################
import json
from datetime import timedelta

from sqlalchemy.engine import Connection

from app import facts as factset
from app import qualification, rules, tripcheck
from app.db import newid, rows, run, utcnow

AHEAD = timedelta(days=7)


def snapshot(conn: Connection) -> int:
    today = utcnow().date()
    taken = 0
    for d in rows(conn, """
        SELECT d.recordid, d.accountid, d.status FROM drivers d JOIN accounts a ON a.recordid = d.accountid
        WHERE d.deleted IS NULL AND d.stub = 0 AND d.terminatedon IS NULL
          AND d.status IN ('pending', 'hired')
    """):
        facts = factset.assemble(conn, d["accountid"], d["recordid"])["facts"]
        items = rules.for_driver(conn, d["accountid"], d["recordid"], facts, today=today)
        for p in qualification.overview(d, items, facts)["programs"]:
            run(conn, """
                INSERT INTO programqualificationsnapshots (recordid, accountid, driverid, program,
                                                           status, reasons, takenon, takenat)
                VALUES (:id, :a, :d, :p, :s, :r, :on, :at)
                ON DUPLICATE KEY UPDATE status = :s, reasons = :r, takenat = :at
            """, id=newid(), a=d["accountid"], d=d["recordid"], p=p["program"], s=p["status"],
                r=json.dumps(p["reasons"]), on=today, at=utcnow())
            taken += 1
    return taken


def sweep(conn: Connection) -> dict:
    now = utcnow()
    out = {"checked": 0, "notqualified": 0}
    for leg in rows(conn, """
        SELECT l.recordid, l.accountid, l.driverid, l.vehicleid FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid
        WHERE l.driverid IS NOT NULL AND l.pickupat BETWEEN :now AND :until
          AND t.deleted IS NULL AND t.cancelledon IS NULL
    """, now=now, until=now + AHEAD):
        got = tripcheck.check(conn, leg["accountid"], leg["driverid"], leg["vehicleid"],
                              legid=leg["recordid"], shadow=True)
        out["checked"] += 1
        out["notqualified"] += got["decision"] == "notqualified"
    return out


def daily(conn: Connection) -> dict:
    return {"snapshots": snapshot(conn), **sweep(conn)}
