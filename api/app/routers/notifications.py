###################################################################################################
# Notifications - computed from live data, never stored (see 005_notifications.sql). Only the read
# state is kept, per user and stable key.
#
#   staff      bursts of failed sign-ins, customers whose payment failed or whose fleet outgrew the priced plans
#   customers  credentials lapsing within 30 days, unbilled trips at risk, drivers who have just
#              finished an online application, imports waiting to be accepted, drivers/vehicles seen
#              only in trips, audit requests coming due
###################################################################################################
from datetime import timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import events
from app.db import get_conn, localnow, rows, run_many, utcnow
from app.security import current_user

router = APIRouter(prefix="/api/notifications", tags=["notifications"])

MAX_ITEMS = 50


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
    """, a=acct, today=today, horizon=today + timedelta(days=30)):
        days = (c["expireson"] - today).days
        link = "/company" if c["subject"] == "company" else f"/{c['subject']}s/{c['subjectid']}"
        out.append(_note(f"expiring:{c['recordid']}", "warn" if days > 7 else "bad",
                         f"{c['holder']}: {c['typename']} expires {'today' if days == 0 else f'in {days} days'}",
                         f"Expires {c['expireson']:%m/%d/%Y}. Trips after that will fail until it is renewed.", link))

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
