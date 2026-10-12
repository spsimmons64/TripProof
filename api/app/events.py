###################################################################################################
# Things having changed.
#
# An event is written in the same transaction as the change that caused it, so there is no state in
# which the change happened and the event did not. It says what changed and nothing about what it
# changed to: a client that hears "this driver changed" goes and asks, through the endpoints that
# already decide what it may see.
#
# That restraint is the whole design. A feed carrying content is a second copy of the truth, which
# has to be kept in step, access-controlled all over again, and audited separately. A feed carrying
# ids is a doorbell.
###################################################################################################
from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run

# How long the feed keeps what it has heard. A client that has been away longer than this asks for
# everything it cares about instead, which is what it does on first load anyway.
KEEP_HOURS = 48


# What counts as something arriving - work the office was waiting on that has come back. These are
# the ones worth interrupting somebody for; everything else is a nudge to refetch and nothing more.
# A document the driver sent in belongs here for the same reason a signature does: it arrived on
# its own, nobody asked it to land at that moment, and it is waiting to be read.
ARRIVED = ("signed", "application-submitted", "report-returned", "uploaded")


def record(conn: Connection, accountid: str | None, subject: str, subjectid: str | None,
           kind: str = "changed", detail: str | None = None, label: str | None = None) -> None:
    """Note that something changed. Never raises: a feed nobody is listening to must not be able to
    take down the change it is describing."""
    if not accountid:
        return
    try:
        run(conn, """
            INSERT INTO events (recordid, accountid, subject, subjectid, kind, detail, label)
            VALUES (:id, :a, :s, :sid, :k, :d, :l)
        """, id=newid(), a=accountid, s=subject[:24], sid=subjectid, k=kind[:48],
            d=(detail or None) and detail[:255], l=(label or None) and label[:160])
        # Something that arrived on its own is also work: it goes in the inbox, which outlives the
        # feed and remembers whether anybody has read it.
        if kind in ARRIVED:
            run(conn, """
                INSERT INTO arriveddocuments (recordid, accountid, subject, subjectid, kind, detail, label)
                VALUES (:id, :a, :s, :sid, :k, :d, :l)
            """, id=newid(), a=accountid, s=subject[:24], sid=subjectid, k=kind[:48],
                d=(detail or None) and detail[:255], l=(label or None) and label[:160])
    except Exception:                       # noqa: BLE001 - deliberately swallowed, see above
        pass


def arrived(conn: Connection, accountid: str, driverid: str | None, code: str,
            label: str) -> None:
    """Something made outside this office has landed on a driver's file.

    The alert, the toast and the needs-review state are one event, not three things that have to be
    remembered separately. This writes the first two in the same transaction as the record itself;
    the third needs nothing written at all, because a rule whose evidence comes from outside is
    unread until there is a row in `documentreads` saying otherwise - so the moment the record
    exists it is already in review. They cannot drift apart because they are not kept apart."""
    record(conn, accountid, "driver", driverid, "report-returned", code, label=label)


def waiting_to_be_read(conn: Connection, accountid: str, limit: int = 200) -> list[dict]:
    """What has come in and not been looked at, oldest first - a queue is worked from the front."""
    return rows(conn, """
        SELECT a.recordid, a.subject, a.subjectid, a.kind, a.detail, a.label, a.arrivedon,
               d.firstname, d.lastname
        FROM arriveddocuments a
        LEFT JOIN drivers d ON d.recordid = a.subjectid AND a.subject = 'driver'
        WHERE a.accountid = :a AND a.reviewedon IS NULL
        ORDER BY a.arrivedon LIMIT :n
    """, a=accountid, n=limit)


def mark_read(conn: Connection, accountid: str, recordid: str, userid: str) -> int:
    """One arrival, read. Only ever the account's own, and only ever once."""
    return run(conn, """
        UPDATE arriveddocuments SET reviewedon = UTC_TIMESTAMP(), reviewedby = :u
        WHERE recordid = :id AND accountid = :a AND reviewedon IS NULL
    """, u=userid, id=recordid, a=accountid).rowcount


def read_arrivals(conn: Connection, accountid: str, subject: str, subjectid: str,
                  code: str | None = None) -> int:
    """Clear the inbox entries one reading answers.

    The arrival and the needs-review state went in together, so they come out together: an item
    that has gone green must not still be sitting in somebody's alerts."""
    where = "accountid = :a AND subject = :s AND subjectid = :sid AND reviewedon IS NULL"
    params = {"a": accountid, "s": subject, "sid": subjectid}
    if code:
        where += " AND detail = :c"
        params["c"] = code
    return run(conn, f"UPDATE arriveddocuments SET reviewedon = UTC_TIMESTAMP() WHERE {where}",
               **params).rowcount


def since(conn: Connection, accountid: str, cursor: int | None, subject: str | None = None,
          subjectid: str | None = None, limit: int = 200) -> dict:
    """What has happened for this account since the cursor, and where the cursor is now.

    With no cursor the caller is starting: they are told where the end is, and nothing else, because
    they have just read the current state by other means."""
    here = row(conn, "SELECT COALESCE(MAX(seq), 0) AS seq FROM events WHERE accountid = :a",
               a=accountid)["seq"]
    if cursor is None:
        return {"cursor": here, "events": []}
    where = ["accountid = :a", "seq > :c"]
    if subject:
        where.append("subject = :s")
    if subjectid:
        where.append("subjectid = :sid")
    found = rows(conn, f"""
        SELECT seq, subject, subjectid, kind, detail, label, createdon
        FROM events WHERE {' AND '.join(where)}
        ORDER BY seq LIMIT :n
    """, a=accountid, c=cursor, s=subject, sid=subjectid, n=limit)
    return {"cursor": found[-1]["seq"] if found else max(cursor, here), "events": found}


def prune(conn: Connection) -> int:
    """Forget what is too old to be news."""
    return run(conn, """
        DELETE FROM events WHERE createdon < UTC_TIMESTAMP() - INTERVAL :h HOUR
    """, h=KEEP_HOURS).rowcount
