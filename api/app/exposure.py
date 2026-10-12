"""The bloodborne pathogens exposure determination - 29 CFR 1910.1030(c)(2).

An employer works out whether anybody's assigned work involves reasonably anticipated contact
with blood or other potentially infectious material, writes that down, and keeps it current.
The section asks for the determination to be made WITHOUT regard to personal protective
equipment: the question is what the work exposes somebody to, not what they are given to wear
against it.

It is answered by ticking duties rather than by writing out job classifications. The regulation
names the duties, the determination is the same for every carrier that does them, and the
answer follows from the ticks - any one of them is occupational exposure and none of them is
not. Nobody is asked to invent a taxonomy, and nobody can tick a duty and then record that
there is no exposure beside it.

What comes out is `company.exposure`, the fact every driver's bloodborne pathogens training and
the company's exposure control plan both hang on.

A determination is never edited. It is superseded by the next one, or withdrawn if it was filed
in error, because what an inspector asks is what was determined and when.
"""

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run, utcnow

# The duties that make exposure reasonably anticipated, as 1910.1030 describes them and as the
# determination itself prints them. Keyed, so the wording can be corrected later without
# rewriting what companies have already determined.
DUTIES = {
    "firstaid": "Assigned first aid involving anticipated contact with blood or other "
                "potentially infectious material",
    "cleaning": "Cleaning blood-contaminated vehicle surfaces or equipment",
    "sharps": "Handling contaminated sharps or regulated medical waste",
    "materials": "Handling materials contaminated with blood or other potentially infectious "
                 "material",
    "assistance": "Assisting passengers with tasks where contact with blood or other "
                  "potentially infectious material is reasonably anticipated",
}

# The same duties as a tick box reads them. The full sentences above go on the signed page,
# where the regulation's own phrasing is what an inspector expects; a checkbox wants a few
# words, and fifteen of them wrapped to three lines is a list nobody reads before ticking.
DUTY_SHORT = {
    "firstaid": "Assigned first aid",
    "cleaning": "Cleaning blood-contaminated surfaces or equipment",
    "sharps": "Handling contaminated sharps or medical waste",
    "materials": "Handling contaminated materials",
    "assistance": "Passenger assistance where contact is foreseeable",
}

# What the determination says about everybody else once the duties are settled. Written here
# rather than at the screen, because it is the wording that goes on the signed page.
EXPOSED_AS = "Drivers"
NOT_EXPOSED_AS = "All other job classifications"
NOBODY_EXPOSED_AS = "All job classifications"
NO_DUTIES = ("No assigned duties involving reasonably anticipated contact with blood or other "
             "potentially infectious material")


def current(conn: Connection, accountid: str) -> dict | None:
    """The determination in force - the most recent one that has not been withdrawn."""
    return row(conn, """
        SELECT d.recordid, d.assessedon, d.exposed, d.nextreview, d.changes, d.corrective,
               d.added, u.name AS madeby,
               s.signedon, s.recordid AS signatureid
        FROM exposuredeterminations d
        LEFT JOIN users u ON u.recordid = d.addedby
        LEFT JOIN documentsignatures s
               ON s.accountid = d.accountid AND s.ownertype = 'exposure'
              AND s.ownerid = d.recordid AND s.doctype = 'BBP_EXPOSURE_DETERMINATION'
        WHERE d.accountid = :a AND d.withdrawn IS NULL
        ORDER BY d.assessedon DESC, d.added DESC
        LIMIT 1
    """, a=accountid)


def history(conn: Connection, accountid: str) -> list[dict]:
    """Every determination this company has made, newest first.

    Withdrawn ones come too, marked: 1910.1030(c)(2)(iv) is about keeping the determination
    current, and a list that hides what was reconsidered cannot show that it was.
    """
    return rows(conn, """
        SELECT d.recordid, d.assessedon, d.exposed, d.nextreview, d.withdrawn, d.added,
               u.name AS madeby, s.signedon
        FROM exposuredeterminations d
        LEFT JOIN users u ON u.recordid = d.addedby
        LEFT JOIN documentsignatures s
               ON s.accountid = d.accountid AND s.ownertype = 'exposure'
              AND s.ownerid = d.recordid AND s.doctype = 'BBP_EXPOSURE_DETERMINATION'
        WHERE d.accountid = :a
        ORDER BY d.assessedon DESC, d.added DESC
    """, a=accountid)


def duties_of(conn: Connection, determinationid: str) -> list[str]:
    """The duty keys ticked on one determination, in the order they are published."""
    held = {r["duty"] for r in rows(
        conn, "SELECT duty FROM exposureduties WHERE determinationid = :d", d=determinationid)}
    return [k for k in DUTIES if k in held]


def exposed(conn: Connection, accountid: str) -> bool | None:
    """Whether this company has occupational exposure - the fact, from the signed page.

    None where no determination has been signed, which is a different thing from no exposure:
    nobody has looked. The drivers' training requirement reads this, and "we have not decided"
    must not read as "no".
    """
    held = current(conn, accountid)
    if not held or not held["signedon"]:
        return None
    return bool(held["exposed"])


def make(conn: Connection, accountid: str, userid: str, *, assessedon,
         duties: list[str], nextreview=None, changes: str | None = None,
         corrective: str | None = None) -> str:
    """Record a determination. Returns its id; the caller signs it.

    `exposed` is not a parameter. It is what the duties say, computed here so that the stored
    answer and the stored ticks cannot disagree."""
    kept = [k for k in DUTIES if k in set(duties)]
    recordid = newid()
    run(conn, """
        INSERT INTO exposuredeterminations (recordid, accountid, assessedon, exposed, nextreview,
                                            changes, corrective, addedby)
        VALUES (:id, :a, :on, :e, :nr, :ch, :co, :by)
    """, id=recordid, a=accountid, on=assessedon, e=1 if kept else 0, nr=nextreview,
        ch=(changes or "").strip()[:512] or None, co=(corrective or "").strip()[:512] or None,
        by=userid)
    for duty in kept:
        run(conn, """
            INSERT INTO exposureduties (recordid, accountid, determinationid, duty)
            VALUES (:id, :a, :d, :k)
        """, id=newid(), a=accountid, d=recordid, k=duty)
    return recordid


def withdraw(conn: Connection, accountid: str, recordid: str, userid: str) -> bool:
    """Take back a determination filed in error. The row stays and gets a date."""
    return bool(run(conn, """
        UPDATE exposuredeterminations SET withdrawn = :now, withdrawnby = :by
        WHERE recordid = :id AND accountid = :a AND withdrawn IS NULL
    """, now=utcnow(), by=userid, id=recordid, a=accountid).rowcount)


def tables(duties: list[str]) -> dict[str, str]:
    """Sections 3, 4 and 5 of the determination, written from the ticks.

    The form asks for three tables of job classifications; the company answered one question
    about duties. These are the same answer set out the way the section asks to read it, so
    what is signed is a complete determination rather than a page of blanks.
    """
    done = [k for k in DUTIES if k in set(duties)]
    if done:
        some = _table("Exposure-producing tasks or procedures",
                      [(EXPOSED_AS, "; ".join(DUTIES[k] for k in done))])
        none = _table("Basis for the determination", [(NOT_EXPOSED_AS, NO_DUTIES)])
    else:
        some = _none()
        none = _table("Basis for the determination", [(NOBODY_EXPOSED_AS, NO_DUTIES)])
    # Nothing in non-emergency medical transportation puts EVERY employee in a classification
    # under exposure, so section 3 is answered rather than offered as a blank to fill.
    return {"allexposed": _none(), "someexposed": some, "noexposure": none}


def _none() -> str:
    return "<p><strong>None identified.</strong></p>"


def _table(detailhead: str, lines: list[tuple[str, str]]) -> str:
    from html import escape
    body = "".join(f"<tr><td>{escape(a)}</td><td>{escape(b)}</td></tr>" for a, b in lines)
    return (f"<table><thead><tr><th>Job classification</th><th>{escape(detailhead)}</th>"
            f"</tr></thead><tbody>{body}</tbody></table>")
