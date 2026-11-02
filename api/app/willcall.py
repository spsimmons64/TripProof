"""The on-call driver's texts, and the office's dispatch alerts.

The driver on call is texted once when on call begins, with the will-calls waiting, and once as each
will-call comes due (its Ready About time) - so a return is not waiting on somebody who does not know
it is there. Trip references and times only, as every text to a driver is; each text is written down
once (oncalltexts), so a restart never sends another.

How a will-call reaches the provider is the broker's business or the passenger's - the broker's
Ride Assist, the facility, the passenger ringing the company's own number. Whoever takes it records
it (Passenger Called in the office, I'm Going in the driver app).
"""

import logging
import threading
import time as clock
from datetime import datetime, timedelta

from sqlalchemy.engine import Connection

from app import dispatch, sms
from app import shifts as plan
from app.config import settings
from app.db import engine, localnow, rows, run, saved, utcnow

logger = logging.getLogger(__name__)

TICK = 60                  # how often the on-call texts are looked for


def on_call_now(conn: Connection, acct: str, here: datetime, lead: timedelta = timedelta(0)) -> list[dict]:
    """The on-call assignments running now (or starting within `lead`), with each driver's phone."""
    out = []
    for s in plan.on_call(conn, acct, here.date() - timedelta(days=1)) + plan.on_call(conn, acct, here.date()):
        s["from"], s["until"] = plan.span(s["workday"], s["startsat"], s["endsat"])
        if s["from"] - lead <= here < s["until"]:
            out.append(s)
    return sorted(out, key=lambda s: s["from"])


# ------------------------------------------------------------------------------------------------
# The on-call driver's texts
# ------------------------------------------------------------------------------------------------
def _once(conn: Connection, key: str, acct: str, driverid: str, legid: str | None = None) -> bool:
    """Write down that this text is going; False if it already went."""
    return bool(run(conn, "INSERT IGNORE INTO oncalltexts (dedupe, accountid, driverid, legid, senton) "
                          "VALUES (:k, :a, :d, :l, :now)", k=key[:160], a=acct, d=driverid, l=legid,
                    now=utcnow()).rowcount)


def tick(conn: Connection) -> int:
    """One look round every company with somebody on call: the start-of-on-call text, and a text
    for each will-call that has come due. Returns how many were queued."""
    from app.routers.driverapp import _waiting_calls
    sent = 0
    for a in rows(conn, "SELECT DISTINCT accountid FROM oncall WHERE workday >= :d",
                  d=utcnow().date() - timedelta(days=2)):
        acct = a["accountid"]
        here = localnow(dispatch.zone(conn, acct))
        for s in on_call_now(conn, acct, here):
            waiting = _waiting_calls(conn, acct, s["from"].date())
            if _once(conn, f"start:{s['recordid']}:{s['from']:%Y%m%d%H%M}", acct, s["driverid"]):
                due = ", ".join(f"{w['externalid']}" + (f" ready ~{w['readyabout']:%-I:%M %p}" if w["readyabout"] else "")
                                for w in waiting[:4])
                sms.tell(conn, acct, s["driverid"], "oncall",
                         f"You are on call in {s['vehiclename']} until {s['until']:%-I:%M %p}. "
                         + (f"{len(waiting)} will-call{'s' if len(waiting) != 1 else ''} waiting: {due}." if waiting
                            else "No will-calls waiting."))
                sent += 1
            for w in waiting:
                if w["readyabout"] and w["readyabout"] <= here and _once(
                        conn, f"due:{s['recordid']}:{w['legid']}", acct, s["driverid"], w["legid"]):
                    sms.tell(conn, acct, s["driverid"], "willcalldue",
                             f"Will-call {w['externalid']} is due about now (ready ~{w['readyabout']:%-I:%M %p}). "
                             f"Watch for the call, or open the app to call them.", w["tripid"], w["legid"])
                    sent += 1
    return sent


# ------------------------------------------------------------------------------------------------
# Dispatch alerts: the office texted when a flag on the board has stood unanswered
# ------------------------------------------------------------------------------------------------
CALL_LATE = timedelta(minutes=30)          # past Ready About with no call recorded (Call Overdue)
NO_DRIVER = timedelta(minutes=30)          # before pickup with nobody on it
COVER_BY = timedelta(minutes=60)           # before closing with no coverage recorded
FACILITY_BY = timedelta(minutes=30)        # before a facility closes with a passenger still waiting

def office_alerts(conn: Connection) -> int:
    """One look round every company with somebody taking dispatch alerts: each will-call gone
    quiet, each trip about to pick up with no driver, each will-call with no coverage near
    closing - texted once to each of them. Returns how many were queued."""
    from app.routers.shifts import company_hours
    sent = 0
    for a in rows(conn, "SELECT DISTINCT accountid FROM users WHERE dispatchalerts = 1 AND mobile IS NOT NULL "
                        "AND deleted IS NULL AND platformrole IS NULL"):
        acct = a["accountid"]
        here = localnow(dispatch.zone(conn, acct))
        today = here.date()
        h = company_hours(conn, acct, today)
        if h and h.get("closed"):
            continue
        opens, closes = plan.span(today, h["open"], h["close"]) if h else (None, None)
        open_now = not h or opens <= here < closes
        said = []                                                  # (kind, legid, tripid, text)
        handed = "t.brokerstate NOT IN ('offered', 'returnpending', 'returned') AND l.brokerstate IS NULL"
        if open_now:
            for l in rows(conn, f"""
                SELECT l.recordid, l.tripid, l.readyabout, t.externalid FROM triplegs l JOIN trips t ON t.recordid = l.tripid
                WHERE l.accountid = :a AND t.deleted IS NULL AND t.cancelledon IS NULL AND t.tripdate = :d
                  AND l.pickupat IS NULL AND l.outcomestate IS NULL AND {handed} AND l.readyabout < :late
            """, a=acct, d=today, late=here.replace(tzinfo=None) - CALL_LATE):
                said.append(("alertcall", l["recordid"], l["tripid"],
                             f"Will-call {l['externalid']} was to be ready about {l['readyabout']:%-I:%M %p} "
                             f"and no call is recorded. Check Dispatch."))
            for l in rows(conn, f"""
                SELECT l.recordid, l.tripid, l.pickupat, t.externalid FROM triplegs l JOIN trips t ON t.recordid = l.tripid
                WHERE l.accountid = :a AND t.deleted IS NULL AND t.cancelledon IS NULL AND t.tripdate = :d
                  AND l.pickupat IS NOT NULL AND l.driverid IS NULL AND l.outcomestate IS NULL
                  AND l.executionstate = 'scheduled' AND {handed} AND l.pickupat < :soon
            """, a=acct, d=today, soon=here.replace(tzinfo=None) + NO_DRIVER):
                said.append(("alertdriver", l["recordid"], l["tripid"],
                             f"Trip {l['externalid']} picks up at {l['pickupat']:%-I:%M %p} and has no driver."))
        if closes and closes - COVER_BY <= here < closes + timedelta(hours=3):
            for l in rows(conn, f"""
                SELECT l.recordid, l.tripid, t.externalid FROM triplegs l JOIN trips t ON t.recordid = l.tripid
                WHERE l.accountid = :a AND t.deleted IS NULL AND t.cancelledon IS NULL AND t.tripdate = :d
                  AND l.pickupat IS NULL AND l.outcomestate IS NULL AND {handed}
                  AND COALESCE(l.responsibility, 'provider') IN ('provider', 'unconfirmed')
                  AND NOT EXISTS (SELECT 1 FROM returncoverage rc WHERE rc.legid = l.recordid)
            """, a=acct, d=today):
                said.append(("alertcover", l["recordid"], l["tripid"],
                             f"Will-call {l['externalid']} has no coverage recorded and you close at "
                             f"{closes:%-I:%M %p}."))
        # A passenger still waiting at a place about to lock up, whatever the company's own hours.
        for l in rows(conn, f"""
            SELECT l.recordid, l.tripid, t.externalid, p.closesat FROM triplegs l JOIN trips t ON t.recordid = l.tripid
            JOIN places p ON p.accountid = l.accountid AND p.deleted IS NULL AND p.closesat IS NOT NULL
             AND CONCAT_WS(', ', p.address, p.city, CONCAT_WS(' ', p.state, p.zip)) = l.pickupplace
            WHERE l.accountid = :a AND t.deleted IS NULL AND t.cancelledon IS NULL AND t.tripdate = :d
              AND l.pickupat IS NULL AND l.outcomestate IS NULL AND {handed}
              AND COALESCE(l.responsibility, 'provider') IN ('provider', 'unconfirmed')
              AND TIMESTAMP(t.tripdate, p.closesat) - INTERVAL :w MINUTE <= :here
        """, a=acct, d=today, w=int(FACILITY_BY.total_seconds() // 60), here=here.replace(tzinfo=None)):
            said.append(("alertclosing", l["recordid"], l["tripid"],
                         f"Will-call {l['externalid']} is still waiting and its pickup place closes at "
                         f"{plan.as_time(l['closesat']):%-I:%M %p}."))
        if not said:
            continue
        for u in rows(conn, "SELECT recordid FROM users WHERE accountid = :a AND dispatchalerts = 1 "
                            "AND mobile IS NOT NULL AND deleted IS NULL AND platformrole IS NULL", a=acct):
            for kind, legid, tripid, body in said:
                # Written down once per person and trip (oncalltexts holds the user in driverid).
                if _once(conn, f"{kind}:{legid}:{u['recordid']}", acct, u["recordid"], legid):
                    sms.tell_user(conn, acct, u["recordid"], kind, body, tripid, legid)
                    sent += 1
    return sent


def _loop() -> None:
    while True:
        try:
            with engine.connect() as conn:
                conn.info.pop("after_commit", None)
                tick(conn)
                office_alerts(conn)
                saved(conn)
        except Exception:                                                     # noqa: BLE001
            logger.exception("on-call texts")
        clock.sleep(TICK)


def start() -> None:
    """Run the on-call texts and dispatch alerts in the background, once a minute, for the life of the API."""
    if settings.oncall_texts:
        threading.Thread(target=_loop, name="oncall-texts", daemon=True).start()
