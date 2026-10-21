###################################################################################################
# Collecting background screenings that have finished.
#
# A screening is ordered and then nobody hears anything. backgroundchecks.com publishes no way to
# register a callback through their API - whatever webhook they offer is configured in their own
# web console, and an integration must not depend on something it cannot see or set - so TripProof
# goes and asks.
#
# Without this the only thing that moves a finished report onto a driver's file is somebody
# opening the driver and pressing Check For The Result. A report can therefore sit complete at the
# vendor for a week while the office believes it is still running, and a driver who is in fact
# cleared stays blocked by a requirement that has already been met. That is the failure this job
# exists to prevent.
#
# It is deliberately dull: walk the orders that are open, ask about each one, and land the ones
# that have finished. The landing itself is `vault._land_screening`, the same code the button and
# the webhook use - three roads to one place, so a report filed by this job is indistinguishable
# from one filed by hand.
###################################################################################################
import logging

from sqlalchemy.engine import Connection

from app import backgroundchecks, screeningaccount
from app.db import rows, utcnow

log = logging.getLogger("tripproof.screeningsweep")


def collect(conn: Connection) -> dict:
    """Ask about every open screening and file the ones that are done.

    Returns a count of what happened, for the log and for whoever runs it by hand."""
    open_orders = rows(conn, """
        SELECT r.recordid, r.accountid, r.driverid, r.vendorref, r.vendorstatus,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS drivername
        FROM driverreports r
        JOIN drivers d ON d.recordid = r.driverid AND d.deleted IS NULL
        WHERE r.code = 'BACKGROUND_SCREENING' AND r.vendor = 'backgroundchecks'
          AND r.vendorref IS NOT NULL AND r.receivedon IS NULL
        ORDER BY r.orderedon
    """)
    out = {"looked": 0, "landed": 0, "waiting": 0, "failed": 0, "unreachable": 0}
    # One token per account rather than one per order: a company with forty open screenings should
    # not have its credential unsealed forty times.
    keys: dict[str, str | None] = {}
    # Imported here rather than at the top: vault imports half the application, and a sweep that
    # drags all of it in at start-up is a sweep that fails for reasons nothing to do with it.
    from app.routers.vault import _land_screening

    for order in open_orders:
        acct = order["accountid"]
        if acct not in keys:
            keys[acct] = screeningaccount.token_for(conn, acct)
        token = keys[acct]
        if not token:
            # The company has disconnected its account since ordering. Their order is still theirs
            # and still running; we simply have no key to ask about it with any more.
            continue
        out["looked"] += 1
        try:
            got = backgroundchecks.fetch(order["vendorref"], token)
        except backgroundchecks.ScreeningError as e:
            out["unreachable"] += 1
            log.warning("could not ask about %s for %s: %s",
                        order["vendorref"], order["drivername"], e)
            continue
        status = got["status"]
        if status in ("running", "waiting"):
            out["waiting"] += 1
            # Still records that we asked, so a stalled order can be told from an unexamined one.
            _touch(conn, order["recordid"], status)
            continue
        _land_screening(conn, acct, order["driverid"], order["recordid"], order["vendorref"],
                        status, "backgroundchecks")
        out["failed" if status == "failed" else "landed"] += 1
        log.info("screening %s for %s came back %s", order["vendorref"],
                 order["drivername"], status)
    return out


def _touch(conn: Connection, recordid: str, status: str) -> None:
    from app.db import run
    run(conn, "UPDATE driverreports SET vendorstatus = :s, lastsyncedon = :now "
              "WHERE recordid = :id", s=status, now=utcnow(), id=recordid)
