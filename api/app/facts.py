###################################################################################################
# The facts a rule is judged against.
#
# One place assembles everything the engine is allowed to know, so a rule never reaches into the
# database itself and never decides anything from a field it happened to find. A rule asks about a
# named fact; this decides what that fact is.
#
# Three kinds of fact live here, and the difference matters:
#
#   recorded    somebody typed it in - seats, GVWR, whether passengers are carried for compensation
#   derived     worked out from recorded facts - whether the vehicle is a commercial motor vehicle
#   unanswered  nobody has said yet, which is None and is NOT False
#
# The third one is the whole reason this module exists. "We have not asked whether this company
# drives across a state line" and "this company does not drive across a state line" lead to
# opposite answers about whether Part 391 reaches a driver, and a system that quietly treats the
# first as the second will tell somebody they are qualified when nobody has checked.
#
# Driver qualification is worked out against the FLEET rather than against one vehicle, because at
# the point it matters - before the driver is hired - there is no trip and no assignment. If the
# company runs anything that is a commercial motor vehicle, a driver who may be put in it owes what
# that vehicle brings with it. A trip-time answer narrows this to the vehicle actually used; that
# is the same fact set with `fleet` replaced by one vehicle.
###################################################################################################
import json
from sqlalchemy.engine import Connection

from app import vehicleclass
from datetime import date

from app import exposure as _exposure
from app import randompool as _randompool
from app import payerlines as _payerlines
from app.db import row, rows


def _any(values: list, key: str) -> bool | None:
    """True if any says so, None if none says so but some could not say, else False."""
    seen = [v[key] for v in values]
    if any(v is True for v in seen):
        return True
    if any(v is None for v in seen):
        return None
    return False


def fleet_facts(conn: Connection, accountid: str) -> dict:
    """What the company runs, reduced to what it means for a driver.

    A fleet is a commercial motor vehicle operation if any vehicle in it is one - the driver does
    not know which van they will be handed."""
    held = rows(conn, """
        SELECT recordid, externalid, seats, gvwr, gcwr, forcompensation, lift
        FROM vehicles WHERE accountid = :a AND deleted IS NULL
    """, a=accountid)
    if not held:
        return {"vehicles": 0, "cmv_federal": None, "cmv_florida": None, "cdl_required": None,
                "heaviest_gvwr": None, "wheelchair": None, "multiplecmv": None,
                "why": "No vehicles are on file, so nothing can be said about what the drivers drive."}

    worked = [dict(v, **vehicleclass.facts(v)) for v in held]
    weights = [v["gvwr"] for v in worked if v["gvwr"]]
    # A determination on file outranks the figures, unit by unit, as it does for the fleet below.
    judged = {r["vehicleid"]: r["fmcsa"] for r in rows(conn, """
        SELECT vehicleid, fmcsa FROM vehicleassessments WHERE accountid = :a AND fmcsa IS NOT NULL
    """, a=accountid)}
    def cmv(v):
        said = judged.get(v["recordid"])
        return True if said == "covered" else False if said == "notcovered" else v["cmv_federal"]
    counted = [cmv(v) for v in worked]
    out = {
        "vehicles": len(worked),
        # Derived, never asked. The lift is already recorded per vehicle, and asking the office to
        # re-state it as a yes/no is how two answers to one question drift apart.
        "wheelchair": any(v.get("lift") for v in worked),
        "cmv_federal": _any(worked, "cmv_federal"),
        "cmv_florida": _any(worked, "cmv_florida"),
        "cdl_required": _any(worked, "cdl_required"),
        "heaviest_gvwr": max(weights) if weights else None,
        # 49 CFR 396.11(a)(1): a carrier operating only one commercial motor vehicle does not
        # prepare driver vehicle inspection reports. Two or more settles it; one, with units
        # nobody has measured, does not.
        "multiplecmv": (True if counted.count(True) >= 2
                        else None if counted.count(True) + counted.count(None) >= 2 else False),
    }
    # Which vehicle carried the answer, so a surprising result can be traced to the unit that caused
    # it rather than to the fleet in general.
    for key in ("cmv_federal", "cmv_florida", "cdl_required"):
        if out[key] is True:
            cause = next(v for v in worked if v[key] is True)
            out[f"{key}_because"] = cause["externalid"] or cause["recordid"]
    unknown = [v["externalid"] or v["recordid"] for v in worked if v["cmv_federal"] is None]
    out["why"] = (f"{len(worked)} vehicle{'s' if len(worked) != 1 else ''} on file"
                  + (f"; not enough recorded on {', '.join(unknown)}" if unknown else ""))
    return out


def _postaccident_owed(conn: Connection, accountid: str, driverid: str) -> bool | None:
    """Whether 382.303 asked for a test on any accident this driver has, and it is not on file.

    Three-valued, because an accident nobody has finished answering is not an accident that needed
    no test. The decision itself lives in app/accidents.py and is read from here rather than
    repeated - two places deciding when a test was owed is two places to be wrong in."""
    from app import accidents                      # late: accidents reads facts of its own
    unsure = False
    for crash in accidents.for_driver(conn, accountid, driverid):
        call = accidents.decide(crash)
        # 382.303(d)(2): where a test was not given, the reason recorded is the answer.
        if crash.get("nottested"):
            continue
        if call["required"] is None:
            unsure = True
        elif call["required"] and not (crash.get("alcoholtestid") and crash.get("drugtestid")):
            return True
    return None if unsure else False


def _spe_variance(conn: Connection, accountid: str, driverid: str) -> bool | None:
    """Whether the newest driving record carrying medical information names an SPE certificate."""
    got = row(conn, """
        SELECT medvariancetype FROM drivermvrs
        WHERE accountid = :a AND driverid = :d AND receivedon IS NOT NULL
          AND medcertstatus IS NOT NULL
        ORDER BY issuedon DESC, receivedon DESC LIMIT 1
    """, a=accountid, d=driverid)
    # No record carrying medical information at all is not "no variance" - nobody has looked.
    return None if not got else got["medvariancetype"] == "spe"


def _followup_owed(conn: Connection, accountid: str, driverid: str) -> bool:
    """Whether a SAP's follow-up schedule has tests still owed on it.

    Counted rather than assumed: the plan says how many, the tests on file say how many have been
    done, and the difference is the obligation. A plan with no number on it owes nothing TripProof
    can measure, and saying otherwise would put a driver on a hard stop with no way off it."""
    plan = row(conn, """
        SELECT MAX(followuptests) AS owed, MAX(followupuntil) AS until
        FROM driverprohibitions
        WHERE accountid = :a AND driverid = :d AND followuptests IS NOT NULL
          AND withdrawn IS NULL
    """, a=accountid, d=driverid)
    owed = (plan or {}).get("owed")
    if not owed:
        return False
    done = row(conn, """
        SELECT COUNT(*) AS n FROM drugtests
        WHERE accountid = :a AND driverid = :d AND reason = 'followup'
          AND withdrawn IS NULL
    """, a=accountid, d=driverid)["n"]
    return done < int(owed)


# What a driver's `operation` means. One definition, read by the driver facts and by the company
# facts below, because a company that must register with the Clearinghouse is exactly a company
# with a driver TripProof already asks Clearinghouse questions of.
CMV_OPERATIONS = ("cmv", "cdl", "cdlheavy")
CDL_OPERATIONS = ("cdl", "cdlheavy")
# 26,001 lb or more - the weight F.S. 316.302(1)(b) names when it adopts the federal rules for
# intrastate operation.
HEAVY_OPERATIONS = ("cdlheavy",)


def vehicle_facts(conn: Connection, accountid: str, vehicleid: str) -> dict:
    """What one vehicle is, for the rules that ask about it.

    The measurements are already on the record and `vehicleclass` already reads them, so nothing is
    asked twice: whether this unit is a commercial motor vehicle is the same answer here as on its
    own page. Three-valued where the record does not say - a vehicle with no GVWR is not a vehicle
    anybody has established the weight of."""
    got = row(conn, """
        SELECT recordid, externalid, seats, gvwr, gcwr, forcompensation, lift, modelyear
        FROM vehicles WHERE recordid = :v AND accountid = :a AND deleted IS NULL
    """, v=vehicleid, a=accountid)
    if not got:
        return {}
    worked = vehicleclass.facts(got)
    return {
        **_vehicle_transit(conn, accountid, vehicleid),
        "vehicle.cmv_federal": worked.get("cmv_federal"),
        "vehicle.cmv_florida": worked.get("cmv_florida"),
        "vehicle.cdl_required": worked.get("cdl_required"),
        "vehicle.seats": got.get("seats"),
        "vehicle.gvwr": got.get("gvwr"),
        # A tick box on the vehicle record, so an empty one is somebody saying no - the same
        # reasoning the driver's own tick boxes carry.
        "vehicle.lift": bool(got.get("lift")),
        "vehicle.forcompensation": bool(got.get("forcompensation")),
    }


def _vehicle_transit(conn: Connection, accountid: str, vehicleid: str) -> dict:
    """Whether each transit safety program that governs vehicles reaches this one.

    A program that does not touch the company's home or operating states does not reach it, and
    neither does one the company has determined it is not covered by. Otherwise the vehicle's own
    determination answers - and a vehicle nobody has determined, or one under review, is unknown,
    never exempt."""
    company = row(conn, """
        SELECT a.state, p.operatingstates FROM accounts a
        LEFT JOIN companyprofiles p ON p.accountid = a.recordid WHERE a.recordid = :a
    """, a=accountid) or {}
    states = {s for s in (company.get("operatingstates") or "").split(",") if s} | {
        company.get("state"), "US"}
    said = {r["programcode"]: r["determination"] for r in rows(conn, """
        SELECT programcode, determination FROM companytransitprograms WHERE accountid = :a
    """, a=accountid)}
    held = {r["programcode"]: r["determination"] for r in rows(conn, """
        SELECT programcode, determination FROM vehicletransitprograms
        WHERE accountid = :a AND vehicleid = :v
    """, a=accountid, v=vehicleid)}
    out = {}
    for p in rows(conn, "SELECT code, state FROM transitsafetyprograms WHERE active = 1 AND vehicles = 1"):
        if p["state"] not in states or said.get(p["code"]) == "notcovered":
            out[f"vehicle.transit.{p['code']}"] = False
        else:
            out[f"vehicle.transit.{p['code']}"] = {"covered": True, "notcovered": False}.get(
                held.get(p["code"]))
    return out


# The day 49 CFR Part 380 Subpart F took effect. A license or endorsement obtained before it was
# obtained under the old rules and is not reopened by this one.
ELDT_FROM = date(2022, 2, 7)
# What entry-level training is required FOR: the CDL classes, and the endorsements that need it
# the first time they are held.
ELDT_CLASSES = ("A", "B")
ELDT_ENDORSEMENTS = ("P", "S", "H")


def _eldt_reaches(conn: Connection, accountid: str, driverid: str) -> bool | None:
    """Whether entry-level driver training reaches this driver, from their licensing history.

    True where a CDL class or a P/S/H endorsement on file was issued on or after 7 February
    2022. False where licenses are on file and all of it predates that. None where nothing is
    recorded, because an empty licensing history is not evidence of an exemption.

    A RENEWAL carries a recent issue date without being a first obtainment, which is why an
    earlier license of the same class counts as the first and clears it: the oldest record of
    the class is what says when the driver first held it. Where the only record is a recent one,
    this says it reaches them - the office then either files the training record or files the
    evidence that the driver held the class before the rule, and either answers it.
    """
    held = rows(conn, """
        SELECT classification, endorsements, issued FROM driverlicenses
        WHERE accountid = :a AND driverid = :d
        ORDER BY issued
    """, a=accountid, d=driverid)
    if not held:
        return None
    for l in held:
        cls = (l["classification"] or "").upper()
        ends = (l["endorsements"] or "").upper()
        if not l["issued"]:
            continue
        first_of_class = min((x["issued"] for x in held
                              if (x["classification"] or "").upper() == cls and x["issued"]),
                             default=l["issued"])
        if cls in ELDT_CLASSES and first_of_class >= ELDT_FROM:
            return True
        for e in ELDT_ENDORSEMENTS:
            if e not in ends:
                continue
            first_with = min((x["issued"] for x in held
                              if e in (x["endorsements"] or "").upper() and x["issued"]),
                             default=l["issued"])
            if first_with >= ELDT_FROM:
                return True
    return False


def company_drivers(conn: Connection, accountid: str) -> dict:
    """What this company's roster means for the obligations that fall on the EMPLOYER.

    Read off the drivers rather than off the fleet. An employer's duty to query the Clearinghouse
    follows the drivers it employs - a CDL driver may be in a leased vehicle, a customer's vehicle,
    or one nobody has recorded yet - and reading it off the fleet is how TripProof came to ask a
    driver for a pre-employment query while telling the company it need not be registered to run
    one.

    Three-valued. An empty roster says nothing either way; it does not say no."""
    held = rows(conn, """
        SELECT operation FROM drivers
        WHERE accountid = :a AND deleted IS NULL AND stub = 0 AND terminatedon IS NULL
    """, a=accountid)
    if not held:
        return {"cdldrivers": None, "cmvdrivers": None, "heavydrivers": None,
                "why": "No drivers are on file, so nothing can be said about who this company "
                       "employs."}
    return {
        "cdldrivers": any(d["operation"] in CDL_OPERATIONS for d in held),
        "cmvdrivers": any(d["operation"] in CMV_OPERATIONS for d in held),
        "heavydrivers": any(d["operation"] in HEAVY_OPERATIONS for d in held),
        "why": f"{len(held)} driver{'s' if len(held) != 1 else ''} on file",
    }


# Which regulations reach this operation - answered ONCE, here.
#
# This exists because it did not. Every rule carried its own hand-written `applieswhen`, so the
# question "is this carrier subject to Part 382?" was re-answered in eighty-seven places and
# nothing ever compared one answer against another. Twelve company rules settled it by asking
# `operation.interstate` - do you cross a state line - and the driver rules asked what actually
# decides it. The result was a carrier that owed a Part 382 prohibition on its driver and owed
# no Part 382 programme: no policy, no DER, no random selections, no supervisor training, no
# Clearinghouse account. Each of those rules was defensible read on its own. They were wrong
# against each other, which is the one thing reading them one at a time can never show.
#
# So reach is a fact now, not a habit. A rule says {"fact": "reach.part382", "is": true} and adds
# whatever trigger is its own on top; it does not get to re-decide who the regulation reaches.
# app/catalogcheck.py fails the build when a rule tries.
#
# Three-valued throughout. "Nobody has told us yet" is not "no" - a company with an empty roster
# and no vehicles on file is not a company the federal rules have been shown to miss.
def _reach(company: dict, fleet: dict, roster: dict, driver: dict | None = None) -> dict:
    """Subject to the FMCSRs, and to the Parts that sit under them.

    Computed for whoever is being asked about. The carrier's reach and one driver's reach are
    not the same question and must not share an answer: a company with a single 26,001 lb unit
    IS subject to the FMCSRs, while the driver who only ever takes out a 12,000 lb van is not
    reached by F.S. 316.302(1)(b) at all. Answering the driver from the company's reach would
    pull the whole of Part 391 onto a van driver, which is the mirror image of the bug this
    exists to fix and would be just as wrong."""
    # Crossing a state line settles it outright: 49 CFR 390.3(a).
    interstate = company.get("operation.interstate")
    if interstate is True:
        fmcsr = True
    else:
        # Otherwise the state may have adopted them. Florida adopts the FMCSRs for intrastate
        # operation of vehicles rated 26,001 lb or more - F.S. 316.302(1)(b) - which is the same
        # statute FL_INTRASTATE_FULL already cites at the driver. It applied there and nowhere
        # else, so the carrier running those drivers was told the federal rules missed it.
        heavy = _or(roster.get("heavydrivers"), fleet.get("cmv_florida"))
        if company.get("company.state") == "FL" and heavy is True:
            fmcsr = True
        elif interstate is False and heavy is False:
            fmcsr = False
        else:
            fmcsr = None                      # not enough on file to say either way
    # Part 382 follows the CDL requirement, not the state line: 49 CFR 382.103(a)(1) reaches
    # every employer of a driver operating a vehicle that requires a CDL.
    cdl = _or(roster.get("cdldrivers"), fleet.get("cdl_required"))
    cmv = _or(roster.get("cmvdrivers"), fleet.get("cmv_federal"))
    out = {
        "reach.fmcsr": fmcsr,
        "reach.part382": _and(fmcsr, cdl),
        "reach.part390": _and(fmcsr, cmv),
        "reach.part391": _and(fmcsr, cmv),
        # Operating authority and registration are about interstate carriage itself, not about
        # which safety rules a state has adopted, so these stay on the state line.
        "reach.authority": interstate,
    }
    if driver is None:
        return out

    # This driver, now. Crossing a state line in a commercial vehicle settles it; otherwise
    # Florida's adoption reaches the heavy ones only, which is the line F.S. 316.302(1)(b)
    # draws at 26,001 lb and the same line FL_INTRASTATE_FULL already cites. Lighter intrastate
    # commercial drivers are reached for drug and alcohol testing by FL_INTRASTATE_382 instead,
    # which is why this does not quietly sweep them into the whole of Part 382.
    byflorida = company.get("company.state") == "FL" and interstate is False
    def mine(qualifier: bool | None) -> bool | None:
        if interstate is True:
            return qualifier
        if byflorida:
            return _and(qualifier, driver.get("driver.heavy"))
        if interstate is False:
            return False
        return None                      # nobody has said whether they cross a state line
    out["reach.fmcsr"] = mine(driver.get("driver.cmv"))
    # Part 391 reached by the federal rules themselves - across a state line - rather than by
    # Florida's adoption of them. The difference is the age: F.S. 316.302(2)(a) excuses the
    # intrastate driver from 391.11(b)(1)'s twenty-one, and (4) puts the floor at eighteen.
    out["reach.part391interstate"] = (driver.get("driver.cmv") if interstate is True
                                      else False if interstate is False or byflorida else None)
    out["reach.part391"] = out["reach.fmcsr"]
    out["reach.part390"] = out["reach.fmcsr"]
    out["reach.part382"] = mine(driver.get("driver.cdl"))
    return out


def _and(a: bool | None, b: bool | None) -> bool | None:
    """Three-valued AND: one definite no settles it; otherwise unknown beats yes."""
    if a is False or b is False:
        return False
    return None if a is None or b is None else True


def _or(a: bool | None, b: bool | None) -> bool | None:
    """Three-valued OR: one definite yes settles it; otherwise unknown beats no."""
    if a is True or b is True:
        return True
    return None if a is None or b is None else False


def assemble(conn: Connection, accountid: str, driverid: str | None = None,
             vehicleid: str | None = None, states: list[str] | None = None) -> dict:
    """Every fact a rule may ask about, flattened to dotted names.

    Flat on purpose: a rule says {"fact": "fleet.cmv_federal"} and nothing about how that was
    reached. When trip-time evaluation arrives it adds `trip.*` here and no rule changes."""
    company = row(conn, "SELECT state FROM accounts WHERE recordid = :a", a=accountid) or {}
    fleet = fleet_facts(conn, accountid)
    roster = company_drivers(conn, accountid)

    facts = {
        "company.state": company.get("state"),
        "company.cdldrivers": roster["cdldrivers"],
        "company.cmvdrivers": roster["cmvdrivers"],
        "company.heavydrivers": roster["heavydrivers"],
        "fleet.vehicles": fleet["vehicles"],
        "fleet.cmv_federal": fleet["cmv_federal"],
        "fleet.cmv_florida": fleet["cmv_florida"],
        "fleet.cdl_required": fleet["cdl_required"],
        "fleet.heaviest_gvwr": fleet["heaviest_gvwr"],
        "fleet.wheelchair": fleet["wheelchair"],
        "fleet.multiplecmv": fleet.get("multiplecmv"),
    }

    # A vehicle somebody has determined to be FMCSA-covered is covered, whatever its weight and
    # seats say; where every vehicle has been determined not covered, the fleet is not. Otherwise
    # the figures on the vehicles decide, as before.
    judged = rows(conn, """
        SELECT a.fmcsa FROM vehicleassessments a JOIN vehicles v ON v.recordid = a.vehicleid
        WHERE a.accountid = :a AND v.deleted IS NULL AND v.stub = 0 AND a.fmcsa IS NOT NULL
    """, a=accountid)
    if any(j["fmcsa"] == "covered" for j in judged):
        facts["fleet.cmv_federal"] = True
    elif judged and len(judged) == fleet["vehicles"] and all(j["fmcsa"] == "notcovered" for j in judged):
        facts["fleet.cmv_federal"] = False

    # What the company has said about itself. The questions are rows in companyquestions, so a new
    # one is data: it names the fact it answers, and rules refer to that name.
    for q in rows(conn, """
        SELECT q.factname, a.answer
        FROM companyquestions q
        LEFT JOIN companyanswers a ON a.code = q.code AND a.accountid = :a
        WHERE q.active = 1
    """, a=accountid):
        facts[q["factname"]] = None if q["answer"] is None else bool(q["answer"])

    # The operating profile, where one has been kept, answers what the yes/no questions answered
    # before - with dates and history. A program on file says whether Medicaid trips are carried;
    # a question still answers where nothing has been recorded.
    profile = row(conn, "SELECT employmentmodel, fdot1490, operatingstates FROM companyprofiles "
                        "WHERE accountid = :a", a=accountid) or {}
    # The programs are whatever the company's active payer lines carry - nobody enters them twice.
    programs = rows(conn, f"""
        SELECT program, state FROM companycontracts c
        WHERE accountid = :a AND status = 'active' AND program IS NOT NULL AND {_payerlines.live("c")}
          AND (effectivefrom IS NULL OR effectivefrom <= CURDATE())
          AND (effectiveto IS NULL OR effectiveto >= CURDATE())
    """, a=accountid)
    if row(conn, "SELECT 1 AS x FROM companycontracts WHERE accountid = :a LIMIT 1", a=accountid):
        facts["company.medicaid"] = any(p_["program"] == "medicaid" for p_ in programs)
    facts["company.programs"] = sorted({p_["program"] for p_ in programs})
    # WHICH state's Medicaid program the company carries for: the states of its Medicaid payer
    # lines. A Florida provider that drives into Georgia, with no Georgia Medicaid line, is not
    # held to Georgia's NEMT rules - operating somewhere is not being enrolled there. A line with
    # no state is the company's home state.
    if "company.medicaid" in facts:
        facts["company.medicaidstates"] = sorted({
            (p_["state"] or company.get("state") or "").upper()
            for p_ in programs if p_["program"] == "medicaid"} - {""})
    facts["company.employmentmodel"] = profile.get("employmentmodel")
    facts["company.operatingstates"] = [x for x in (profile.get("operatingstates") or "").split(",") if x]
    # Transit safety programs: one determination per program - covered / notcovered / review.
    # Review, or no answer, is unknown - never exempt.
    determined = {r["programcode"]: r["determination"] for r in rows(conn, """
        SELECT programcode, determination FROM companytransitprograms WHERE accountid = :a
    """, a=accountid)}
    transit = [r["code"] for r in rows(conn, "SELECT code FROM transitsafetyprograms WHERE active = 1")]
    for code in transit:
        facts[f"company.transit.{code}"] = {"covered": True, "notcovered": False}.get(determined.get(code))
    facts["company.transitdetermined"] = determined
    # The Florida names the existing rules read.
    facts["company.fdot1490"] = facts.get("company.transit.FL_1490")
    facts["company.fdot1490set"] = determined.get("FL_1490")

    # 29 CFR 1910.1030(c)(2). Read from the determination the company signed, not from a
    # question on the applicability screen: the written determination IS the answer, and a tick
    # beside it would be a second copy free to disagree with the page an inspector reads.
    # None until one is signed, which is "nobody has looked" and not "no exposure".
    facts["company.exposure"] = _exposure.exposed(conn, accountid)

    # A trip's own states, pickup first: where the trip happens decides which state's rules reach
    # it, not where the company is headquartered. One that crosses a state line is interstate
    # commerce whatever the company says of itself - 49 CFR 390.5 - and the reach below reads that.
    if states:
        facts["company.state"] = states[0]
        facts["company.operatingstates"] = list(states)
        facts["trip.state"] = states[0]
        facts["trip.states"] = list(states)
        if len(states) > 1:
            facts["operation.interstate"] = True

    # Last, because reach reads what the company has just said about itself.
    facts.update(_reach(facts, fleet, roster))

    if vehicleid:
        facts.update(vehicle_facts(conn, accountid, vehicleid))


    if driverid:
        driver = row(conn, """
            SELECT operation, chapter1490, licenseclass, endorsements, endorsementsneeded, status,
                   engagement,
                   englishproficient, dob, TIMESTAMPDIFF(YEAR, dob, CURDATE()) AS age
            FROM drivers WHERE recordid = :d AND accountid = :a AND deleted IS NULL
        """, d=driverid, a=accountid) or {}
        facts.update({
            "driver.licenseclass": (driver.get("licenseclass") or "").upper() or None,
            "driver.endorsements": (driver.get("endorsements") or "").upper() or None,
            "driver.status": driver.get("status"),
            # What this driver is being qualified to operate. A statement of intent, and
            # deliberately not read off the fleet: a company buying a bus next quarter has to be
            # able to qualify its drivers for it now, and buying one must not silently disqualify
            # everybody already on the roster.
            #
            # These are two-valued, not three. Every one of them is a tick box on the driver's
            # record, and a tick box has no "not answered" - an empty one is somebody saying no.
            # Reporting an unticked box as undecidable would put the control and the engine at odds,
            # which is exactly how an answered question came to read as unanswered once already.
            # Derived from one ordered answer, so they cannot contradict each other.
            "driver.cmv": driver.get("operation") in CMV_OPERATIONS,
            "driver.cdl": driver.get("operation") in CDL_OPERATIONS,
            "driver.heavy": driver.get("operation") == "cdlheavy",
            # Florida's name for the 14-90 program, set from the program facts below.
            "driver.chapter1490": None,
            # The broker contracts this driver is approved to work.
            "driver.contracts": [x["contractid"] for x in rows(conn, """
                SELECT contractid FROM driverauthorizations
                WHERE accountid = :a AND driverid = :d AND endedon IS NULL
            """, a=accountid, d=driverid)],
            # Employee or not. The driver's own classification first, then the company's model;
            # a mixed or unset model leaves it unknown.
            "driver.employee": ({"employee": True, "contractor": False, "subcontracted": False}
                                .get(driver.get("engagement"))
                                if driver.get("engagement")
                                else {"employee": True, "contractor": False}
                                .get(facts.get("company.employmentmodel"))),
            # Whether a prohibition is in force RIGHT NOW - 49 CFR 382.501. Two-valued: the
            # record either has an uncleared bar on it or it does not.
            #
            # This exists because the testing module and the compliance engine had each
            # answered it separately and come to different conclusions. A driver with an open
            # positive read as prohibited on his own testing page and "Clear to drive" on the
            # company dashboard, because the dashboard asks the ENGINE for hard stops and the
            # engine had never been told prohibitions exist.
            "driver.prohibited": bool(row(conn, """
                SELECT 1 AS x FROM driverprohibitions
                WHERE accountid = :a AND driverid = :d AND clearedon IS NULL
                  AND withdrawn IS NULL LIMIT 1
            """, a=accountid, d=driverid)),
            # 49 CFR Part 380 Subpart F. Entry-level driver training is tied to GETTING the
            # license or the endorsement, not to being hired - a driver who has held a Class B
            # since 2019 does not repeat it because a new company took them on. So this is read
            # off the licensing history rather than asked of every CDL holder: it applies where
            # a CDL class or a P, S or H endorsement on file was issued on or after the rule's
            # compliance date, and not where everything on file predates it.
            #
            # Three-valued on purpose. With no license recorded there is nothing to read, and
            # saying "not required" about a driver whose licensing history nobody has entered
            # would be the software vouching for a check it never made.
            "driver.eldt": _eldt_reaches(conn, accountid, driverid),
            # What the work requires, as against driver.endorsements which is what they hold.
            # Two-valued like the ticks above and for the same reason: it is a field on the
            # driver's record, and an empty one is somebody saying this work needs none.
            "driver.endorsementsneeded": (driver.get("endorsementsneeded") or "").upper() or None,
            "driver.needsendorsements": bool((driver.get("endorsementsneeded") or "").strip()),
            # 49 CFR 391.11(b)(1): twenty-one to drive in interstate commerce. Three-valued, and
            # the third value matters - a driver whose date of birth nobody has recorded is not a
            # driver anybody has established the age of, and saying "yes" about them would be the
            # software vouching for something it has never been told.
            "driver.age": driver.get("age"),
            "driver.age21": None if driver.get("age") is None else driver["age"] >= 21,
            # F.S. 316.302(4): eighteen to operate a CMV in Florida, where the intrastate driver is
            # excused the federal twenty-one by 316.302(2)(a).
            "driver.age18": None if driver.get("age") is None else driver["age"] >= 18,
            # Whether the license they drive on is a CDL. Asked of the license, not read off its
            # class letter: Georgia's ordinary license is a Class C. Unknown until somebody says.
            "driver.licensecommercial": _commercial(conn, accountid, driverid),
            # 49 CFR 382.303: whether any accident on this driver's register called for a test.
            # True the moment one does and stays true until the test is on file - the obligation
            # does not lapse because the window to collect has closed, it just gets harder to
            # discharge, and a file that forgot it would be a file that forgot a violation.
            "driver.postaccidentowed": _postaccident_owed(conn, accountid, driverid),
            # 49 CFR 382.305(l): this driver's name came out of the pool and no test has been
            # filed for it, nor any reason recorded why not. Two-valued, unlike the accident
            # one - a selection either names them or it does not, and there is nothing about it
            # that anybody has yet to find out.
            "driver.randomtestowed": _randompool.test_owed(conn, accountid, driverid),
            # 391.11(b)(2). Three-valued on purpose: a driver nobody has assessed is not a driver
            # who passed, and the carrier is the one who has to make the determination.
            "driver.english": (None if driver.get("englishproficient") is None
                               else bool(driver["englishproficient"])),
            # 391.49: whether the licensing State's record says this driver drives under a Skill
            # Performance Evaluation certificate. Read from the driving record rather than asked,
            # because that is where it is stated.
            "driver.spevariance": _spe_variance(conn, accountid, driverid),
            # 40.307: a SAP's follow-up schedule, with fewer tests on file than it prescribed.
            "driver.followupowed": _followup_owed(conn, accountid, driverid),
        })
        # Which transit safety programs this driver works under, and whether each reaches them:
        # assigned and covered (or not yet determined - assigning the driver says they work that
        # operation) is yes; not assigned, or the company determined not covered, is no; assigned
        # while the determination is under review is unknown.
        assigned = {r["programcode"] for r in rows(conn, """
            SELECT programcode FROM drivertransitprograms WHERE accountid = :a AND driverid = :d
        """, a=accountid, d=driverid)}
        for code in transit:
            said = determined.get(code)
            facts[f"driver.transit.{code}"] = (
                False if code not in assigned or said == "notcovered"
                else None if said == "review" else True)
        facts["driver.chapter1490"] = facts.get("driver.transit.FL_1490")
        # What the driver said on their own application about a license being revoked or
        # denied. Three-valued, unlike the tick boxes above: an applicant who has not
        # answered it is not the same as one who answered no, and a rule that turns on the
        # answer must not reach somebody nobody has asked.
        facts["driver.licenseaction"] = _license_action(conn, accountid, driverid)
        # 49 CFR 40.25(j): what the applicant said about pre-employment tests for jobs they applied
        # for and did not get. Three-valued, and the detail behind a "yes" comes with it.
        facts.update(_prior_violation(conn, accountid, driverid))
        # Reach again, now that there is a driver to ask about. The company-level answer was
        # computed above from the roster and the fleet; a rule about THIS driver has to be
        # decided on this driver, and the two differ wherever the carrier is reached by one
        # unit the driver never touches.
        facts.update(_reach(facts, fleet, roster, driver=facts))

    return {"facts": facts, "fleet": fleet}


def _application_step(conn: Connection, accountid: str, driverid: str, step: str) -> dict:
    """One step of the driver's own application, as they filled it in."""
    app_ = row(conn, """
        SELECT data FROM driverapplications
        WHERE driverid = :d AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=accountid)
    if not app_:
        return {}
    try:
        steps = (json.loads(app_["data"] or "{}") or {}).get("steps") or {}
    except ValueError:
        return {}
    got = steps.get(step)
    return got if isinstance(got, dict) else {}


def _prior_violation(conn: Connection, accountid: str, driverid: str) -> dict:
    """The 40.25(j) answer, and whether the way back from it is finished.

    A "yes" is not a bar on employment - it is a bar on performing safety-sensitive functions until
    the Part 40 Subpart O return-to-duty process has been completed and verified. So the answer and
    the state of that process are two facts, not one."""
    said = _application_step(conn, accountid, driverid, "10")
    answer = (said.get("priorviolation") or "").strip().lower()
    rtd = (said.get("priorrtd") or "").strip().lower()
    return {
        "driver.priorviolation": True if answer == "yes" else False if answer == "no" else None,
        "driver.priorrtdcomplete": True if rtd == "yes" else False if rtd in ("no", "inprogress")
        else None,
    }


def _commercial(conn: Connection, accountid: str, driverid: str) -> bool | None:
    held = row(conn, """SELECT commercial FROM driverlicenses
                        WHERE accountid = :a AND driverid = :d AND active = 1 LIMIT 1""",
               a=accountid, d=driverid)
    return None if not held or held["commercial"] is None else bool(held["commercial"])


def _license_action(conn: Connection, accountid: str, driverid: str) -> bool | None:
    """Did this driver say a license had been revoked, or denied, in the last three years?

    Read from the application they filled in rather than copied onto the driver record, so it cannot
    drift away from what they actually signed. None where there is no application, or where the
    question is not answered in it."""
    app_ = row(conn, """
        SELECT data FROM driverapplications
        WHERE driverid = :d AND accountid = :a ORDER BY startedon DESC LIMIT 1
    """, d=driverid, a=accountid)
    if not app_:
        return None
    try:
        steps = (json.loads(app_["data"] or "{}") or {}).get("steps") or {}
    except ValueError:
        return None
    said = ((steps.get("2") or {}).get("licenseaction") or "").strip().lower()
    return True if said == "yes" else False if said == "no" else None


def questions(conn: Connection, accountid: str) -> list[dict]:
    """The questions this company can answer, with whatever it has said."""
    return rows(conn, """
        SELECT q.code, q.factname, q.question, q.help, a.answer, a.updated
        FROM companyquestions q
        LEFT JOIN companyanswers a ON a.code = q.code AND a.accountid = :a
        WHERE q.active = 1 ORDER BY q.sortorder, q.code
    """, a=accountid)


# What a person should be told when a fact is the reason nothing can be decided.
UNANSWERED = {
    "operation.interstate": "Nobody has said whether this company drives across a state line "
                            "(Settings - Company).",
    "fleet.cmv_federal": "Not enough is recorded about the vehicles to say whether any is a "
                         "commercial motor vehicle (seating capacity and GVWR).",
    "fleet.cmv_florida": "Not enough is recorded about the vehicles to say whether any is a "
                         "commercial motor vehicle under Florida law.",
    "fleet.cdl_required": "Not enough is recorded about the vehicles to say whether any needs a CDL.",
    "fleet.wheelchair": "No vehicles are on file, so it is not known whether any carries wheelchairs.",
    "company.cdldrivers": "No drivers are on file, so it is not known whether this company employs "
                          "any who hold a CDL.",
    "company.cmvdrivers": "No drivers are on file, so it is not known whether this company employs "
                          "any who drive a commercial motor vehicle.",

    "driver.employee": "Nobody has said whether this driver is an employee or a contractor "
                       "(Driver Information, or the employment model on Company - Operating Profile)",
    "driver.chapter1490": "The company's Florida Bus Transit System Safety (F.A.C. Chapter 14-90) "
                          "determination is under review (Company - Operating Profile)",
    "vehicle.transit.FL_1490": "Nobody has determined whether this vehicle operates under Florida's "
                               "Bus Transit System Safety rule, F.A.C. Chapter 14-90 (Company - "
                               "Operating Profile, Vehicle Determinations)",
    "company.medicaid": "Nobody has said whether this company carries Medicaid funded trips "
                        "(Settings - Company).",
    "company.transit": "Nobody has said whether this company works under a CTC, a transit contract "
                       "or FDOT funding (Settings - Company).",
    "company.hipaa": "Nobody has said whether this company is HIPAA covered (Settings - Company).",
    "company.cra": "Nobody has said whether background reports come from a consumer reporting "
                   "agency (Settings - Company).",
    "company.hiredautos": "Nobody has said whether drivers ever drive vehicles the company does "
                          "not own (Settings - Company).",
    "company.billsdirect": "Nobody has said whether this company bills a payer directly or "
                           "invoices a broker (Settings - Company).",
    "company.copec": "Nobody has said whether a county this company works in requires a "
                     "certificate of public convenience (Settings - Company).",
    "vehicle.cmv_federal": "Not enough is recorded about this vehicle to say whether it is a "
                           "commercial motor vehicle (seating capacity and GVWR).",
    "vehicle.cdl_required": "Not enough is recorded about this vehicle to say whether it needs a "
                            "CDL (seating capacity and GVWR).",
    "driver.eldt": "No license is recorded for this driver, so there is no licensing history to "
                   "say whether entry-level driver training applies (Driver Information).",
    "company.misrequested": "Nobody has said whether FMCSA has asked this company for a drug "
                            "and alcohol MIS report (Settings - Company).",
    # Points at a requirement on this same page rather than at a question on another screen,
    # which is the one case the old wording could not express - and it sent people to Company
    # Operations hunting for a question that is no longer asked there.
    "company.exposure": "Nobody has signed a bloodborne pathogens exposure determination, so "
                        "whether these duties involve exposure is undecided. Make it on the "
                        "exposure determination above.",
    "company.level2": "Nobody has said whether a contract requires Level 2 screening "
                      "(Settings - Company).",
    "company.samgov": "Nobody has said whether a contract, grant or program requires SAM.gov "
                      "screening (Settings - Company).",
    "driver.age21": "The driver's date of birth is not on file, so their age cannot be "
                    "established (Driver Information).",
    "company.medicaidstates": "Nobody has set up a payer line, so which state's Medicaid program "
                              "this company carries for is not known (Payers).",
    "fleet.multiplecmv": "Not enough is recorded about the vehicles to say whether the company runs "
                         "more than one commercial motor vehicle (Vehicles).",
    "driver.licensecommercial": "Nobody has said whether the license this driver drives on is a "
                                "commercial license (Licenses).",
    "driver.age18": "The driver's date of birth is not on file, so their age cannot be "
                    "established (Driver Information).",
    "driver.postaccidentowed": "An accident on file has not been answered either way "
                               "(Requirements - accident register).",
    "driver.english": "Nobody has recorded whether this driver can read and speak English "
                      "(Driver Information).",
    "driver.spevariance": "No driving record carrying medical certification information is on "
                          "file, so it is not known whether this driver holds an SPE certificate.",
    "driver.priorviolation": "The driver has not answered the pre-employment drug and alcohol "
                             "questionnaire on their application (49 CFR 40.25(j)).",
    "driver.priorrtdcomplete": "The driver has not said whether they completed the return-to-duty "
                               "process for the violation they disclosed.",

    "company.transitmedicalalt": "Nobody has said whether this company has adopted medical "
                                 "standards meeting or exceeding the FDOT bus transit standards "
                                 "(Settings - Company).",
}
