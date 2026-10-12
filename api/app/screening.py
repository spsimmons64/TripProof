###################################################################################################
# Monthly exclusion screening.
#
# An excluded driver is the compliance failure that costs money backwards: every trip they carried
# becomes an overpayment, whether or not anybody knew. OIG republishes the list monthly, by the
# 10th, so a screening from eight weeks ago can be wrong without anybody having done anything - the
# driver did not change, the list did. Which is why this runs on a clock.
#
# HOW IT WORKS, AND WHY IT IS A FILE RATHER THAN AN API
#
# There is no OIG API. Their own FAQ: "No, there are no plans for a public API." The list is a CSV
# republished monthly at a fixed URL, so the job downloads it, records exactly which file it got,
# and matches every driver against it in memory.
#
# That is better than an API would be, for this. We hold the list, so the whole roster can be
# re-screened the moment a new file drops, and the evidence is a dataset anybody can fetch again
# and check us against.
#
# WHAT THE MACHINE CANNOT FINISH
#
# The downloadable file carries no SSN and no EIN - the Privacy Act forbids publishing them - so a
# name match is a CANDIDATE, never a confirmation. OIG says so plainly: "It is not sufficient to
# simply find a matching first and last name on the LEIE." Confirmation happens on their online
# form, against the SSN, by a person, and the evidence is a screenshot.
#
# So this writes `clear` or `potential`, and never `confirmed`. A potential match is work for a
# human, and the driver is not accused of anything by it - names repeat.
###################################################################################################
import csv
import hashlib
import io
import json
import urllib.request
from datetime import date, datetime

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run, utcnow

# The full database, replaced in place every month. There are monthly delta files beside it, but
# the guidance is explicit that you use one or the other and never both, and a full match is
# cheaper to reason about than a diff that has to be right about what it missed.
LEIE_URL = "https://oig.hhs.gov/exclusions/downloadables/UPDATED.csv"

# Below this, assume the download was truncated or the URL now serves an error page rather than a
# list. Screening every driver clear against a broken file is worse than not screening at all.
LEIE_MIN_ROWS = 50_000

SOURCE = "OIG_LEIE"


def fetch(url: str = LEIE_URL, timeout: int = 180) -> dict:
    """Download the list and pin exactly what was downloaded."""
    req = urllib.request.Request(url, headers={"User-Agent": "TripProof/1.0 exclusion screening"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        stamp = r.headers.get("Last-Modified")
    return {"body": body, "stamp": stamp, "bytes": len(body),
            "sha": hashlib.sha256(body).hexdigest()}


def fetch_stamp(url: str = LEIE_URL, timeout: int = 30) -> str | None:
    """Which list is published right now, without downloading 15 MB to find out."""
    req = urllib.request.Request(url, method="HEAD",
                                 headers={"User-Agent": "TripProof/1.0 exclusion screening"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.headers.get("Last-Modified")
    except Exception:
        return None                   # unreachable: fall through and let the real download report


def _norm(value: str | None) -> str:
    return " ".join((value or "").strip().upper().split())


def index(body: bytes) -> dict[tuple[str, str], list[dict]]:
    """The list, keyed by last and first name.

    Keyed on name because that is all the file gives us to key on - it holds no SSN. The date of
    birth rides along on each row and is what tells a real match from a namesake, so it is kept
    beside the entry rather than folded into the key."""
    held: dict[tuple[str, str], list[dict]] = {}
    reader = csv.DictReader(io.StringIO(body.decode("utf-8-sig", errors="replace")))
    for entry in reader:
        last, first = _norm(entry.get("LASTNAME")), _norm(entry.get("FIRSTNAME"))
        if not last or not first:
            continue                      # a business row - it has BUSNAME instead
        held.setdefault((last, first), []).append({
            "lastname": last, "firstname": first, "middle": _norm(entry.get("MIDNAME")),
            "dob": _norm(entry.get("DOB")), "npi": _norm(entry.get("NPI")),
            "state": _norm(entry.get("STATE")), "general": _norm(entry.get("GENERAL")),
            "excltype": _norm(entry.get("EXCLTYPE")), "excldate": _norm(entry.get("EXCLDATE")),
        })
    return held


def _dob_matches(driver_dob: date | None, listed: str) -> bool | None:
    """None when the list gives no birth date - which is common, and is not a ruling-out."""
    if not driver_dob or not listed or len(listed) != 8 or not listed.isdigit():
        return None
    return listed == driver_dob.strftime("%Y%m%d")


def screen(conn: Connection, held: dict, runid: str | None = None,
           performedby: str = "tripproof") -> dict:
    """Screen every driver on the platform, and record the clean ones too.

    Every driver who has not been deleted, including drivers who were never hired: somebody in the
    application pipeline is exactly who you want to catch before they are on the roster."""
    counted = {"clear": 0, "potential": 0}
    for driver in rows(conn, """
        SELECT recordid, accountid, firstname, lastname, dob
        FROM drivers WHERE deleted IS NULL
    """):
        last, first = _norm(driver["lastname"]), _norm(driver["firstname"])
        if not last or not first:
            continue
        # Only the name we hold. A driver's former or maiden names are not recorded anywhere yet,
        # and OIG holds only the name known at the time of exclusion - so this is a floor, not a
        # complete search, and the record says which names were actually tried.
        names = [f"{last}, {first}"]
        candidates = []
        for entry in held.get((last, first), []):
            candidates.append({**entry, "dobmatch": _dob_matches(driver["dob"], entry["dob"])})

        # A namesake with a different birth date on the list is not this person. Where the list
        # gives no birth date nothing has been ruled out, so it stays a potential match.
        live = [c for c in candidates if c["dobmatch"] is not False]
        result = "potential" if live else "clear"
        counted[result] += 1
        run(conn, """
            INSERT INTO exclusionchecks (recordid, accountid, driverid, runid, source, checkedon,
                                         namessearched, dobsearched, result, candidates, performedby)
            VALUES (:id, :a, :d, :run, :src, :now, :names, :dob, :res, :cands, :by)
        """, id=newid(), a=driver["accountid"], d=driver["recordid"], run=runid, src=SOURCE,
            now=utcnow(), names="; ".join(names)[:512], dob=driver["dob"], res=result,
            cands=json.dumps(live) if live else None, by=performedby)
    return counted


def already_screened(conn: Connection, stamp: str | None) -> bool:
    """Has this exact published list already been screened against?"""
    if not stamp:
        return False
    return bool(row(conn, """
        SELECT 1 AS x FROM exclusionruns
        WHERE source = :src AND state = 'done' AND datasetstamp = :stamp LIMIT 1
    """, src=SOURCE, stamp=stamp))


def monthly(conn: Connection, url: str = LEIE_URL, force: bool = False) -> dict:
    """One screening run, start to finish.

    Keyed on the published list rather than on the calendar, which is what makes this safe to run
    every day. OIG replaces the file monthly; a day when the stamp has not moved is a day with
    nothing to do. The point of running daily is that a missed month cannot happen quietly - if the
    box is down on the 11th, the 12th picks it up - and a missing month is precisely the thing an
    auditor asks about."""
    head = fetch_stamp(url)
    if not force and already_screened(conn, head):
        return {"skipped": True, "stamp": head}

    runid = newid()
    run(conn, """
        INSERT INTO exclusionruns (recordid, source, startedon, state)
        VALUES (:id, :src, :now, 'running')
    """, id=runid, src=SOURCE, now=utcnow())

    try:
        got = fetch(url)
        held = index(got["body"])
        listed = sum(len(v) for v in held.values())
        if listed < LEIE_MIN_ROWS:
            raise ValueError(f"only {listed:,} rows - the download looks truncated, refusing to "
                             "screen everybody clear against it")
        counted = screen(conn, held, runid=runid)
        run(conn, """
            UPDATE exclusionruns SET datasetstamp = :stamp, datasetbytes = :bytes, datasetsha = :sha,
                   records = :n, finishedon = :now, state = 'done' WHERE recordid = :id
        """, stamp=got["stamp"], bytes=got["bytes"], sha=got["sha"], n=listed, now=utcnow(), id=runid)
        return {"runid": runid, "stamp": got["stamp"], "listed": listed, **counted}
    except Exception as e:
        # A failed run is recorded rather than silently retried: a month with no screening is a
        # thing somebody has to know about.
        run(conn, "UPDATE exclusionruns SET finishedon = :now, state = 'failed', note = :why "
                  "WHERE recordid = :id", now=utcnow(), why=str(e)[:512], id=runid)
        raise


def latest_for(conn: Connection, accountid: str, driverid: str) -> dict | None:
    return row(conn, """
        SELECT recordid, checkedon, result, candidates, verifiedon
        FROM exclusionchecks WHERE accountid = :a AND driverid = :d AND source = :src
        ORDER BY checkedon DESC LIMIT 1
    """, a=accountid, d=driverid, src=SOURCE)
