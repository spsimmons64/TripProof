###################################################################################################
# Notifications - computed from live data, never stored (see 005_notifications.sql). Only the read
# state is kept, per user and stable key.
#
#   staff      bursts of failed sign-ins, customers whose payment failed or whose fleet outgrew the priced plans
#   customers  credentials lapsing within 30 days, unbilled trips at risk, drivers who have just
#              finished an online application, imports waiting to be accepted, drivers/vehicles seen
#              only in trips, audit requests coming due
###################################################################################################
import json
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import events
from app.routers.dashboard import MVR_EXPIRING
from app.routers import driverapp
from app.db import get_conn, localnow, rows, run_many, utcnow
from app.security import current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

MAX_ITEMS = 50

# How often an unacknowledged problem asks again, in minutes. Short enough that a dispatcher who
# looked away cannot lose it; long enough that it is not the reason they stop listening.
NAG = 5


def _note(key, level, title, detail=None, link=None, at=None) -> dict:
    return {"key": key, "level": level, "title": title, "detail": detail, "link": link, "at": at}


def _money(v) -> str:
    return f"${float(v or 0):,.0f}"


def _staff(conn: Connection) -> list[dict]:
    out = []
    for r in rows(conn, """
        SELECT a.recordid, a.name, a.status, s.status AS substatus, s.pastduesince, s.lastpaymenterror
        FROM accounts a JOIN subscriptions s ON s.recordid = (
            SELECT s2.recordid FROM subscriptions s2 WHERE s2.accountid = a.recordid ORDER BY s2.status IN ('unpaid', 'canceled', 'incomplete_expired'), s2.startedon DESC, s2.added DESC LIMIT 1)
        WHERE a.deleted IS NULL AND s.status IN ('past_due', 'unpaid') ORDER BY s.pastduesince
    """):
        out.append(_note(f"pastdue:{r['recordid']}:{(r['pastduesince'] or utcnow()):%Y%m%d}", "bad", f"{r['name']}: payment failed",
                         r["lastpaymenterror"] or "Stripe is retrying the card.", "/admin/customers", r["pastduesince"]))
    for r in rows(conn, """
        SELECT a.recordid, a.name, COUNT(v.recordid) AS n, MAX(v.added) AS last FROM accounts a
        JOIN vehicles v ON v.accountid = a.recordid AND v.deleted IS NULL AND v.stub = 0
        WHERE a.deleted IS NULL AND a.platform = 0
          AND EXISTS (SELECT 1 FROM subscriptions s WHERE s.accountid = a.recordid AND s.status IN ('trialing', 'active', 'past_due'))
        GROUP BY a.recordid, a.name
        HAVING n > (SELECT COALESCE(MAX(maxvehicles), 2147483647) FROM plans WHERE active = 1 AND monthlyprice IS NOT NULL)
    """):
        out.append(_note(f"quote:{r['recordid']}:{r['n']}", "warn", f"{r['name']} has grown to {r['n']} vehicles",
                         "That's past the priced plans - they keep their current price until you quote them.",
                         "/admin/customers", r["last"]))
    since = utcnow() - timedelta(hours=24)
    failed = rows(conn, "SELECT COUNT(*) AS n, MAX(added) AS last FROM activitylog WHERE action = 'login-failed' AND added >= :s",
                  s=since)[0]
    if failed["n"] >= 5:
        out.append(_note(f"failedlogins:{since:%Y-%m-%d}", "bad", f"{failed['n']} failed sign-ins in the last 24 hours",
                         None, "/admin/users", failed["last"]))
    return out


def _customer(conn: Connection, user: dict) -> list[dict]:
    acct = user["accountid"]
    today = localnow(user["timezone"]).date()
    out = []

    # FIRST, above everything else on this list, because it is the only one with somebody standing
    # at the side of a road waiting for an answer. A credential lapsing in three weeks can be read
    # after lunch; a driver who has just reported a flat tyre on the way to a pickup cannot.
    now = utcnow()
    for i in rows(conn, """
        SELECT i.recordid, i.kind, i.note, i.raisedon, i.acknowledgedon, t.externalid, t.passenger,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM tripissues i
        JOIN trips t ON t.recordid = i.tripid AND t.deleted IS NULL
        LEFT JOIN drivers d ON d.recordid = i.driverid
        WHERE i.accountid = :a AND i.resolvedon IS NULL
        ORDER BY i.raisedon DESC LIMIT 25
    """, a=acct):
        who = (i["drivername"] or "A driver").strip()
        waiting = int(max(0, (now - i["raisedon"]).total_seconds()) // 60)
        # It goes on asking until somebody says they have seen it. Every notification else on this
        # list is read once and done with, because nothing is waiting on it; this one has a person
        # at the side of a road, so its key moves on every NAG minutes and the bell rings again.
        # Pressing Seen It stops the noise - which is what acknowledging a thing is for.
        key = (f"issue:{i['recordid']}" if i["acknowledgedon"]
               else f"issue:{i['recordid']}:{waiting // NAG}")
        since = ("just now" if waiting < 2 else f"{waiting} minutes ago" if waiting < 90
                 else f"{waiting // 60} hours ago")
        out.append(_note(key, "bad",
                         f"{who}: {driverapp.ISSUES.get(i['kind'], 'a problem')}",
                         " · ".join(x for x in (i["note"],
                                                f"{i['externalid']} · {i['passenger']}",
                                                f"reported {since}") if x),
                         "/dispatch?state=attention", i["raisedon"]))

    risk = rows(conn, """
        SELECT COUNT(*) AS n, COALESCE(SUM(billedamount), 0) AS amt FROM tripexposure
        WHERE accountid = :a AND billingstatus = 'unbilled'
    """, a=acct)[0]
    if risk["n"]:
        out.append(_note(f"atrisk:{today}:{risk['n']}", "bad", f"{risk['n']} unbilled trips are at risk",
                         f"{_money(risk['amt'])} would bill with a credential gap. Fix or hold them before billing.",
                         "/trips?status=fail&billing=unbilled"))

    # The newest credential of each type per holder, lapsing within 30 days and not yet renewed.
    for c in rows(conn, """
        SELECT c.recordid, c.subject, c.subjectid, c.expireson, t.name AS typename,
               CASE c.subject WHEN 'driver' THEN CONCAT(d.firstname, ' ', d.lastname)
                              WHEN 'vehicle' THEN COALESCE(v.externalid, v.vin) ELSE 'Company' END AS holder
        FROM credentials c
        JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        LEFT JOIN drivers d ON c.subject = 'driver' AND d.recordid = c.subjectid
        LEFT JOIN vehicles v ON c.subject = 'vehicle' AND v.recordid = c.subjectid
        WHERE c.accountid = :a AND c.deleted IS NULL AND c.revokedon IS NULL
          AND c.expireson BETWEEN :today AND :horizon
          AND NOT EXISTS (SELECT 1 FROM credentials n
                          WHERE n.accountid = c.accountid AND n.subject = c.subject AND n.subjectid = c.subjectid
                            AND n.credentialtypeid = c.credentialtypeid AND n.deleted IS NULL AND n.issuedon > c.issuedon)
        ORDER BY c.expireson LIMIT 25
    """, a=acct, today=today, horizon=today + timedelta(days=30)) + rows(
            conn, MVR_EXPIRING, a=acct, today=today, horizon=today + timedelta(days=30)):
        days = (c["expireson"] - today).days
        link = "/company" if c["subject"] == "company" else f"/{c['subject']}s/{c['subjectid']}"
        out.append(_note(f"expiring:{c['recordid']}", "warn" if days > 7 else "bad",
                         f"{c['holder']}: {c['typename']} expires {'today' if days == 0 else f'in {days} days'}",
                         f"Expires {c['expireson']:%m/%d/%Y}. Trips after that will fail until it is renewed.", link))

    # A screening that has come back and not been read.
    #
    # It arrives on its own - fetched by the sweep, or by a webhook - so nobody in the office knows
    # unless they are told. Until somebody reads it the driver stays blocked by a requirement that
    # has in fact been met, which is the worst kind of waiting: the work is done and nothing
    # happens because of it.
    for r in rows(conn, """
        SELECT r.recordid, r.driverid, r.receivedon, r.tier, r.outcome,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM driverreports r
        JOIN drivers d ON d.recordid = r.driverid AND d.deleted IS NULL
        WHERE r.accountid = :a AND r.code = 'BACKGROUND_SCREENING'
          AND r.receivedon IS NOT NULL AND r.reviewstate = 'pending'
        ORDER BY r.receivedon DESC LIMIT 25
    """, a=acct):
        name = (r["drivername"] or "A driver").strip().title()
        out.append(_note(f"screening:{r['recordid']}", "info",
                         f"{name}: the background check has come back",
                         "Nobody has read it yet. The driver stays short of this requirement "
                         "until somebody does.",
                         f"/drivers/{r['driverid']}", r["receivedon"]))

    # An assigned trip in the coming week whose driver no longer qualifies for it, by the newest
    # check on that leg. Something lapsed or came back since it was booked, and the trip is still
    # on the board with their name on it.
    for e in rows(conn, """
        SELECT e.legid, e.blockers, e.evaluatedfor, t.externalid,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM tripeligibility e
        JOIN (SELECT legid, MAX(evaluatedon) AS latest FROM tripeligibility
              WHERE accountid = :a AND legid IS NOT NULL GROUP BY legid) m
          ON m.legid = e.legid AND m.latest = e.evaluatedon
        JOIN triplegs l ON l.recordid = e.legid AND l.driverid = e.driverid
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL AND t.cancelledon IS NULL
        LEFT JOIN drivers d ON d.recordid = e.driverid
        WHERE e.accountid = :a AND e.decision = 'notqualified'
          AND l.pickupat BETWEEN UTC_TIMESTAMP() AND UTC_TIMESTAMP() + INTERVAL 7 DAY
        ORDER BY l.pickupat LIMIT 25
    """, a=acct):
        why = (json.loads(e["blockers"] or "[]") or [{}])[0]
        out.append(_note(f"tripcheck:{e['legid']}:{e['evaluatedfor']:%Y%m%d}", "bad",
                         f"Trip {e['externalid']}: {(e['drivername'] or 'the driver').title()} "
                         f"no longer qualifies",
                         " - ".join(x for x in (why.get("name"), why.get("reason")) if x),
                         "/dispatch", e["evaluatedfor"]))

    # A driving record that has come back and not been read. The same reason as the screening above:
    # until somebody reads it, the driver stays short of the requirement it answers.
    for m in rows(conn, """
        SELECT m.recordid, m.driverid, m.receivedon, l.state, l.number,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM drivermvrs m
        JOIN drivers d ON d.recordid = m.driverid AND d.deleted IS NULL
        LEFT JOIN driverlicenses l ON l.recordid = m.licenseid
        WHERE m.accountid = :a AND m.receivedon IS NOT NULL AND m.cancelledon IS NULL
          AND m.norecord = 0 AND m.reviewstate = 'pending'
        ORDER BY m.receivedon DESC LIMIT 25
    """, a=acct):
        name = (m["drivername"] or "A driver").strip().title()
        lic = f' for {m["state"]} {m["number"]}' if m["state"] else ""
        out.append(_note(f"mvr:{m['recordid']}", "info",
                         f"{name}: the motor vehicle record{lic} has come back",
                         "Nobody has read it yet. The driver stays short of this requirement "
                         "until somebody does.",
                         f"/drivers/{m['driverid']}", m["receivedon"]))

    # A driver who has finished their online application and is waiting for the office to look.
    for d in rows(conn, """
        SELECT d.recordid, d.firstname, d.lastname, d.drivernumber, ap.submittedon
        FROM drivers d JOIN driverapplications ap ON ap.driverid = d.recordid
        WHERE d.accountid = :a AND d.deleted IS NULL AND d.status = 'new' AND ap.status = 'submitted'
        ORDER BY ap.submittedon DESC LIMIT 25
    """, a=acct):
        name = f"{d['firstname']} {d['lastname']}".title()
        out.append(_note(f"application:{d['recordid']}:{d['submittedon']:%Y%m%d%H%M}", "info",
                         f"{name} has applied to drive",
                         f"Driver {d['drivernumber']} finished their application. Nothing has been reviewed yet.",
                         f"/drivers/{d['recordid']}", d["submittedon"]))

    for b in rows(conn, """
        SELECT recordid, filename, tripcount, added FROM importbatches
        WHERE accountid = :a AND status = 'staged' ORDER BY added DESC
    """, a=acct):
        out.append(_note(f"import:{b['recordid']}", "info", f"Import “{b['filename']}” is waiting to be accepted",
                         f"{b['tripcount']} trips staged. Nothing is checked until you accept it.", "/import", b["added"]))

    stubs = rows(conn, """
        SELECT (SELECT COUNT(*) FROM drivers WHERE accountid = :a AND stub = 1 AND deleted IS NULL) AS d,
               (SELECT COUNT(*) FROM vehicles WHERE accountid = :a AND stub = 1 AND deleted IS NULL) AS v
    """, a=acct)[0]
    if stubs["d"] or stubs["v"]:
        out.append(_note(f"stubs:{stubs['d']}:{stubs['v']}", "warn",
                         f"{stubs['d']} drivers and {stubs['v']} vehicles need their details",
                         "They appeared in a trip import with nothing on file, so every trip they ran is at risk.",
                         "/drivers" if stubs["d"] else "/vehicles"))

    # Work that came back on its own - a driver signing from a link, an application submitted.
    # Nobody in the office made it happen, so nobody in the office knows unless they are told.
    for e in rows(conn, f"""
        SELECT seq, subject, subjectid, kind, label, createdon FROM events
        WHERE accountid = :a AND kind IN ({", ".join(f"'{k}'" for k in events.ARRIVED)})
          AND createdon >= UTC_TIMESTAMP() - INTERVAL 7 DAY
        ORDER BY seq DESC LIMIT 20
    """, a=acct):
        out.append(_note(f"arrived:{e['seq']}", "good", e["label"] or "Something was returned",
                         None, f"/drivers/{e['subjectid']}" if e["subject"] == "driver" else None,
                         at=e["createdon"]))

    for a in rows(conn, """
        SELECT recordid, requester, reference, dueon FROM auditrequests
        WHERE accountid = :a AND status = 'open' AND dueon IS NOT NULL AND dueon <= :horizon ORDER BY dueon
    """, a=acct, horizon=today + timedelta(days=14)):
        days = (a["dueon"] - today).days
        when = "is overdue" if days < 0 else ("is due today" if days == 0 else f"is due in {days} days")
        out.append(_note(f"audit:{a['recordid']}:{a['dueon']}", "bad" if days <= 3 else "warn",
                         f"Audit request from {a['requester']} {when}", a["reference"], f"/audits/{a['recordid']}"))
    return out


@router.get("")
def notifications(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    staff = user.get("platformrole") and not user.get("launched")
    items = (_staff(conn) if staff else _customer(conn, user))[:MAX_ITEMS]
    read = {r["notekey"] for r in rows(conn, "SELECT notekey FROM notificationreads WHERE userid = :u", u=user["recordid"])}
    for n in items:
        n["read"] = n["key"] in read
    return {"unread": sum(1 for n in items if not n["read"]), "items": items}


class ReadIn(BaseModel):
    keys: list[str]


@router.post("/read")
def mark_read(body: ReadIn, user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    keys = [k[:128] for k in body.keys[:MAX_ITEMS]]
    run_many(conn, "INSERT IGNORE INTO notificationreads (userid, notekey) VALUES (:u, :k)",
             [{"u": user["recordid"], "k": k} for k in keys])
    return {"ok": True}
