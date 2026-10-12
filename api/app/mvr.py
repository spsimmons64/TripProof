###################################################################################################
# Which driving records a driver actually owes, and which are on file.
#
# "Is there an MVR" is the wrong question, and answering it is how a file looks complete while a
# whole state is missing from it. 49 CFR 391.23(a)(1) asks for a record from
#
#     "each driver's licensing authority where the driver held or holds a motor vehicle operator's
#      license or permit during the preceding 3 years"
#
# so the unit is a STATE, over a WINDOW, and the answer is coverage rather than presence.
#
# TWO RULES, AND THEY INVERT EACH OTHER
#
#   391.23(a)(1)  at hire      3 years back    ANY licence or permit
#   391.25(a)     every 12 mo  12 months back  only where a CDL was held
#
# The annual is not another three-year sweep. It is a narrower question asked more often, and
# reading them as the same rule gets one of them wrong in whichever direction you picked.
#
# PER STATE, NOT PER CARD
#
# Both say "each driver's licensing authority". A driver who renewed in Florida three times holds
# three cards and has one licensing authority, so that is one inquiry and one record - not three.
# Treating cards as the unit would have customers buying the same record twice and calling the
# duplicate compliance.
#
# WHEN A STATE HAS NOTHING TO GIVE
#
# Some authorities return no record. The requirement is then met by documenting the good-faith
# effort and that nothing was available - so an inquiry that came back empty is still an inquiry,
# and is recorded as one rather than left looking like a gap nobody chased.
###################################################################################################
from datetime import date, timedelta

from sqlalchemy.engine import Connection

from app.db import rows

# 391.23(a)(1): the three years before the driver was taken on.
HIRE_LOOKBACK = timedelta(days=3 * 365)
# 391.25(a): at least every 12 months, covering at least the preceding 12 months.
ANNUAL_LOOKBACK = timedelta(days=365)

# Which licence classes are commercial. Only 391.25 needs this, and it is a guess dressed as a
# lookup - states do not agree on the letters, and Florida's Class E is ordinary while its Class C
# is commercial. It is the default until somebody says otherwise on the licence itself.
CDL_CLASSES = ("A", "B", "C")


def standing(cov: dict, today: date) -> tuple[str, str] | None:
    """How a rule answered state by state stands as one mark, and the sentence for it.

    A rule like this has no single record to look at, so its standing is the worst thing true of any
    state - except that "worst" is not the same as "most urgent". A request already out is not work
    for this office, so it reads as waiting even where the record it will replace has run out; a
    record sitting unread IS work for this office, so it outranks one that has simply lapsed.

    The order is: waiting on an authority, waiting on a reader, out of date, never asked, done.
    """
    required = cov.get("required") or []
    if not required:
        return None

    def these(pick) -> str:
        return ", ".join(e["state"] for e in required if pick(e))

    out = these(lambda e: e.get("ordered"))
    if out:
        return "ordered", f"Requested from {out}, not back yet."
    unread = these(lambda e: e.get("record") and not e["record"]["norecord"]
                   and e["record"]["reviewstate"] != "reviewed")
    if unread:
        return "review", f"On file for {unread}, waiting to be read."
    lapsed = these(lambda e: e.get("record") and e["expireson"] and e["expireson"] < today)
    if lapsed:
        return "expired", f"The record on file for {lapsed} has run out."
    nothing = these(lambda e: not e.get("record"))
    if nothing:
        return "pending", f"Nothing on file for {nothing}."
    return "satisfied", cov["why"]


def horizon(rule: dict) -> timedelta | None:
    """How long one record answers this rule, or None if it is asked once and done.

    The rule carries this already - it is what `stand()` uses to expire the one record it looks at -
    so coverage asks the rule rather than keeping a second opinion about the same question. Reading
    it off a rule code was worse than wrong: the code being tested reads annual reviews, not driving
    records, so the branch never fired and nothing ever went out of date."""
    if rule.get("recurrence") == "days" and rule.get("recurrencedays"):
        return timedelta(days=int(rule["recurrencedays"]))
    return None


def _held_during(conn: Connection, accountid: str, driverid: str, since: date,
                 cdl_only: bool = False) -> list[dict]:
    """Every licence held on or after `since`.

    A licence counts as held during the window unless it had already expired before the window
    opened. One still marked active counts whatever its dates say - an expired card in the drawer
    is still the authority that issued it."""
    held = rows(conn, """
        SELECT recordid, state, number, classification, issued, expires, active
        FROM driverlicenses
        WHERE accountid = :a AND driverid = :d
          AND (active = 1 OR expires IS NULL OR expires >= :since)
        ORDER BY state, issued DESC
    """, a=accountid, d=driverid, since=since)
    if cdl_only:
        held = [l for l in held if (l["classification"] or "").upper() in CDL_CLASSES]
    return held


def coverage(conn: Connection, accountid: str, driverid: str, *, window: timedelta = HIRE_LOOKBACK,
             cdl_only: bool = False, current_within: timedelta | None = None,
             today: date | None = None) -> dict:
    """What is required, what is covered, and what is missing - by state.

    `current_within` is how recent a record has to be to still count. The hiring inquiry has no
    such limit: it is asked once and answers for that hire. The annual does - a record from two
    years ago does not answer this year's question."""
    today = today or date.today()
    since = today - window
    licences = _held_during(conn, accountid, driverid, since, cdl_only=cdl_only)

    # One entry per licensing authority, carrying the cards it issued so the office can see why the
    # state is on the list at all.
    states: dict[str, dict] = {}
    for l in licences:
        entry = states.setdefault(l["state"], {"state": l["state"], "licences": [], "licenceid": None})
        entry["licences"].append(l["number"])
        # Ordering is done against a licence, so each state carries one to order on: the current
        # card where there is one, otherwise the most recent.
        if entry["licenceid"] is None or l["active"]:
            entry["licenceid"] = l["recordid"]

    if not states:
        return {"required": [], "covered": 0, "missing": [], "complete": None,
                "why": "No licences are on file, so there is nothing to say which states to ask."}

    for got in rows(conn, """
        SELECT l.state, m.recordid, m.issuedon, m.receivedon, m.orderedon, m.norecord, m.documentid,
               m.reviewstate, m.finding, m.note,
               -- What a CDLIS record says about medical qualification, carried so the panel that
               -- reads the record can show what is already recorded rather than an empty form.
               m.selfcert, m.medcertstatus, m.medcertexpires, m.medvariancetype, m.medvariance
        FROM drivermvrs m JOIN driverlicenses l ON l.recordid = m.licenseid
        WHERE m.accountid = :a AND m.driverid = :d AND m.cancelledon IS NULL
        ORDER BY COALESCE(m.issuedon, m.receivedon) DESC
    """, a=accountid, d=driverid):
        entry = states.get(got["state"])
        if not entry:
            continue                       # a record for a state that has dropped out of the window
        if got["receivedon"] or got["norecord"]:
            # Newest first, so the first one seen is this state's latest answer. A record too old to
            # answer the question is kept rather than skipped: dropping it made a state with an
            # out-of-date record on file read identically to a state nobody had ever asked, and it
            # is the difference between work that has lapsed and work never started.
            if not entry.get("record"):
                entry["record"] = got
        elif got["orderedon"] and not entry.get("ordered"):
            entry["ordered"] = got

    required = list(states.values())
    for entry in required:
        # When the record on file stops answering the question. Only a question with a horizon has
        # one: the hiring inquiry is asked once and answers for that hire, so a date there would be
        # invented. A rule that recurs gives its record that long and no longer.
        entry["expireson"] = None
        got = entry.get("record")
        if got and current_within:
            when = got["issuedon"] or got["receivedon"]
            if when:
                if not isinstance(when, date):
                    when = when.date()
                entry["expireson"] = when + current_within
        # On file and still current. A record that has run out is on file and does not count.
        entry["state_covered"] = bool(got) and not (entry["expireson"] and entry["expireson"] < today)
    missing = [e["state"] for e in required if not e["state_covered"]]
    return {
        "required": required,
        "covered": sum(1 for e in required if e["state_covered"]),
        "missing": missing,
        "complete": not missing,
        "why": (f'{len(required) - len(missing)} of {len(required)} '
                f'{"state" if len(required) == 1 else "states"} covered'
                + (f'; missing {", ".join(missing)}' if missing else '')),
    }
