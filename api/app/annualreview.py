###################################################################################################
# The annual review of a driver's driving record.
#
# 49 CFR 391.25 asks the carrier to obtain the driver's motor vehicle record at least once every
# twelve months, to consider the accidents and violations it shows, to decide whether the driver
# still meets the qualification standards, and to note that decision with the name of the person who
# made it. That note is the form here, and the name on it is a signature.
#
# The sheet is rebuilt from the record rather than stored as a file, and the record keeps the driver
# and the license as they read on the day - so a review read three years later shows the license
# that was reviewed, not the one that replaced it.
###################################################################################################
import json
from datetime import date, timedelta
from html import escape

from sqlalchemy.engine import Connection

from app import applicationview as view
from app import phi, signatures, storage
from app.db import newid, row, rows, run


def mvr_document(conn: Connection, accountid: str, driverid: str, asof=None) -> dict | None:
    """The driving record the review was made against: the newest one on file as at the review, with
    a copy behind it. A review of a record nobody can produce is a review of nothing, so the record
    travels with the review rather than being looked up again years later."""
    return row(conn, """
        SELECT c.documentid, c.issuedon, d.filename, d.mimetype, d.bytes, d.sha256, d.storagekey
        FROM credentials c JOIN credentialtypes t ON t.recordid = c.credentialtypeid
        JOIN documents d ON d.recordid = c.documentid AND d.deleted IS NULL
        WHERE c.accountid = :a AND c.subject = 'driver' AND c.subjectid = :d AND c.deleted IS NULL
          AND c.revokedon IS NULL AND t.code = 'MVR' AND (:on IS NULL OR c.issuedon <= :on)
        ORDER BY c.issuedon DESC, c.added DESC LIMIT 1
    """, a=accountid, d=driverid, on=asof)


FINDINGS = {
    "qualified": "Meets the minimum requirements for safe driving",
    # The middle answer, and the one a two-answer form forces a reviewer to lie about. A record
    # showing something that needs chasing - a violation to counsel on, a license class to put
    # right - does not disqualify anybody, but recording it as a plain "qualified" loses the only
    # note that says anybody noticed. 391.25(b) asks the reviewer to CONSIDER the record; this is
    # how they say what considering it produced.
    "corrective": ("Meets the minimum requirements for safe driving, with corrective action "
                   "required on the item noted below"),
    "notqualified": ("Disqualified to drive a motor vehicle pursuant to Section 391.15 and has been "
                     "removed from safety sensitive functions"),
}
# The two that oblige somebody to say what they found. "Qualified, with corrective action" and
# "disqualified" are both unreadable without the reason, and a blank there is a finding nobody can
# act on a year later.
NEEDS_REASON = ("corrective", "notqualified")


def _active_license(conn: Connection, accountid: str, driverid: str) -> dict | None:
    """The license the driver drives on today."""
    return row(conn, """
        SELECT recordid, state, number FROM driverlicenses
        WHERE accountid = :a AND driverid = :d AND active = 1
        ORDER BY COALESCE(issued, '1900-01-01') DESC LIMIT 1
    """, a=accountid, d=driverid)


def readiness(conn: Connection, accountid: str, driverid: str, today: date | None = None) -> dict:
    """Whether a review CAN be completed: a current driving record on the driver's active license.

    The annual review is one form, made against the license the driver drives on now. The reviewer
    is stopped rather than warned where that license has no current record.

    The window is read from MVR_ANNUAL's own recurrence rather than written down a second time
    here: the gate and the requirement answer the same question, and two copies of the same
    interval is how they come to disagree about whether a record is still current.
    """
    from app import mvr as mvrs
    rule = row(conn, """SELECT recurrence, recurrencedays, recurrencemonths FROM compliancerules
                        WHERE code = 'MVR_ANNUAL' AND accountid IS NULL AND effectiveto IS NULL""") or {}
    lic = _active_license(conn, accountid, driverid)
    if not lic:
        return {"required": [], "covered": 0, "missing": [], "complete": None,
                "why": "No active license is on file, so there is nothing to review against."}
    cov = mvrs.coverage(conn, accountid, driverid, today=today, window=mvrs.HIRE_LOOKBACK,
                        lapses=mvrs.horizon(rule) or mvrs.horizon({"recurrence": "months",
                                                                   "recurrencemonths": 12}))
    card = next((c for c in cov.get("cards", []) if c["licenseid"] == lic["recordid"]), None) or {}
    today = today or date.today()
    covered = bool(card.get("record")) and not (card.get("expireson") and card["expireson"] < today)
    label = f'{lic["state"]} {lic["number"]}'
    entry = {"state": lic["state"], "licenses": [lic["number"]], "licenseid": lic["recordid"],
             "record": card.get("record"), "ordered": card.get("ordered"),
             "expireson": card.get("expireson"), "state_covered": covered}
    return {"required": [entry], "covered": int(covered), "missing": [] if covered else [label],
            "complete": covered,
            "why": f"Current record on file for {label}" if covered
                   else f"No current record for {label}"}

# What the carrier says it did before reaching the finding. It is the same every time because it is
# a statement of practice, not of this driver - what differs is the finding underneath it.
GOOD_FAITH_CMV = (
    "A current Motor Vehicle Record (MVR) has been obtained from the licensing state covering the "
    "driver's previous 3 years of driving. In accordance with 49 CFR §391.25(a), the employer has "
    "reviewed the MVR(s) along with the driver's certification of violations and other "
    "safety-related data, and has used this information to determine the driver's continuing "
    "qualification to operate a commercial motor vehicle.")
GOOD_FAITH_OTHER = (
    "A current Motor Vehicle Record (MVR) has been obtained from the licensing state covering the "
    "driver's previous 3 years of driving. The employer has reviewed the MVR(s) along with the "
    "driver's certification of violations and other safety-related data, and has used this "
    "information to determine the driver's continuing qualification to drive for the company.")

TITLE = "Annual Review Of Driving Record"


def _choice(selected: str, options: list[tuple[str, str]]) -> str:
    """The finding, as the form asks it: one line per answer, the one taken ticked."""
    return "".join(
        f'<div class="question"><span class="q">'
        f'{"&#9745;" if key == selected else "&#9744;"} {escape(label)}</span></div>'
        for key, label in options)


def _license(conn: Connection, accountid: str, driverid: str, licenseid: str | None = None) -> dict:
    """The license the review was made against - the one its driving record was pulled on, or, where
    a review is not tied to one, the license they drive on."""
    if licenseid:
        return row(conn, """
            SELECT number, state, classification, endorsements, issued, expires
            FROM driverlicenses WHERE recordid = :l AND accountid = :a
        """, l=licenseid, a=accountid) or {}
    return row(conn, """
        SELECT number, state, classification, endorsements, issued, expires
        FROM driverlicenses WHERE accountid = :a AND driverid = :d
        ORDER BY active DESC, COALESCE(expires, '1900-01-01') DESC LIMIT 1
    """, a=accountid, d=driverid) or {}


def snapshot(conn: Connection, accountid: str, driver: dict, licenseid: str | None = None) -> dict:
    """Driver and license as the form shows them, kept with the review."""
    held = (phi.get(conn, accountid, "driver", driver["recordid"]) or {}).get("ssn")
    lic = _license(conn, accountid, driver["recordid"], licenseid)
    return {
        "name": f'{driver.get("firstname") or ""} {driver.get("lastname") or ""}'.strip(),
        "dob": str(driver["dob"]) if driver.get("dob") else None,
        "ssnlast4": held[-4:] if held and len(held) >= 4 else None,
        "licensenumber": lic.get("number") or driver.get("licensenumber"),
        "licensestate": lic.get("state") or driver.get("licensestate"),
        "licenseclass": lic.get("classification") or driver.get("licenseclass"),
        "issued": str(lic["issued"]) if lic.get("issued") else None,
        "expires": str(lic["expires"]) if lic.get("expires") else None,
        "country": "United States",
        "cmv": bool(driver.get("operatescmv")),
    }


def open_period(conn: Connection, accountid: str, driverid: str, on: date | None = None) -> dict | None:
    """The review currently open for this driver, if there is one.

    At most one is open at a time. 49 CFR 391.25 asks for one determination about one driver at
    least once every 12 months - not one per record that happens to arrive."""
    return row(conn, """
        SELECT recordid, periodstart, periodend, snapshot FROM annualreviews
        WHERE accountid = :a AND driverid = :d AND reviewedon IS NULL
        ORDER BY createdon DESC LIMIT 1
    """, a=accountid, d=driverid)


def newer_record(conn: Connection, accountid: str, driverid: str, reviewid: str,
                 reviewedon: date) -> dict | None:
    """A driving record that came in after the one this review read. The review answered for the
    record it read; a newer one has not been reviewed by anybody."""
    return row(conn, """
        SELECT m.recordid, m.receivedon FROM drivermvrs m
        WHERE m.accountid = :a AND m.driverid = :d AND m.receivedon IS NOT NULL
          AND m.cancelledon IS NULL
          AND m.recordid NOT IN (SELECT mvrid FROM annualreviewmvrs WHERE reviewid = :r)
          -- Received after the review was completed. A review from before completion times were
          -- kept counts from the start of its day: a record that came in that day is one the
          -- review cannot be shown to have read, and the record it did read is excluded above.
          AND m.receivedon > (SELECT COALESCE(completedon, TIMESTAMP(reviewedon, '00:00:00'))
                              FROM annualreviews WHERE recordid = :r)
        ORDER BY m.receivedon DESC LIMIT 1
    """, a=accountid, d=driverid, r=reviewid)


def due(conn: Connection, accountid: str, driverid: str, today: date | None = None) -> dict:
    """Whether a §391.25 annual review is owed, and when the last one was.

    "At least once every 12 months" is a deadline, not a trigger. It comes round on its own clock -
    it is not started by a record arriving, and an extra record ordered in between does not move it.
    """
    today = today or date.today()
    last = row(conn, """
        SELECT recordid, reviewedon, finding FROM annualreviews
        WHERE accountid = :a AND driverid = :d AND reviewedon IS NOT NULL
        -- Several on one day: the one completed last.
        ORDER BY reviewedon DESC, COALESCE(completedon, createdon) DESC, createdon DESC LIMIT 1
    """, a=accountid, d=driverid)
    openone = open_period(conn, accountid, driverid)
    nextdue = (last["reviewedon"] + timedelta(days=365)) if last and last["reviewedon"] else None
    # A record received since the last review leaves that review answering for an older record, so
    # another is owed now, whatever the calendar says.
    newer = newer_record(conn, accountid, driverid, last["recordid"], last["reviewedon"]) if last else None
    # A review is started for one of two reasons only: a driving record no completed review has
    # read - a newer one, or the driver's first - or a last review that found the driver
    # disqualified.
    unread = newer or (None if last else row(conn, """
        SELECT recordid, receivedon FROM drivermvrs
        WHERE accountid = :a AND driverid = :d AND receivedon IS NOT NULL AND cancelledon IS NULL
        ORDER BY receivedon DESC LIMIT 1
    """, a=accountid, d=driverid))
    startable = not openone and (bool(unread) or bool(last and last["finding"] == "notqualified"))
    return {"last": last, "open": openone, "nextdue": nextdue, "newer": newer,
            "startable": startable,
            "owed": bool(openone) or not last or bool(newer)
                    or (nextdue is not None and nextdue <= today)}


def start(conn: Connection, accountid: str, driver: dict, today: date | None = None) -> str:
    """Open this driver's annual review, or hand back the one already open.

    The latest driving record received in the period on the active license is attached to it -
    the review is one form, made against the license the driver drives on."""
    held = open_period(conn, accountid, driver["recordid"])
    if held:
        return held["recordid"]
    today = today or date.today()
    start_on = today - timedelta(days=365)
    reviewid = newid()
    run(conn, """
        INSERT INTO annualreviews (recordid, accountid, driverid, periodstart, periodend, method,
                                   snapshot)
        VALUES (:id, :a, :d, :from, :to, 'form', :snap)
    """, id=reviewid, a=accountid, d=driver["recordid"],
        **{"from": start_on, "to": today}, snap=json.dumps(snapshot(conn, accountid, driver)))
    attach(conn, accountid, driver["recordid"], reviewid, start_on)
    return reviewid


def attach(conn: Connection, accountid: str, driverid: str, reviewid: str, start_on: date) -> None:
    """The record the review reads: the latest received in the period on the active license."""
    lic = _active_license(conn, accountid, driverid)
    run(conn, "DELETE FROM annualreviewmvrs WHERE reviewid = :r", r=reviewid)
    if not lic:
        return
    run(conn, "UPDATE annualreviews SET licenseid = :l WHERE recordid = :r",
        l=lic["recordid"], r=reviewid)
    run(conn, """
        INSERT IGNORE INTO annualreviewmvrs (reviewid, mvrid)
        SELECT :r, recordid FROM drivermvrs
        WHERE accountid = :a AND driverid = :d AND licenseid = :l AND receivedon IS NOT NULL
          AND cancelledon IS NULL AND COALESCE(issuedon, DATE(receivedon)) >= :from
        ORDER BY COALESCE(issuedon, DATE(receivedon)) DESC, receivedon DESC LIMIT 1
    """, r=reviewid, a=accountid, d=driverid, l=lic["recordid"], **{"from": start_on})


def records_for(conn: Connection, accountid: str, reviewid: str) -> list[dict]:
    """The driving records this review was performed against, by state."""
    return rows(conn, """
        SELECT m.recordid, m.issuedon, m.documentid, m.norecord, l.state, l.number,
               -- Whether each record has been read, and what reading it concluded. The review
               -- reaches one determination, but it reaches it from records that are read one at
               -- a time, and a record nobody has opened is the gap the review is meant to catch.
               m.reviewstate, m.finding
        FROM annualreviewmvrs a
        JOIN drivermvrs m ON m.recordid = a.mvrid
        LEFT JOIN driverlicenses l ON l.recordid = m.licenseid
        WHERE a.reviewid = :r AND m.accountid = :a
        ORDER BY l.state
    """, r=reviewid, a=accountid)


def complete(conn: Connection, accountid: str, review: dict, driver: dict, *, reviewedon: date,
             finding: str, note: str | None, reviewer: str, signatureid: str | None,
             method: str = "form", documentid: str | None = None, filedon: date | None = None,
             enteredby: str | None = None, ip: str | None = None, useragent: str | None = None) -> dict:
    """Finish an open review: what it found, who found it, and how that was recorded.

    The words the reviewer signed are hashed as they stood, so the sheet read later can be shown to
    be the sheet that was signed."""
    if finding not in FINDINGS:
        raise ValueError("Unknown finding")
    if method not in ("form", "upload"):
        raise ValueError("Unknown method")
    snap = json.loads(review["snapshot"] or "{}") or snapshot(conn, accountid, driver, review["licenseid"])
    run(conn, """
        UPDATE annualreviews SET reviewedon = :on, completedon = UTC_TIMESTAMP(), finding = :f,
               method = :meth, note = :n,
               reviewer = :by, signatureid = :sig, documentid = :doc, filedon = :filed,
               snapshot = :snap, contentsha256 = :h, ip = :ip, useragent = :ua, enteredby = :u
        WHERE recordid = :id AND accountid = :a
    """, on=reviewedon, f=finding, meth=method, n=(note or None), by=reviewer[:128], sig=signatureid,
        doc=documentid, filed=filedon, snap=json.dumps(snap),
        h=signatures.content_hash(statement(snap, reviewedon, review["mvron"], finding, note)),
        ip=ip, ua=(useragent or "")[:255] or None, u=enteredby, id=review["recordid"], a=accountid)
    return {"recordid": review["recordid"], "snapshot": snap}


def record(conn: Connection, accountid: str, driver: dict, *, reviewedon: date, mvr: dict,
           finding: str, note: str | None, reviewer: str, signatureid: str | None,
           method: str = "form", documentid: str | None, filedon: date | None, enteredby: str | None,
           ip: str | None = None, useragent: str | None = None) -> dict:
    """File one review, against the driving record it was made on.

    The review is fixed to that record and to the license it was pulled on, so the file can always
    say which history was examined. The words the reviewer signed are hashed as they stood, so the
    sheet read later can be shown to be the sheet that was signed."""
    if finding not in FINDINGS:
        raise ValueError("Unknown finding")
    if method not in ("form", "upload"):
        raise ValueError("Unknown method")
    snap = snapshot(conn, accountid, driver, mvr["licenseid"])
    snap["mvrdocumentid"] = mvr.get("documentid")
    snap["mvrfilename"] = mvr.get("filename")
    mvron = mvr.get("issuedon")
    reviewid = newid()
    run(conn, """
        INSERT INTO annualreviews (recordid, accountid, driverid, licenseid, mvrid, signatureid,
                                   reviewedon, completedon, mvron, finding, method, note, reviewer,
                                   documentid, filedon, snapshot, contentsha256, ip, useragent,
                                   enteredby)
        VALUES (:id, :a, :d, :lic, :mvrid, :sig, :on, UTC_TIMESTAMP(), :mvr, :f, :meth, :n, :by,
                :doc, :filed, :snap, :h, :ip, :ua, :u)
    """, id=reviewid, a=accountid, d=driver["recordid"], lic=mvr["licenseid"], mvrid=mvr["recordid"],
        sig=signatureid, on=reviewedon, mvr=mvron, f=finding, meth=method, n=(note or None),
        by=reviewer[:128], doc=documentid, filed=filedon, snap=json.dumps(snap),
        h=signatures.content_hash(statement(snap, reviewedon, mvron, finding, note)),
        ip=ip, ua=(useragent or "")[:255] or None, u=enteredby)
    return {"recordid": reviewid, "snapshot": snap}


def statement(snap: dict, reviewedon, mvron, finding: str, note: str | None) -> str:
    """Everything the signature stands behind, as one piece of text to hash."""
    parts = [TITLE, snap.get("name") or "", str(snap.get("dob") or ""),
             str(snap.get("licensenumber") or ""), str(snap.get("licensestate") or ""),
             GOOD_FAITH_CMV if snap.get("cmv") else GOOD_FAITH_OTHER,
             f"MVR dated {mvron}" if mvron else "MVR date not recorded",
             FINDINGS[finding], f"Reviewed {reviewedon}", (note or "").strip()]
    return "\n".join(p for p in parts if p)


def listing(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every review on file for this driver, newest first - the ones signed here and the ones done
    elsewhere and filed. Both carry a finding, and both name the license and the driving record they
    were made on."""
    done = [{**r, "kind": r["method"] or "form",
             "state": "complete" if r["finding"] else "open",
             "records": records_for(conn, accountid, r["recordid"])} for r in rows(conn, """
        SELECT r.recordid, r.reviewedon, r.completedon, r.mvron, r.finding, r.method, r.reviewer,
               r.documentid,
               r.filedon, r.createdon, r.periodstart, r.periodend, r.licenseid, r.mvrid, s.typedname,
               l.state AS licensestate, l.number AS licensenumber
        FROM annualreviews r
        LEFT JOIN signatures s ON s.recordid = r.signatureid
        LEFT JOIN driverlicenses l ON l.recordid = r.licenseid
        WHERE r.accountid = :a AND r.driverid = :d
    """, a=accountid, d=driverid)]
    # Newest first within each group, and the open ones first of all - they are the work owed.
    # Completed ones by when they were completed - several on one day are told apart by the time.
    done.sort(key=lambda r: (str(r["reviewedon"] or r["periodend"] or r["mvron"] or ""),
                             str(r["completedon"] or r["createdon"]), str(r["createdon"])), reverse=True)
    done.sort(key=lambda r: r["state"] == "complete")
    return done


def _one(conn: Connection, accountid: str, reviewid: str) -> dict | None:
    return row(conn, """
        SELECT r.*, s.typedname, s.fontkey, s.signername
        FROM annualreviews r LEFT JOIN signatures s ON s.recordid = r.signatureid
        WHERE r.recordid = :id AND r.accountid = :a
    """, id=reviewid, a=accountid)


LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


def attached_records(conn: Connection, accountid: str, r: dict, snap: dict) -> str:
    """Every driving record this review was performed against, one exhibit each.

    A review of a driver who held licenses in three states reads three records and reaches one
    determination - so the sheet carries all three behind it, lettered, and says which state each
    came from. A single "Exhibit A" on a review that read three is a sheet that cannot be checked."""
    held = records_for(conn, accountid, r["recordid"])
    if not held:
        return _attached_record(conn, accountid, r, snap)       # a review migrated from the old shape
    out = []
    for i, rec in enumerate(held):
        where = " ".join(x for x in (rec.get("state"), rec.get("number")) if x) or "Driving record"
        when = f' dated {rec["issuedon"]:%m/%d/%Y}' if rec.get("issuedon") else ""
        label = f"Exhibit {LETTERS[i] if i < len(LETTERS) else str(i + 1)}"
        head = (f'<div class="exhibit"><span class="label">{label}</span>'
                f'<span class="name">{escape(where)}{escape(when)}</span></div>')
        if rec.get("norecord"):
            out.append(f'<div class="sheet">{head}<p class="none">The licensing authority returned '
                       f'no record. The inquiry was made and is documented here.</p></div>')
            continue
        out.append(_one_record_sheet(conn, accountid, rec.get("documentid"), head))
    return "".join(out)


def _exhibit(conn: Connection, accountid: str, label: str, name: str, documentid: str | None,
             none: str) -> dict:
    """One exhibit, two ways: as HTML for the screen, which can show a PDF inside the page, and as
    a heading page plus the document's own pages for the printed PDF, which cannot."""
    head = (f'<div class="exhibit"><span class="label">{escape(label)}</span>'
            f'<span class="name">{escape(name)}</span></div>')
    doc = row(conn, """
        SELECT filename, mimetype, bytes, sha256, storagekey FROM documents
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=documentid, a=accountid) if documentid else None
    if not doc:
        page = f'<div class="sheet">{head}<p class="none">{escape(none)}</p></div>'
        return {"inline": page, "page": page, "pdf": None}
    meta = f'{doc["filename"]} · {doc["bytes"]:,} bytes · SHA-256 {doc["sha256"][:16]}…'
    mime = doc["mimetype"] or "application/pdf"
    try:
        blob = storage.get(doc["storagekey"])
    except storage.Missing:
        page = f'<div class="sheet">{head}<p class="none">That file is no longer stored.</p></div>'
        return {"inline": page, "page": page, "pdf": None}
    if mime.startswith("image/"):
        page = f'<div class="sheet">{head}{view._embedded(blob, mime, name)}<p class="meta">{escape(meta)}</p></div>'
        return {"inline": page, "page": page, "pdf": None}
    if mime == "application/pdf":
        return {"inline": f'<div class="sheet">{head}{view._embedded(blob, mime, name)}'
                          f'<p class="meta">{escape(meta)}</p></div>',
                "page": f'<div class="sheet">{head}<p class="meta">{escape(meta)}</p></div>',
                "pdf": blob}
    page = (f'<div class="sheet">{head}<p class="none">This document is filed as {escape(mime)} and '
            f'cannot be shown on the page.</p><p class="meta">{escape(meta)}</p></div>')
    return {"inline": page, "page": page, "pdf": None}


def exhibits(conn: Connection, accountid: str, r: dict, snap: dict) -> list[dict]:
    """What the review was made against, behind it: the driver's license, then the last driving
    record on that license."""
    lic = row(conn, """
        SELECT recordid, state, number, copydocumentid FROM driverlicenses
        WHERE accountid = :a AND recordid = :l
    """, a=accountid, l=r.get("licenseid")) if r.get("licenseid") else None
    lic = lic or row(conn, """
        SELECT recordid, state, number, copydocumentid FROM driverlicenses
        WHERE accountid = :a AND driverid = :d
        ORDER BY active DESC, COALESCE(issued, '1900-01-01') DESC LIMIT 1
    """, a=accountid, d=r["driverid"])
    where = " ".join(x for x in ((lic or {}).get("state"), (lic or {}).get("number")) if x)
    out = [_exhibit(conn, accountid, "Exhibit A", f"Driver's License - {where}" if where
                    else "Driver's License", (lic or {}).get("copydocumentid"),
                    "No copy of the driver's license is on file.")]
    held = records_for(conn, accountid, r["recordid"])
    mvr = held[0] if held else (row(conn, """
        SELECT m.recordid, m.issuedon, m.documentid, m.norecord FROM drivermvrs m
        WHERE m.accountid = :a AND m.licenseid = :l AND m.receivedon IS NOT NULL
          AND m.cancelledon IS NULL
        ORDER BY COALESCE(m.issuedon, DATE(m.receivedon)) DESC, m.receivedon DESC LIMIT 1
    """, a=accountid, l=lic["recordid"]) if lic else None)
    when = f' dated {mvr["issuedon"]:%m/%d/%Y}' if mvr and mvr.get("issuedon") else ""
    name = f"Motor Vehicle Record - {where}{when}" if where else f"Motor Vehicle Record{when}"
    if mvr and mvr.get("norecord"):
        page = (f'<div class="sheet"><div class="exhibit"><span class="label">Exhibit B</span>'
                f'<span class="name">{escape(name)}</span></div><p class="none">The licensing '
                f'authority returned no record. The inquiry was made and is documented here.</p></div>')
        out.append({"inline": page, "page": page, "pdf": None})
    else:
        out.append(_exhibit(conn, accountid, "Exhibit B", name, (mvr or {}).get("documentid"),
                            "No copy of the driving record is on file."))
    return out


def _one_record_sheet(conn: Connection, accountid: str, documentid: str | None, head: str) -> str:
    doc = row(conn, """
        SELECT filename, mimetype, bytes, sha256, storagekey FROM documents
        WHERE recordid = :id AND accountid = :a AND deleted IS NULL
    """, id=documentid, a=accountid) if documentid else None
    if not doc:
        return f'<div class="sheet">{head}<p class="none">No copy of the driving record is on file.</p></div>'
    meta = f'{doc["filename"]} · {doc["bytes"]:,} bytes · SHA-256 {doc["sha256"][:16]}…'
    mime = doc["mimetype"] or "application/pdf"
    if not (mime.startswith("image/") or mime == "application/pdf"):
        return (f'<div class="sheet">{head}'
                f'<p class="none">This record is filed as {escape(mime)} and cannot be shown on the '
                f'page. It is part of this review and can be saved from here.</p>'
                f'<p class="meta">{escape(meta)} · '
                f'<a class="avsave" data-name="{escape(doc["filename"])}">save</a></p></div>')
    try:
        shown = view._embedded(storage.get(doc["storagekey"]), mime, "Motor vehicle record")
    except storage.Missing:
        return f'<div class="sheet">{head}<p class="none">That file is no longer stored.</p></div>'
    return f'<div class="sheet">{head}{shown}<p class="meta">{escape(meta)}</p></div>'


def _attached_record(conn: Connection, accountid: str, r: dict, snap: dict) -> str:
    """The single record a review was opened from, for reviews written before a review could read
    more than one."""
    doc = None
    if r.get("mvrid"):
        doc = row(conn, """
            SELECT d.filename, d.mimetype, d.bytes, d.sha256, d.storagekey
            FROM drivermvrs m JOIN documents d ON d.recordid = m.documentid AND d.deleted IS NULL
            WHERE m.recordid = :m AND m.accountid = :a
        """, m=r["mvrid"], a=accountid)
    if not doc and snap.get("mvrdocumentid"):
        doc = row(conn, """
            SELECT filename, mimetype, bytes, sha256, storagekey FROM documents
            WHERE recordid = :id AND accountid = :a AND deleted IS NULL
        """, id=snap["mvrdocumentid"], a=accountid)
    if not doc:
        doc = (mvr_document(conn, accountid, r["driverid"], r["mvron"] or r["reviewedon"])
               or mvr_document(conn, accountid, r["driverid"], None))
    head = ('<div class="exhibit"><span class="label">Exhibit A</span>'
            '<span class="name">Motor Vehicle Record Reviewed</span></div>')
    if not doc:
        return f'<div class="sheet">{head}<p class="none">No copy of the driving record is on file.</p></div>'
    meta = f'{doc["filename"]} · {doc["bytes"]:,} bytes · SHA-256 {doc["sha256"][:16]}…'
    mime = doc["mimetype"] or "application/pdf"
    # A record filed as something no page can draw - a word processor file, a spreadsheet - is named
    # and offered rather than shown as an empty frame.
    if not (mime.startswith("image/") or mime == "application/pdf"):
        return (f'<div class="sheet">{head}'
                f'<p class="none">This record is filed as {escape(mime)} and cannot be shown on the '
                f'page. It is part of this review and can be saved from here.</p>'
                f'<p class="meta">{escape(meta)} · '
                f'<a class="avsave" data-name="{escape(doc["filename"])}">save</a></p></div>')
    try:
        shown = view._embedded(storage.get(doc["storagekey"]), mime, "Motor vehicle record")
    except storage.Missing:
        return f'<div class="sheet">{head}<p class="none">{escape(meta)} is no longer stored.</p></div>'
    return (f'<div class="sheet">{head}{shown}'
            f'<p class="meta">{escape(meta)} · '
            f'<a class="avsave" data-name="{escape(doc["filename"])}">save</a></p></div>')


def sheet(conn: Connection, accountid: str, driverid: str, reviewid: str) -> dict | None:
    """The review as it was signed, on a sheet - the same three parts as the form that was filled."""
    r = _one(conn, accountid, reviewid)
    if not r or r["driverid"] != driverid:
        return None
    snap = json.loads(r["snapshot"] or "{}")
    company = row(conn, "SELECT name FROM accounts WHERE recordid = :a", a=accountid)["name"]

    who = (view._blank("Driver Name", snap.get("name"), 6)
           + view._blank("Birth Date", snap.get("dob"), 3)
           + view._blank("Social Security", f'***-**-{snap["ssnlast4"]}' if snap.get("ssnlast4") else "", 3)
           + view._blank("License Number", snap.get("licensenumber"), 6)
           + view._blank("Date Issued", snap.get("issued"), 3)
           + view._blank("Date Expires", snap.get("expires"), 3)
           + view._blank("License State", snap.get("licensestate"), 6)
           + view._blank("License Country", snap.get("country") or "United States", 6))

    text = GOOD_FAITH_CMV if snap.get("cmv") else GOOD_FAITH_OTHER
    good = f'<div class="fields"><div class="blank note s12"><span class="avval">{escape(text)}</span></div>'
    if r["mvron"]:
        good += view._blank("Date Of The Driving Record Reviewed", r["mvron"], 4)
    good += "</div>"

    finding = ('<div class="question"><span class="q">I have reviewed the driving record of the above '
               'named driver and find that he/she</span></div>'
               + _choice(r["finding"], list(FINDINGS.items())))
    extra = ""
    if r["note"]:
        extra += view._note("Notes", r["note"])
    if r["filedon"]:
        extra += view._blank("Copy Of The Review Filed", r["filedon"], 4)
    if extra:
        finding += f'<div class="fields">{extra}</div>'

    if r["signatureid"] and r["typedname"]:
        signed = view._signature_block(
            {"recordid": r["signatureid"], "signername": r["signername"] or r["reviewer"],
             "signedon": r["createdon"], "ip": r["ip"], "typedname": r["typedname"],
             "fontkey": r["fontkey"] or "modern"},
            label="Signature of reviewer")
    else:
        signed = (f'<div class="avrow">{view._blank("Signature Of Reviewer", r["reviewer"], 6)}'
                  f'{view._blank("Signature Date", r["reviewedon"], 4)}</div>')
    finding += signed

    main = (f'<div class="sheet"><div class="exhibit"><span class="label">Signed</span>'
            f'<span class="name">{TITLE}</span></div>'
            + view._section("Driver / License Information", f'<div class="fields">{who}</div>')
            + view._section("MVR Status / Good Faith Effort Documentation", good)
            + view._section("Review Of Driving Record", finding)
            + "</div>")
    shown = exhibits(conn, accountid, r, snap)
    return {"doctype": f"ANNUAL_REVIEW:{reviewid}", "title": TITLE, "company": company,
            "signedon": r["createdon"], "html": main + "".join(e["inline"] for e in shown),
            "css": view.STYLE,
            # For the printed PDF: the sheet, then each exhibit's heading page and its own pages.
            "main": main, "exhibits": shown}
