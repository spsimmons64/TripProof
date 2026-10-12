###################################################################################################
# Accidents, and whether one of them owed a drug and alcohol test - 49 CFR 390.15(b), 382.303.
#
# The register and the decision are kept together because they are the same event seen twice. What
# this module will not do is treat an accident as a test trigger on its own: 382.303 reaches a
# minority of accidents, and a system that tests everybody after every knock is not more compliant,
# it is just wrong in the other direction.
#
# THE DECISION IS THREE-VALUED, AND THAT IS THE POINT
#
# In the hours after an accident the carrier often does not yet know whether the driver was cited.
# "We do not know" is a real answer, it is not "no", and the difference decides whether somebody
# has to get a driver to a collection site within the next few hours. So `decide` answers True,
# False or None, and None says what is still missing.
#
# THE CLOCK
#
# An alcohol test is attempted within 8 hours (382.303(d)(2)) and a controlled substances test
# within 32 (382.303(e)). Where it did not happen in time the carrier keeps a record of why - which
# is a column, not a shrug.
###################################################################################################
from datetime import timedelta

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run, utcnow

# How long after the accident each test may still be attempted.
ALCOHOL_WINDOW = timedelta(hours=8)
DRUG_WINDOW = timedelta(hours=32)
# 382.303(d)(1): after two hours the carrier must already be recording why it has not happened.
ALCOHOL_PROMPT = timedelta(hours=2)


def _said(value) -> bool | None:
    """A stored yes/no/nobody-has-said, as itself. MySQL hands a tinyint back as 0, 1 or None, and
    coercing that to a bool is how "not answered" quietly becomes "no"."""
    return None if value is None else bool(value)


def qualifying(accident: dict) -> bool | None:
    """Whether this accident is one of the kinds 382.303 reaches, leaving the citation aside.

    A fatality is not in here: a fatality tests on its own and never asks about a citation."""
    hurt = _said(accident.get("injurytreatedaway"))
    towed = _said(accident.get("towaway"))
    if hurt or towed:
        return True
    if hurt is None or towed is None:
        return None                     # one of them might yet be a yes
    return False


def decide(accident: dict) -> dict:
    """Whether 382.303 required a test, and what is still unanswered if nobody can say.

    Answers {"required": True|False|None, "why": str, "waiting": [facts]} - and the same answer
    covers both tests, because the alcohol and controlled substances triggers are the same."""
    dead = accident.get("fatalities")
    if dead is not None and dead > 0:
        return {"required": True, "waiting": [],
                "why": "A human fatality. 382.303 requires a test whatever else is true, and no "
                       "citation is needed for it."}

    reached = qualifying(accident)
    cited = _said(accident.get("cited"))

    if reached is False and dead is not None:
        return {"required": False, "waiting": [],
                "why": "No fatality, nobody was treated away from the scene, and no vehicle was "
                       "towed. 382.303 does not reach this accident."}
    # A citation with nothing for it to attach to still tests nothing: the kind of accident is what
    # 382.303 asks about first, and the citation only decides those two kinds.
    if reached is True and cited is False:
        return {"required": False, "waiting": [],
                "why": "The driver was not cited, so neither the injury nor the tow-away requires "
                       "a test under 382.303."}
    if reached is True and cited is True:
        return {"required": True, "waiting": [],
                "why": "The driver was cited and somebody was treated away from the scene or a "
                       "vehicle was towed. 382.303 requires a test."}

    waiting = []
    if dead is None:
        waiting.append("whether anybody died")
    if _said(accident.get("injurytreatedaway")) is None:
        waiting.append("whether anybody was treated away from the scene")
    if _said(accident.get("towaway")) is None:
        waiting.append("whether a vehicle was towed")
    if reached is not False and cited is None:
        waiting.append("whether the driver was cited")
    return {"required": None, "waiting": waiting,
            "why": "Not decided yet - nobody has said " + ", ".join(waiting) + "."}


def windows(accident: dict) -> dict:
    """When each test stops being possible, counted from the accident itself."""
    when = accident.get("occurredon")
    if not when:
        return {"alcoholby": None, "drugby": None, "alcoholprompt": None}
    return {"alcoholby": when + ALCOHOL_WINDOW,
            "alcoholprompt": when + ALCOHOL_PROMPT,
            "drugby": when + DRUG_WINDOW}


def standing(accident: dict) -> tuple[str, str]:
    """Where one accident stands, and the sentence for it."""
    call = decide(accident)
    if call["required"] is None:
        return "unknown", call["why"]
    if call["required"] is False:
        return "notrequired", call["why"]
    got = [k for k in ("alcoholtestid", "drugtestid") if accident.get(k)]
    if len(got) == 2:
        return "tested", "Tested for alcohol and controlled substances."
    if got:
        which = "alcohol" if got[0] == "alcoholtestid" else "controlled substances"
        return "part", f"Tested for {which}. The other test is not on file."
    if accident.get("nottested"):
        return "excused", accident["nottested"]
    return "owed", call["why"]


def record(conn: Connection, accountid: str, driverid: str, *, occurredon, location=None,
           fatalities=None, injuries=None, hazmatreleased=None, injurytreatedaway=None,
           towaway=None, cited=None, citedon=None, nottested=None, note=None,
           enteredby=None) -> str:
    """Put one accident in the register. Nothing is decided here - the facts are stored as given,
    including the ones nobody can answer yet, and `decide` reads them."""
    rid = newid()
    run(conn, """
        INSERT INTO driveraccidents (recordid, accountid, driverid, occurredon, location,
                                     fatalities, injuries, hazmatreleased, injurytreatedaway,
                                     towaway, cited, citedon, nottested, note, enteredby)
        VALUES (:id, :a, :d, :on, :loc, :dead, :hurt, :hm, :away, :tow, :cit, :citon, :nt, :n, :u)
    """, id=rid, a=accountid, d=driverid, on=occurredon, loc=(location or None),
        dead=fatalities, hurt=injuries, hm=hazmatreleased, away=injurytreatedaway, tow=towaway,
        cit=cited, citon=citedon, nt=(nottested or None), n=(note or None), u=enteredby)
    return rid


def amend(conn: Connection, accountid: str, recordid: str, **fields) -> None:
    """Answer what was not known at the time. An accident is written up before the citation is
    known, so the record has to be able to learn - this is the only way these columns change."""
    allowed = ("fatalities", "injuries", "hazmatreleased", "injurytreatedaway", "towaway",
               "cited", "citedon", "alcoholtestid", "drugtestid", "nottested", "note", "location")
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    run(conn, f"UPDATE driveraccidents SET {', '.join(f'{k} = :{k}' for k in sets)} "
              "WHERE recordid = :id AND accountid = :a", id=recordid, a=accountid, **sets)


def withdraw(conn: Connection, accountid: str, driverid: str, recordid: str, *,
             reason: str, by: str | None = None) -> dict:
    """Take back an accident recorded against the wrong driver.

    Far less to unwind than a drug test, and for a good reason: whether a test was owed is
    DERIVED from the accident by `decide` rather than written down against the driver, so the
    obligation goes when the accident does. That is the advantage of having computed it.

    What does NOT follow it out are any post-accident tests already linked to it. Those are
    records of collections that happened to somebody, and whether they were also filed against
    the wrong person is a separate question with its own answer - so they are reported rather
    than quietly withdrawn alongside.
    """
    held = row(conn, """
        SELECT recordid, occurredon, location, alcoholtestid, drugtestid FROM driveraccidents
        WHERE recordid = :i AND accountid = :a AND driverid = :d AND withdrawn IS NULL
    """, i=recordid, a=accountid, d=driverid)
    if not held:
        raise ValueError("No such accident on this driver")
    call = decide({**held, **(one(conn, accountid, recordid) or {})})
    undone = []
    if call["required"] is True and not (held["alcoholtestid"] and held["drugtestid"]):
        undone.append("This driver no longer owes a post-accident test for it")
    if call["required"] is None:
        undone.append("The unanswered 382.303 questions on it no longer hold up this driver's file")
    if held["alcoholtestid"] or held["drugtestid"]:
        undone.append("The post-accident tests recorded against it stay on this driver's record - "
                      "withdraw those separately if they were filed in error too")
    run(conn, """
        UPDATE driveraccidents SET withdrawn = :now, withdrawnby = :u, withdrawnreason = :r
        WHERE recordid = :i AND accountid = :a
    """, i=recordid, a=accountid, now=utcnow(), u=by, r=reason[:255])
    return {"accident": held, "undone": undone}


def for_driver(conn: Connection, accountid: str, driverid: str) -> list[dict]:
    """Every accident on this driver, newest first, each with where it stands."""
    out = []
    for acc in rows(conn, """
        SELECT recordid, occurredon, location, fatalities, injuries, hazmatreleased,
               injurytreatedaway, towaway, cited, citedon, alcoholtestid, drugtestid, nottested,
               note, createdon
        FROM driveraccidents WHERE accountid = :a AND driverid = :d AND withdrawn IS NULL
        ORDER BY occurredon DESC, createdon DESC
    """, a=accountid, d=driverid):
        state, says = standing(acc)
        out.append({**acc, **decide(acc), **windows(acc), "state": state, "says": says})
    return out


def one(conn: Connection, accountid: str, recordid: str) -> dict | None:
    return row(conn, "SELECT * FROM driveraccidents "
                     "WHERE accountid = :a AND recordid = :i AND withdrawn IS NULL",
               a=accountid, i=recordid)


__all__ = ["decide", "qualifying", "windows", "standing", "record", "amend", "for_driver", "one"]
