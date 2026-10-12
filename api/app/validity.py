###################################################################################################
# Validity windows - pure functions, no database. This is the whole answer to "did this credential
# cover this pickup?", kept separate so it can be tested exhaustively and explained to an auditor.
#
# A credential covers the half-open interval [start, end):
#   start = issuedon at 00:00
#   end   = the earliest of
#             expireson + 1 day            (the card is good through the whole printed day)
#             issuedon  + maxagedays       (freshness limit: a 365-day background check issued
#                                           2025-06-01 stops covering at 2026-06-01 00:00)
#             revokedon                    (the moment it was pulled; no grace after a revocation)
#           with the requirement's gracedays added to the first two.
# A certificate with no printed expiry is assumed good for its type's defaultvaliddays (CPR: two
# years); that stands in for the printed date and is treated the same way.
# Every time here is the operator's local wall clock (see 001_schema.sql).
###################################################################################################
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal


@dataclass(frozen=True)
class Window:
    start: datetime
    end: datetime | None        # None = open-ended
    endcode: str | None         # expired | maxage | revoked - which limit set `end`

    def covers(self, at: datetime) -> bool:
        return self.start <= at and (self.end is None or at < self.end)


def _midnight(d: date) -> datetime:
    return datetime.combine(d, time.min)


def credential_window(issuedon: date, expireson: date | None, revokedon: datetime | None,
                      maxagedays: int | None, gracedays: int = 0, defaultdays: int | None = None) -> Window:
    grace = timedelta(days=gracedays or 0)
    if expireson is None and defaultdays:
        expireson = issuedon + timedelta(days=defaultdays - 1)
    limits: list[tuple[datetime, str]] = []
    # Order matters only for ties: a revocation is the more serious explanation, then the printed
    # expiry, then the age limit.
    if revokedon is not None:
        limits.append((revokedon, "revoked"))
    if expireson is not None:
        limits.append((_midnight(expireson) + timedelta(days=1) + grace, "expired"))
    if maxagedays is not None:
        limits.append((_midnight(issuedon) + timedelta(days=maxagedays) + grace, "maxage"))
    if not limits:
        return Window(_midnight(issuedon), None, None)
    end, code = min(limits, key=lambda l: l[0])
    return Window(_midnight(issuedon), end, code)


@dataclass(frozen=True)
class CredentialFact:
    """The fields of a credentials row the evaluator needs."""
    recordid: str
    issuedon: date
    expireson: date | None
    revokedon: datetime | None
    revokereason: str | None = None
    amount: Decimal | None = None
    # A driver operating under an exemption or waiver holds no card, so there is no card to age.
    # The type's own age limit is not applied to one - otherwise the record would lapse silently,
    # with no date on screen to explain why.
    exempt: bool = False


@dataclass(frozen=True)
class Verdict:
    outcome: str                  # pass | fail
    reasoncode: str | None        # None on pass; expired | revoked | maxage | missing | notyet
    reason: str | None
    credentialid: str | None
    window: Window | None


def _fmt(d: datetime) -> str:
    return d.strftime("%Y-%m-%d") if d.time() == time.min else d.strftime("%Y-%m-%d %H:%M")


def _money(v) -> str:
    return f"${v:,.0f}"


def credential_as_of(facts: list[CredentialFact], at: datetime, typename: str,
                     maxagedays: int | None, gracedays: int = 0, defaultdays: int | None = None,
                     minamount: Decimal | int | None = None) -> Verdict:
    """Which credential covered `at`, or why none did.

    When more than one covers (a renewal issued before the old card lapsed), the most recently
    issued wins; either would be a correct answer, and the newest is what an auditor expects.
    With minamount (a coverage limit), only credentials at or above it count; one that covered the
    date with too low a limit is named in the failure.
    """
    if minamount is not None:
        enough = [f for f in facts if f.amount is not None and f.amount >= minamount]
        verdict = credential_as_of(enough, at, typename, maxagedays, gracedays, defaultdays)
        if verdict.outcome == "pass":
            return verdict
        short = [(f, credential_window(f.issuedon, f.expireson, f.revokedon, maxagedays, gracedays, defaultdays))
                 for f in facts if f not in enough]
        short = [(f, w) for f, w in short if w.covers(at)]
        if short:
            f, w = max(short, key=lambda fw: fw[0].issuedon)
            reason = (f"{typename} limit not entered (need {_money(minamount)})" if f.amount is None
                      else f"{typename} limit {_money(f.amount)} is below the {_money(minamount)} minimum")
            return Verdict("fail", "belowminimum", reason, f.recordid, w)
        return verdict

    if not facts:
        return Verdict("fail", "missing", f"No {typename} on file", None, None)

    windows = [(f, credential_window(f.issuedon, f.expireson, f.revokedon,
                                     None if f.exempt else maxagedays, gracedays,
                                     None if f.exempt else defaultdays))
               for f in facts]
    covering = [(f, w) for f, w in windows if w.covers(at)]
    if covering:
        f, w = max(covering, key=lambda fw: (fw[0].issuedon, fw[1].end or datetime.max))
        return Verdict("pass", None, None, f.recordid, w)

    started = [(f, w) for f, w in windows if w.start <= at]
    if not started:
        first = min(windows, key=lambda fw: fw[1].start)
        return Verdict("fail", "notyet", f"{typename} not issued until {_fmt(first[1].start)}",
                       first[0].recordid, first[1])

    # The credential that lapsed most recently before the pickup is the one to blame.
    f, w = max(started, key=lambda fw: fw[1].end)
    if w.endcode == "revoked":
        why = f" ({f.revokereason})" if f.revokereason else ""
        reason = f"{typename} revoked {_fmt(w.end)}{why}"
    elif w.endcode == "maxage":
        reason = f"{typename} older than {maxagedays} days as of {_fmt(w.end)}"
    else:
        reason = f"{typename} expired {_fmt(w.end - timedelta(days=1 + (gracedays or 0)))}"
    return Verdict("fail", w.endcode, reason, f.recordid, w)


def vehicle_age_verdict(modelyear: int | None, at: datetime, maxyears: int) -> Verdict:
    if modelyear is None:
        return Verdict("fail", "nomodelyear", "Vehicle model year not on file", None, None)
    age = at.year - modelyear
    if age > maxyears:
        return Verdict("fail", "toold", f"Vehicle is {age} model years old (limit {maxyears})", None, None)
    return Verdict("pass", None, None, None, None)


def _full_years(since: date, at: datetime) -> int:
    d = at.date()
    return d.year - since.year - ((d.month, d.day) < (since.month, since.day))


def driver_age_verdict(dob: date | None, at: datetime, minyears: int) -> Verdict:
    if dob is None:
        return Verdict("fail", "nodob", "Driver date of birth not on file", None, None)
    age = _full_years(dob, at)
    if age < minyears:
        return Verdict("fail", "underage", f"Driver was {age} at pickup (minimum {minyears})", None, None)
    return Verdict("pass", None, None, None, None)


def license_years_verdict(since: date | None, at: datetime, minyears: int) -> Verdict:
    if since is None:
        return Verdict("fail", "nolicensedate", "Date first licensed not on file", None, None)
    years = _full_years(since, at)
    if years < minyears:
        return Verdict("fail", "licensetooshort", f"Licensed {years} years at pickup (minimum {minyears})", None, None)
    return Verdict("pass", None, None, None, None)


def vehicle_mileage_verdict(odometer: int | None, maxmiles: int) -> Verdict:
    if odometer is None:
        return Verdict("fail", "nomileage", "Vehicle odometer not on file", None, None)
    if odometer > maxmiles:
        return Verdict("fail", "toomanymiles", f"Vehicle has {odometer:,} miles (limit {maxmiles:,})", None, None)
    return Verdict("pass", None, None, None, None)


EVIDENCE = {"signature": ("nosignature", "No passenger signature on this leg"),
            "gps": ("nogps", "No GPS verification on this leg")}


def licence_class_verdict(needed: dict, held: str | None, endorsements: str | None) -> Verdict:
    """Whether the licence this driver holds covers the vehicle they drove.

    The vehicle decides what is needed - more than 15 seats including the driver, or 26,001 lb and
    over. What cannot be judged is not failed: a vehicle whose capacity nobody has recorded, and a
    driver whose licence class is not on file, are reported as unmatched rather than as breaches."""
    if not needed.get("known"):
        return Verdict("nosubject", "vehicleunknown",
                       "The vehicle's seating capacity and weight rating are not on file", None, None)
    if not needed.get("cdl"):
        return Verdict("pass", None, None, None, None)
    if not held:
        return Verdict("nosubject", "licenceunknown", "This driver's license class is not on file", None, None)

    held = held.strip().upper()[:1]
    carried = (endorsements or "").upper()
    if held not in ("A", "B", "C"):
        return Verdict("fail", "licenceclass",
                       f"{needed['summary']} is needed to drive this vehicle; this driver holds Class {held}",
                       None, None)
    # A heavier class covers a lighter one: A covers B, B covers C.
    order = {"C": 1, "B": 2, "A": 3}
    if order[held] < order[needed["cdl"]]:
        return Verdict("fail", "licenceclass",
                       f"Class {needed['cdl']} is needed to drive this vehicle; this driver holds Class {held}",
                       None, None)
    if needed.get("endorsement") == "P" and "P" not in carried:
        return Verdict("fail", "endorsement",
                       "This vehicle carries more than 15 including the driver, so a passenger (P) "
                       "endorsement is needed; this driver's license does not carry one", None, None)
    return Verdict("pass", None, None, None, None)


def eligibility_verdict(prohibition, at) -> Verdict:
    """Whether this driver may perform a safety-sensitive function on this leg.

    49 CFR 382.501: not after a positive test or a refusal, and not until the return-to-duty
    process is complete. This is not a document that has run out - it is a person who is barred -
    so it is checked on its own and it overrides whatever else the file holds."""
    if not prohibition:
        return Verdict("pass", None, None, None, None)
    started, reason, cleared = prohibition
    day = at.date() if hasattr(at, "date") else at
    if started > day or (cleared and cleared <= day):
        return Verdict("pass", None, None, None, None)
    return Verdict("fail", "prohibited", reason, None, None)


def annual_review_verdict(mvr_on, reviewed_on, at, maxdays: int = 365,
                          mvr_added=None, review_added=None, finding=None) -> Verdict:
    """Whether this driver's driving record has been reviewed, and reviewed since the last one came
    in. A record obtained after the last review has not been read by anyone; until it has, the driver
    is not qualified to drive."""
    day = at.date() if hasattr(at, "date") else at
    if mvr_on is None and reviewed_on is None:
        return Verdict("nosubject", "noreview", "No driving record and no annual review on file", None, None)
    if reviewed_on is None:
        return Verdict("fail", "noreview",
                       "A driving record is on file and no annual review of it has been recorded", None, None)
    # What the review found is the whole point of making one: a driver found disqualified is
    # disqualified, and stays so until a later review says otherwise.
    if finding == "notqualified":
        return Verdict("fail", "disqualified",
                       f"The review of {reviewed_on:%Y-%m-%d} found this driver disqualified under "
                       "49 CFR 391.15 and removed from safety sensitive functions", None, None)
    # A record that landed after the review was signed has not been reviewed, even where the two
    # carry the same date - the reviewer cannot have read what had not arrived.
    if mvr_on is not None and (mvr_on > reviewed_on or (
            mvr_on == reviewed_on and mvr_added and review_added and mvr_added > review_added)):
        return Verdict("fail", "reviewstale",
                       f"A driving record dated {mvr_on:%Y-%m-%d} arrived after the last review "
                       f"({reviewed_on:%Y-%m-%d}) and has not been reviewed", None, None)
    if (day - reviewed_on).days > maxdays:
        return Verdict("fail", "reviewexpired",
                       f"The last annual review was {reviewed_on:%Y-%m-%d}, more than {maxdays} days "
                       f"before this trip", None, None)
    return Verdict("pass", None, None, None, None)


def trip_evidence_verdict(present: bool, field: str) -> Verdict:
    if present:
        return Verdict("pass", None, None, None, None)
    code, reason = EVIDENCE.get(field, ("noevidence", f"No {field} on this leg"))
    return Verdict("fail", code, reason, None, None)
