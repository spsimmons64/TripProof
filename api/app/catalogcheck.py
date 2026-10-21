###################################################################################################
# Does the catalog contradict itself?
#
# Every rule carries its own hand-written `applieswhen`, and for a long time nothing compared one
# against another. That is how the carrier came to owe a 49 CFR Part 382 prohibition on a driver
# while being told that the Part 382 programme - the policy, the DER, the random selections, the
# supervisor training, the Clearinghouse account - did not reach it. Twelve company rules asked
# "do you cross a state line?" and the driver rules asked the question that actually decides it.
#
# Nothing was wrong with any ONE of those rules read on its own. They were wrong against each
# other, and reading them one at a time is exactly how you never find that out.
#
# So this reads the catalog as a whole and answers four questions that no single rule can:
#
#   1. REACH      Does a rule decide for itself who the regulation reaches? Part 382 either
#                 applies to this carrier or it does not - it cannot apply to the driver and
#                 not to the employer - so the inputs that settle it belong in one place
#                 (facts._reach) and a rule reads the answer. A rule that reaches past that to
#                 operation.interstate or the roster is writing its own, which is how the
#                 twelve came to disagree.
#   2. VOCABULARY Does a rule gate on a fact nothing produces? Such a rule is dead - the fact is
#                 forever unknown, so the rule is forever undecided, and nobody is told why.
#   3. DEAD ENDS  Does a rule that applies have somewhere to be answered? A requirement with no
#                 form behind it is a red mark the office cannot clear.
#   4. ORPHANS    Does a rule have no evidence source at all?
#
# This is a check, not a fixer. It reports; test_catalog.py is what makes it fail the build.
###################################################################################################
import json
import re

from sqlalchemy.engine import Connection

from app.db import rows

# Which evidence kinds each screen can actually answer. Taken from the dispatch in the three
# detail components - DriverReview.jsx, CompanyRequirements.jsx, VehicleCompliance.jsx. When a
# screen learns a new kind, it goes here too, and until it does the check calls the rule a dead
# end, which is the correct thing to say about it.
DRIVER_KINDS = {
    "annualreview", "applicationanswer", "applicationanswered", "cdlismedical", "credential",
    "driverfact", "drugtest", "employerhistory", "exclusioncheck", "licensecopy", "licensematch",
    "mvr", "report", "roadtest", "signature", "transitmedical",
    # Answered by the dedicated pages rather than by a requirement dialog.
    "dutyhours", "prohibition", "accidentregister",
    # Both license rules are answered on the one Licenses Held screen - whether the license is
    # valid for the work, and whether a copy of it is in the file - and so is driving experience,
    # read off the licenses' issue and original issue dates.
    "license", "drivingexperience",
    # Georgia: the at-fault count off the driving records, and clearance after a securement failure.
    "atfaultcount", "securementclear",
    # 49 CFR 382.305 pool membership, answered from the requirement rather than from a date
    # field in the middle of Driver Information.
    "poolmember",
}
COMPANY_KINDS = {
    "accidentregister", "clearinghouse", "companyrole", "credential", "mcs150",
    "supervisortraining", "policy", "exposuredetermination",
}
VEHICLE_KINDS = {"credential", "vehiclefact", "maintenance", "inspection", "dvir"}
KINDS_FOR = {"driver": DRIVER_KINDS, "company": COMPANY_KINDS, "vehicle": VEHICLE_KINDS}

# Answered somewhere in the product, but NOT where the requirement is shown.
#
# This distinction exists because the first version of this check did not make it, and reported
# three requirements as impossible to clear when all three were recordable - the USDOT number on
# the company profile, the random pool date on driver information, the DVIR on the vehicle's
# inspections tab. "Cannot be cleared" and "cleared two screens away" call for completely
# different work, and saying the first about the second is how a check stops being believed.
#
# It is still a fault: a red mark with no way to act on it from where it is shown sends somebody
# hunting. It is a smaller and different one, so it is reported as itself.
ELSEWHERE = {
    "usdotnumber": "Company - Company profile (USDOT # and MC #)",
}

# A rule that asks for nothing on purpose. `none` removes another rule rather than requesting
# evidence, and a derived rule is answered from the rest of the file.
NO_EVIDENCE_OK = {"none"}
DERIVED_CODES = {"FL_INTRASTATE_FULL"}

# Which regulation a citation belongs to. Part 382 and Part 391 are different questions with
# different answers, so the grain is the PART, not the title: "49 CFR 382.301(a)" and
# "49 CFR 382.601" are one authority, "49 CFR 391.11" is another.
_PART = re.compile(r"(\d+)\s+CFR\s+(?:Part\s+)?(\d+)")

# The facts that decide whether a body of regulation reaches an operation at all. They are
# inputs to facts._reach and nothing else: a rule that reads one is deciding reach for itself,
# in its own words, with no way for anybody to notice it has drifted from the rule next to it.
#
# This list is the whole of the lesson. Twelve company rules read `operation.interstate` and
# concluded that a Florida intrastate CDL carrier owed no Part 382 programme, while the driver
# rules reached the opposite conclusion about the same carrier on the same day.
REACH_INPUTS = {
    "operation.interstate",
    "company.cdldrivers", "company.cmvdrivers", "company.heavydrivers",
    "fleet.cdl_required", "fleet.cmv_federal", "fleet.cmv_florida",
}

# The rules that are ABOUT a State adopting the federal regulations. Being written in terms of
# the state line is what they are for, so they are the one place it is still the right fact.
ADOPTION_RULES = {"FL_INTRASTATE_382", "FL_INTRASTATE_FULL"}


def authority_of(citation: str | None) -> str | None:
    """The regulation a rule belongs to, as "49 CFR 382". None where it is not a CFR citation -
    a state statute or a contract term is not something other rules can be checked against."""
    if not citation:
        return None
    m = _PART.search(citation)
    return f"{m.group(1)} CFR {m.group(2)}" if m else None


def facts_in(applieswhen) -> set[str]:
    """Every fact a condition reads, however deeply nested."""
    if applieswhen is None:
        return set()
    if isinstance(applieswhen, str):
        try:
            applieswhen = json.loads(applieswhen)
        except (ValueError, TypeError):
            return set()
    found: set[str] = set()

    def walk(node):
        if isinstance(node, list):
            for n in node:
                walk(n)
        elif isinstance(node, dict):
            if "fact" in node:
                found.add(node["fact"])
            for key in ("all", "any", "none", "not"):
                if key in node:
                    walk(node[key])
    walk(applieswhen)
    return found


def catalog(conn: Connection) -> list[dict]:
    return rows(conn, """
        SELECT code, name, subject, citation, authority, applieswhen, evidencekind,
               evidencesource, gate, duestage
        FROM compliancerules
        WHERE effectiveto IS NULL
        ORDER BY subject, code
    """)


def check(conn: Connection, known_facts: set[str]) -> dict[str, list[dict]]:
    """Every contradiction the catalog contains, by kind. Empty lists mean a clean catalog."""
    held = catalog(conn)
    out: dict[str, list[dict]] = {"reach": [], "vocabulary": [], "deadend": [], "orphan": [],
                                  "offscreen": []}

    # 1. REACH. A rule may add its own trigger - a prohibition fires on driver.prohibited, a
    #    post-accident test on driver.postaccidentowed - but it may not decide for itself who
    #    the regulation reaches. That is settled once, in facts._reach, and read as reach.*.
    for r in held:
        if r["code"] in ADOPTION_RULES:
            continue
        handrolled = sorted(facts_in(r["applieswhen"]) & REACH_INPUTS)
        if handrolled:
            out["reach"].append({"code": r["code"], "subject": r["subject"],
                                 "authority": authority_of(r["citation"]),
                                 "facts": handrolled})

    for r in held:
        # 2. VOCABULARY. A fact nothing produces can never be true, so the rule can never be
        #    decided, and it sits on the list saying nothing for ever.
        unknown = sorted(facts_in(r["applieswhen"]) - known_facts)
        if unknown:
            out["vocabulary"].append({"code": r["code"], "facts": unknown})

        # 3 and 4. Somewhere to answer it.
        kind = (r["evidencesource"] or "").partition(":")[0]
        if not r["evidencesource"]:
            if r["evidencekind"] not in NO_EVIDENCE_OK and r["code"] not in DERIVED_CODES:
                out["orphan"].append({"code": r["code"], "subject": r["subject"]})
        elif kind in ELSEWHERE:
            out["offscreen"].append({"code": r["code"], "subject": r["subject"],
                                     "source": r["evidencesource"], "where": ELSEWHERE[kind]})
        elif kind not in KINDS_FOR.get(r["subject"], set()):
            out["deadend"].append({"code": r["code"], "subject": r["subject"],
                                   "source": r["evidencesource"]})
    return out


def report(found: dict[str, list[dict]]) -> str:
    lines = []
    for item in found["reach"]:
        lines.append(f"{item['code']} ({item['subject']}): decides for itself who "
                     f"{item['authority'] or 'this regulation'} reaches, on "
                     f"{', '.join(item['facts'])} - that belongs in facts._reach, read back "
                     f"as a reach.* fact")
    for item in found["vocabulary"]:
        lines.append(f"{item['code']}: gates on a fact nothing produces - {', '.join(item['facts'])}")
    for item in found["deadend"]:
        lines.append(f"{item['code']} ({item['subject']}): no screen answers "
                     f"'{item['source']}' - this requirement cannot be cleared")
    for item in found["orphan"]:
        lines.append(f"{item['code']} ({item['subject']}): no evidence source at all")
    for item in found.get("offscreen", []):
        lines.append(f"{item['code']} ({item['subject']}): answered on another screen - "
                     f"{item['where']} - so the requirement showing the mark cannot be acted on")
    return "\n".join(lines)


__all__ = ["authority_of", "facts_in", "catalog", "check", "report", "snapshot", "diff",
           "REACH_INPUTS", "ADOPTION_RULES",
           "DRIVER_KINDS", "COMPANY_KINDS", "VEHICLE_KINDS"]


###################################################################################################
# Proving a catalog change did what was intended, and only that.
#
# The check above says the catalog does not contradict ITSELF. This says a change to it does not
# quietly move something nobody was looking at. Take a snapshot of where every real subject stands
# on every rule, make the change, take another, and print the difference. A rule edit that was
# meant to turn eight company requirements on and in fact also retired one on three drivers shows
# up as three lines rather than as a complaint six weeks later.
#
# This is the whole answer to "how do we move forward without breaking what we have": not care,
# not memory - a list of exactly what moved.
###################################################################################################

def snapshot(conn: Connection, accountid: str) -> dict[str, str]:
    """Where every subject in one account stands on every rule that reaches it.

    Keyed "subject:id:CODE" so two snapshots can be subtracted. The value carries the applies
    state as well as the status, because a rule going from "does not reach you" to "nothing on
    file" is the change that matters most and both read as not-satisfied.
    """
    from app import rules as engine
    from app.facts import assemble

    out: dict[str, str] = {}

    def put(subject: str, sid: str, items: list[dict]) -> None:
        for i in items:
            reach = {True: "applies", False: "no", None: "unknown"}[i.get("applies")]
            out[f"{subject}:{sid}:{i['code']}"] = f"{reach}/{i.get('status')}"

    company = assemble(conn, accountid, None)["facts"]
    put("company", accountid, engine.for_company(conn, accountid, company))
    for (did,) in conn.exec_driver_sql(
            "SELECT recordid FROM drivers WHERE accountid = %s AND deleted IS NULL", (accountid,)):
        put("driver", did, engine.for_driver(conn, accountid, did,
                                             assemble(conn, accountid, did)["facts"]))
    for (vid,) in conn.exec_driver_sql(
            "SELECT recordid FROM vehicles WHERE accountid = %s AND deleted IS NULL", (accountid,)):
        put("vehicle", vid, engine.for_vehicle(conn, accountid, vid, company))
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> list[str]:
    """Every subject/rule whose standing changed, as one line each."""
    moved = []
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key, "-"), after.get(key, "-")
        if was != now:
            moved.append(f"{key}: {was} -> {now}")
    return moved
