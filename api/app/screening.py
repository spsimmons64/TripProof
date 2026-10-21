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
import re
import urllib.request
from pathlib import Path
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
           performedby: str = "tripproof", source: str = SOURCE,
           driverid: str | None = None) -> dict:
    """Screen every pending and active driver on the platform, and record the clean ones too.

    Pending is the driver waiting on a hiring decision - exactly who you want to catch before they
    are on the roster. Active is a hired driver not terminated. Nobody else is screened."""
    counted = {"clear": 0, "potential": 0}
    for driver in rows(conn, """
        SELECT recordid, accountid, firstname, lastname, dob
        FROM drivers
        WHERE deleted IS NULL AND stub = 0 AND terminatedon IS NULL
          AND status IN ('pending', 'hired')
          AND (:one IS NULL OR recordid = :one)
    """, one=driverid):
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
        """, id=newid(), a=driver["accountid"], d=driver["recordid"], run=runid, src=source,
            now=utcnow(), names="; ".join(names)[:512], dob=driver["dob"], res=result,
            cands=json.dumps(live) if live else None, by=performedby)
    return counted


def already_screened(conn: Connection, stamp: str | None, source: str = SOURCE) -> bool:
    """Has this exact published list already been screened against?"""
    if not stamp:
        return False
    return bool(row(conn, """
        SELECT 1 AS x FROM exclusionruns
        WHERE source = :src AND state = 'done' AND datasetstamp = :stamp LIMIT 1
    """, src=source, stamp=stamp))


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
        keep(SOURCE, got["body"], runid)
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
        # Returned rather than raised: raising rolls the transaction back, and the failed run
        # would vanish with it.
        return {"failed": True, "why": str(e)[:512]}


###################################################################################################
# SAM.gov - the same job against the federal exclusions list.
#
# GSA publishes the complete list of active exclusions every day as a ZIP holding one CSV, early
# in the morning Eastern. It is public - the file sam.gov's Data Services page offers - so it needs
# no key, and one download screens every driver rather than one search per driver.
#
# The file carries no birth date and no SSN, so nothing can rule a namesake out. Every name hit is
# a possible match for a person to settle; none is ever an exclusion on its own.
#
# A day the download fails is recorded as failed and nothing else changes: the checks already on
# file age, and the requirement goes amber and then red on its own arithmetic. A screening is
# never shown as current against a list that could not be fetched.
###################################################################################################
SAM_SOURCE = "SAM_EXCLUSIONS"
# The same files sam.gov's own Data Services page offers, public and needing no key. The listing
# names every extract on hand, so the newest is read from it rather than guessed from the date.
SAM_LIST = ("https://sam.gov/api/prod/fileextractservices/v1/api/listfiles"
            "?domain=Exclusions/Public%20V2&privacy=Public")
SAM_URL = ("https://sam.gov/api/prod/fileextractservices/v1/api/download/Exclusions/Public%20V2/"
           "{name}?privacy=Public")
SAM_NAME = re.compile(r"^SAM_Exclusions_Public_Extract_V2_(\d{2})(\d{3})\.ZIP$", re.I)

# Individuals only. Below this the file is not the list - an error page, or a truncated download.
SAM_MIN_ROWS = 10_000


def sam_latest(timeout: int = 60) -> tuple[str, str]:
    """The newest daily extract: its file name, and its date as the stamp it is recorded under."""
    req = urllib.request.Request(SAM_LIST, headers={"User-Agent": "TripProof/1.0 exclusion screening"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        listed = json.loads(r.read())
    names = [x.get("displayKey") or "" for x in
             (listed.get("_embedded") or {}).get("customS3ObjectSummaryList", [])]
    daily = sorted((m.group(1) + m.group(2), n) for n in names if (m := SAM_NAME.match(n)))
    if not daily:
        raise ValueError("SAM.gov lists no daily exclusions extract")
    yyddd, name = daily[-1]
    day = datetime.strptime(yyddd, "%y%j").date()
    return name, day.strftime("%Y-%m-%d")


def sam_fetch(name: str, timeout: int = 300) -> dict:
    """Download one extract and pin exactly what was downloaded."""
    req = urllib.request.Request(SAM_URL.format(name=name),
                                 headers={"User-Agent": "TripProof/1.0 exclusion screening"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
    return {"body": body, "bytes": len(body), "sha": hashlib.sha256(body).hexdigest()}


def sam_index(body: bytes) -> dict[tuple[str, str], list[dict]]:
    """The individuals on the list, keyed by last and first name - the same shape as `index`, so
    the same `screen` matches against it."""
    import zipfile
    with zipfile.ZipFile(io.BytesIO(body)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".csv"))
        text = z.read(name).decode("utf-8-sig", errors="replace")
    held: dict[tuple[str, str], list[dict]] = {}
    for entry in csv.DictReader(io.StringIO(text)):
        if _norm(entry.get("Classification")) != "INDIVIDUAL":
            continue
        last, first = _norm(entry.get("Last")), _norm(entry.get("First"))
        if not last or not first:
            continue
        held.setdefault((last, first), []).append({
            "lastname": last, "firstname": first, "middle": _norm(entry.get("Middle")),
            "dob": "", "npi": _norm(entry.get("NPI")),
            "city": _norm(entry.get("City")), "state": _norm(entry.get("State / Province")),
            "excltype": _norm(entry.get("Exclusion Type")),
            "agency": _norm(entry.get("Excluding Agency")),
            "excldate": _norm(entry.get("Active Date")),
            "until": _norm(entry.get("Termination Date")),
            "samnumber": _norm(entry.get("SAM Number")),
        })
    return held


def daily_sam(conn: Connection, force: bool = False) -> dict:
    """One SAM.gov screening run, start to finish. Keyed on the file's date, so running it twice in
    a day does the work once - and a second run later the same day is the retry for a first one
    that failed."""
    runid = newid()
    try:
        name, stamp = sam_latest()
    except Exception as e:
        name, stamp = None, None
        failed = e
    else:
        failed = None
        if not force and already_screened(conn, stamp, SAM_SOURCE):
            return {"skipped": True, "stamp": stamp}
    run(conn, """
        INSERT INTO exclusionruns (recordid, source, startedon, state)
        VALUES (:id, :src, :now, 'running')
    """, id=runid, src=SAM_SOURCE, now=utcnow())
    try:
        if failed:
            raise failed
        got = sam_fetch(name)
        held = sam_index(got["body"])
        listed = sum(len(v) for v in held.values())
        if listed < SAM_MIN_ROWS:
            raise ValueError(f"only {listed:,} individuals - the download looks wrong, refusing to "
                             "screen everybody clear against it")
        counted = screen(conn, held, runid=runid, source=SAM_SOURCE)
        keep(SAM_SOURCE, got["body"], runid)
        run(conn, """
            UPDATE exclusionruns SET datasetstamp = :stamp, datasetbytes = :bytes, datasetsha = :sha,
                   records = :n, finishedon = :now, state = 'done' WHERE recordid = :id
        """, stamp=stamp, bytes=got["bytes"], sha=got["sha"], n=listed, now=utcnow(), id=runid)
        return {"runid": runid, "stamp": stamp, "listed": listed, **counted}
    except Exception as e:
        # Returned rather than raised: raising rolls the transaction back, and the failed run
        # would vanish with it.
        run(conn, "UPDATE exclusionruns SET finishedon = :now, state = 'failed', note = :why "
                  "WHERE recordid = :id", now=utcnow(), why=str(e)[:512], id=runid)
        return {"failed": True, "why": str(e)[:512]}


###################################################################################################
# One driver, now. 
#
# A driver moved to pending is screened against both lists at that moment, not at the next
# scheduled run - the office is about to decide on them. Each scheduled run keeps the list it
# screened against, so this matches against exactly that published version and records the run it
# came from, without a download in the middle of somebody's click.
###################################################################################################
def _kept(source: str) -> Path:
    from app.config import settings
    return Path(settings.storage_path) / "exclusions" / source


def keep(source: str, body: bytes, runid: str) -> None:
    """Keep the list a run screened against, beside the run it belongs to."""
    base = _kept(source)
    base.parent.mkdir(parents=True, exist_ok=True)
    tmp = base.with_suffix(".tmp")
    tmp.write_bytes(body)
    tmp.replace(base.with_suffix(".list"))
    base.with_suffix(".run").write_text(runid)


def _parse(source: str, body: bytes) -> dict:
    return sam_index(body) if source == SAM_SOURCE else index(body)


def never_screened(conn: Connection, accountid: str, driverid: str) -> list[str]:
    """The lists this driver has no screening against at all."""
    return [src for src in (SOURCE, SAM_SOURCE) if not row(conn, """
        SELECT 1 AS x FROM exclusionchecks
        WHERE accountid = :a AND driverid = :d AND source = :s LIMIT 1
    """, a=accountid, d=driverid, s=src)]


def screen_now(conn: Connection, driverid: str,
               sources: tuple[str, ...] | list[str] = (SOURCE, SAM_SOURCE)) -> dict:
    """Screen one driver against both lists, against the list each last scheduled run kept.

    Where no list has been kept yet, the scheduled job is run there and then - it screens this
    driver with everybody else. Raises where a list cannot be had at all, because the caller must
    not go on as if the driver had been screened."""
    out = {}
    for source in sources:
        base = _kept(source)
        listfile, runfile = base.with_suffix(".list"), base.with_suffix(".run")
        if listfile.exists() and runfile.exists():
            got = screen(conn, _parse(source, listfile.read_bytes()), runid=runfile.read_text().strip(),
                         source=source, driverid=driverid)
        else:
            got = monthly(conn, force=True) if source == SOURCE else daily_sam(conn, force=True)
            if got.get("failed"):
                raise RuntimeError(f'{LIST_NAME[source]}: {got["why"]}')
        out[source] = got
    return out


def latest_for(conn: Connection, accountid: str, driverid: str) -> dict | None:
    return row(conn, """
        SELECT recordid, checkedon, result, candidates, verifiedon
        FROM exclusionchecks WHERE accountid = :a AND driverid = :d AND source = :src
        ORDER BY checkedon DESC LIMIT 1
    """, a=accountid, d=driverid, src=SOURCE)


# What a result is called on the record, in words rather than the column's spelling.
OUTCOME = {"clear": "No match found", "potential": "Possible match", "confirmed": "Excluded"}
LIST_NAME = {"OIG_LEIE": "OIG LEIE", "SAM_EXCLUSIONS": "SAM.gov exclusions"}


def version_of(stamp: str | None) -> str:
    """The published list as people name it - "October 2026" - from the date OIG stamped on it."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(stamp).strftime("%B %Y") if stamp else ""
    except (TypeError, ValueError):
        return stamp or ""


def verification(check: dict) -> str:
    """Whether a person has to settle this check, and if so whether they have."""
    if check["verifiedon"]:
        return f'Verified {check["verifiedon"]:%m/%d/%Y}'
    if check["result"] == "potential":
        return "Required"
    return "Not required"


def audit_sheet(conn: Connection, accountid: str, driverid: str, checkid: str) -> dict | None:
    """One screening as a record of the search: who was searched, against exactly which published
    list, what came back, and who settled it. Drawn from the check and its run, so it says what
    was done then rather than what the software would do now."""
    from app import applicationview as view
    c = row(conn, """
        SELECT e.*, d.firstname, d.lastname, d.dob AS driverdob,
               x.datasetstamp, x.datasetsha, x.records,
               (SELECT u.name FROM users u WHERE u.recordid = e.verifiedby) AS verifiedbyname
        FROM exclusionchecks e
        JOIN drivers d ON d.recordid = e.driverid
        LEFT JOIN exclusionruns x ON x.recordid = e.runid
        WHERE e.recordid = :c AND e.accountid = :a AND e.driverid = :d
    """, c=checkid, a=accountid, d=driverid)
    if not c:
        return None
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=accountid)["name"]
    automatic = c["performedby"] == "tripproof"
    who = (view._blank("Driver Name", f'{c["firstname"]} {c["lastname"]}'.strip().upper(), 6)
           + view._blank("Birth Date", c["dobsearched"] or c["driverdob"], 3)
           + view._blank("Screened On", c["checkedon"].strftime("%Y-%m-%d"), 3)
           + view._note("Names Searched", c["namessearched"]))
    search = (view._blank("Screening Type", LIST_NAME.get(c["source"], c["source"]), 4)
              + view._blank("Database Version", (c["datasetstamp"] if c["source"] == SAM_SOURCE
                                               else version_of(c["datasetstamp"])) or "-", 4)
              + view._blank("Performed By", "Scheduled" if automatic
                            else c["performedby"], 4))
    if c["datasetstamp"]:
        sam = c["source"] == SAM_SOURCE
        search += (view._blank("Published By GSA" if sam else "Published By OIG",
                               c["datasetstamp"], 6)
                   + view._blank("Individuals In The List" if sam else "Entries In The List",
                                 f'{c["records"]:,}' if c["records"] else "", 6)
                   + view._note("File SHA-256", c["datasetsha"])
                   + view._note("Downloaded From", "sam.gov Data Services - Exclusions, Public V2"
                                if sam else LEIE_URL))
    found = view._blank("Screening Outcome", OUTCOME.get(c["result"], c["result"]), 6)
    found += view._blank("Verification Status", verification(c), 6)
    cands = json.loads(c["candidates"]) if c["candidates"] else []
    listed = ""
    if cands:
        listed = view._rows(
            [("Name", 30), ("Birth Date", 12), ("City / State", 20), ("Exclusion Type", 22),
             ("Excluded", 16)],
            [[f'{x.get("lastname")}, {x.get("firstname")} {x.get("middle") or ""}'.strip(),
              x.get("dob") or "Not listed",
              ", ".join(v for v in (x.get("city"), x.get("state")) if v),
              x.get("excltype"), x.get("excldate")] for x in cands], 0)
    settled = ""
    if c["verifiedon"]:
        settled = (view._blank("Verified By", c["verifiedbyname"], 6)
                   + view._blank("Verified On", c["verifiedon"].strftime("%Y-%m-%d"), 3)
                   + view._blank("Method", (c["verifymethod"] or "").upper(), 3))
    if c["note"]:
        settled += view._note("Note", c["note"])
    html = (f'<div class="sheet">'
            + view._letterhead(company, "Exclusion Screening - Search Audit Record")
            + view._section("Driver Searched", f'<div class="fields">{who}</div>')
            + view._section("List Searched", f'<div class="fields">{search}</div>')
            + view._section("Result", f'<div class="fields">{found}</div>{listed}'
                            + (f'<div class="fields">{settled}</div>' if settled else ""))
            + "</div>")
    return {"html": html, "css": view.STYLE}
