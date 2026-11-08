###################################################################################################
# The requirements importer.
#
# A requirements file (docs/requirements-format/) becomes rules the engine evaluates. Five steps:
#
#   1. Shape      - the file is checked against the published JSON Schema.
#   2. Citations  - every quote is fetched from its official source and must appear there.
#   3. Translate  - each requirement is put in the engine's terms: category, condition, evidence,
#                   renewal, due stage, what failing it does. Where the file names something TripProof
#                   already tracks under another name, it is linked rather than left waiting.
#   4. Compare    - each one is matched against the rules already in force: what it replaces, and
#                   which current rules nothing in the file covers.
#   5. Load       - not done by a dry run. Rules are loaded as drafts; only an approved rule ever
#                   refuses a trip.
#
#   python -m app.cli import-requirements FILE [FILE ...] --dry-run --report out.json
#
# A dry run writes nothing to the database. It returns a report: ready, waiting (on a fact or an
# evidence type TripProof does not have yet, with why), refused, what each replaces, and orphans.
###################################################################################################
import html
import json
import re
import subprocess
from pathlib import Path

from sqlalchemy.engine import Connection

from app.db import rows

SCHEMA = Path(__file__).parent / "assets" / "requirements.schema.json"
APP = Path(__file__).parent

# Category in the file -> category in the engine. Federal motor carrier rules are the paid add-on.
CATEGORY = {"MEDICAID": "MEDICAID", "FEDERAL": "FEDERAL_NEMT", "STATE": "STATE_NEMT",
            "COMPANY": "COMPANY", "BROKER": "BROKER_PAYER", "CDL_CMV": "FMCSA_DOT"}
FMCSA_PARTS = re.compile(r"^49 CFR (382|383|387|390|391|392|393|395|396)\b")

# Renewal in the file -> the engine's recurrence.
RENEWAL = {"once": "once", "perhire": "perhire", "ondocument": "ondocument",
           "days": "days", "months": "months"}

# Evidence TripProof reads under a name of its own. A credential the file asks for that the engine
# already holds as something else is linked to that; it is the same proof.
CREDENTIAL_IS = {
    "FMCSA_DRIVER_APPLICATION": "signature:APPLICATION",
    "FMCSA_SAFETY_PERFORMANCE_HISTORY": "employerhistory",
    "FMCSA_ANNUAL_MVR_REVIEW": "annualreview",
    "FMCSA_ROAD_TEST_OR_EQUIVALENT": "roadtest",
    "FMCSA_MCS150_REGISTRATION": "mcs150",
    "DOT_SUPERVISOR_SUSPICION_TRAINING": "supervisortraining",
}
EXCLUSION_LIST = {"OIG_LEIE": "exclusioncheck:OIG_LEIE", "SAM": "exclusioncheck:SAM_EXCLUSIONS"}
DRUG_TEST = {"preemployment", "random", "postaccident", "followup"}

# A `needs` entry that names something TripProof already knows. Each resolves to a fact or an
# evidence source the engine has today; anything not here stays waiting.
NEED_IS = {
    # Operations questions (migration 409).
    "company.public_transit_authority": ("fact", {"fact": "company.public_transit_authority", "is": False}),
    "operation.ada_part37_covered": ("fact", {"fact": "operation.ada_part37_covered", "is": True}),
    "company.hipaa_covered_entity": ("fact", {"fact": "company.hipaa", "is": True}),
    "company.cra_employment_purpose": ("fact", {"fact": "company.cra", "is": True}),
    "driver.actual_bbp_occupational_exposure": ("fact", {"fact": "company.exposure", "is": True}),
    "company.medicaid_enrollment_required": ("fact", {"all": [{"fact": "company.medicaid", "is": True},
                                                              {"fact": "company.billsdirect", "is": True}]}),
    "company.medicaid_provider_agreement": ("fact", {"all": [{"fact": "company.medicaid", "is": True},
                                                             {"fact": "company.billsdirect", "is": True}]}),
    "reach.passenger_hos": ("fact", {"fact": "reach.fmcsr", "is": True}),
    "vehicle_open_unsafe_defects": ("evidence", "dvir"),
    "vehicle_current_safety_and_defect_status": ("evidence", "dvir"),
    "fmcsa_vehicle_maintenance_records": ("evidence", "maintenance"),
    "fmCSA_mcs150_status_and_biennial_update": ("evidence", "mcs150"),
    "company_supervisors_dot_training_completion": ("evidence", "supervisortraining"),
    "clearinghouse_annual_limited_full_resolution": ("evidence", "clearinghouse"),
    "clearinghouse_query_scope_result_and_consent": ("evidence", "report:CLEARINGHOUSE_PREEMP"),
    "i9_completed_verification": ("evidence", "signature:I9"),
    "fcra_standalone_disclosure": ("evidence", "signature:FCRA_AUTH"),
    "fmcsamedical_actual_expiration": ("evidence", "credential:DOT_MEDICAL_CARD"),
    "current_federal_program_exclusion_status": ("evidence", "exclusioncheck:OIG_LEIE"),
}


# --------------------------------------------------------------------------------------------------
# 1. Shape
# --------------------------------------------------------------------------------------------------
def check_shape(doc: dict) -> list[str]:
    import jsonschema
    schema = json.loads(SCHEMA.read_text())
    v = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    return [f'{"/".join(str(p) for p in e.absolute_path) or "(file)"}: {e.message}' for e in v.iter_errors(doc)]


# --------------------------------------------------------------------------------------------------
# 2. Citations
# --------------------------------------------------------------------------------------------------
def _fetch(url: str) -> str:
    return subprocess.run(["curl", "-sL", "--compressed", "-A", "Mozilla/5.0", "--max-time", "60", url],
                          capture_output=True, text=True).stdout


def _official_url(url: str) -> str:
    """The machine-readable source for a citation link: eCFR's own API for a CFR section, the link
    itself for anything else."""
    m = re.search(r"ecfr\.gov/.*title-(\d+)/.*section-([0-9A-Za-z.]+)", url)
    if m:
        title, sec = m.group(1), m.group(2)
        return (f"https://www.ecfr.gov/api/versioner/v1/full/current/title-{title}.xml"
                f"?part={sec.split('.')[0]}&section={sec}").replace("/current/", f"/{_ecfr_date()}/")
    return url


_ECFR_DATE = None


def _ecfr_date() -> str:
    """The latest date eCFR has published title 1 through - the API takes a date, not "current"."""
    global _ECFR_DATE
    if _ECFR_DATE is None:
        try:
            got = json.loads(_fetch("https://www.ecfr.gov/api/versioner/v1/titles.json"))
            _ECFR_DATE = max(t.get("up_to_date_as_of") or "" for t in got.get("titles", []))
        except (ValueError, TypeError):
            _ECFR_DATE = ""
        _ECFR_DATE = _ECFR_DATE or "2026-10-01"
    return _ECFR_DATE


def _norm(t: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    for a, b in (("—", "-"), ("–", "-"), ("’", "'"), ("‘", "'"),
                 ("“", '"'), ("”", '"'), ("§", "")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip().lower()


def check_citations(reqs: list[dict]) -> dict[str, str]:
    """id -> "verified", or why not. A quote must appear word for word in the official text."""
    cache: dict[str, str] = {}
    out = {}
    for r in reqs:
        # The link must be the section the citation names: a quote that happens to appear in a
        # neighbouring section (387.33 for 387.33T) proves nothing about the one cited.
        cited = re.match(r"\s*\d+\s+CFR\s+([0-9A-Za-z.]+?)(?=\(|\s|$)", r["citation"])
        linked = re.search(r"section-([0-9A-Za-z.]+)", r["citation_url"])
        if cited and linked and cited.group(1).rstrip(".") != linked.group(1):
            out[r["id"]] = (f"the citation names section {cited.group(1).rstrip('.')} but the link "
                            f"points at section {linked.group(1)}")
            continue
        src = _official_url(r["citation_url"])
        if src not in cache:
            cache[src] = _norm(_fetch(src))
        page, quote = cache[src], _norm(r["citation_text"])
        if not page:
            out[r["id"]] = "the official text could not be fetched"
        elif quote in page or re.sub(r"[^a-z0-9]", "", quote) in re.sub(r"[^a-z0-9]", "", page):
            out[r["id"]] = "verified"
        else:
            out[r["id"]] = "the quoted text does not appear in the official text"
    return out


# --------------------------------------------------------------------------------------------------
# 3. Translate
# --------------------------------------------------------------------------------------------------
def _evidence(ev: dict, known: dict) -> tuple[str | None, str | None]:
    """(engine evidence source, or None) and why it is waiting, if it is."""
    t = ev["type"]
    if t == "license":
        return "license", None
    if t == "license_copy":
        return "licensecopy", None
    if t == "credential":
        code = ev["credential"]
        if code in CREDENTIAL_IS:
            return CREDENTIAL_IS[code], None
        if code in known["credentials"]:
            return f"credential:{code}", None
        # A document type is data: loading creates it, and the engine reads it like any other.
        return f"credential:{code}", None
    if t == "signature":
        return f"signature:{ev['document']}", None
    if t == "exclusion_check":
        return EXCLUSION_LIST[ev["list"]], None
    if t == "driving_record":
        return "mvr", None
    if t == "drug_test":
        if ev["reason"] in DRUG_TEST:
            return f"drugtest:{ev['reason']}", None
        return None, f"no evidence type yet for a {ev['reason']} drug test"
    if t == "company_role":
        if ev["role"] == "supervisor":
            return "supervisortraining", None
        return f"companyrole:{ev['role']}", None
    if t == "policy":
        if ev["policy"] in known["policies"]:
            return f"policy:{ev['policy']}", None
        return None, f"no policy template yet for {ev['policy']}"
    if t == "fact":
        fact = ev["fact"]
        if fact == "driver.age" and ev.get("gte") in (18, 21):
            return f"driverfact:driver.age{ev['gte']}", None
        if fact == "driver.prohibited" and ev.get("is") is False:
            return "prohibition", None
        if ev.get("is") is True:
            return f"driverfact:{fact}", None
        return None, f"no way yet to read {fact} as evidence"
    return None, f"new evidence type: {ev.get('describe') or t}"


def translate(r: dict, known: dict) -> dict:
    category = "FMCSA_DOT" if FMCSA_PARTS.match(r["citation"]) else CATEGORY[r["category"]]
    condition = r["applies_when"]
    waiting, linked = [], []
    source, why = _evidence(r["evidence"], known)
    if why:
        waiting.append(why)
    for n in r.get("needs") or []:
        hit = NEED_IS.get(n["name"])
        if not hit:
            waiting.append(f'{n["kind"]} {n["name"]}: {n["why"]}')
            continue
        kind, what = hit
        linked.append(f'{n["name"]} -> {json.dumps(what) if kind == "fact" else what}')
        if kind == "fact":
            condition = what if condition is None else {"all": [condition, what]}
        elif source is None or source != what:
            source = what
            waiting = [w for w in waiting if not w.startswith("new evidence type")
                       and not w.startswith("no way yet")]
    programs = r["programs"]
    if programs and len(programs) > 1:
        waiting.append("more than one program; the engine holds one program per rule")
    v = r["validity"]
    rule = {
        "code": r["id"], "qualificationcode": r["qualification"], "name": r["name"],
        "description": r["requirement_text"], "subject": r["subject"],
        "authoritycategory": category, "authority": r["authority"], "jurisdiction": r["jurisdiction"],
        "citation": r["citation"], "sourceurl": r["citation_url"],
        "applieswhen": condition, "program": programs[0] if programs else None,
        "evidencesource": source,
        "recurrence": RENEWAL[v["renewal"]],
        "recurrencedays": v.get("every") if v["renewal"] == "days" else None,
        "recurrencemonths": v.get("every") if v["renewal"] == "months" else None,
        "warndays": v.get("warn_days", 30),
        "duestage": r["due"], "duedays": r.get("due_within_days"),
        "gate": "hardstop" if r["on_failure"] == "block" else "deficiency",
        "blocking": 1 if r["on_failure"] == "block" else 0,
        "enforcement": "hr" if r["on_failure"] == "track" and r["subject"] == "driver" else "dispatch",
        "effectivefrom": r["effective_from"], "effectiveto": r.get("effective_to"),
        "legalreview": "draft", "note": (r.get("notes") or "")[:512] or None,
    }
    return {"rule": rule, "waiting": waiting, "linked": linked}


# --------------------------------------------------------------------------------------------------
# 4. Compare
# --------------------------------------------------------------------------------------------------
def _section(citation: str | None) -> str:
    """'49 CFR 391.11(b)(1)' -> '49 CFR 391.11'; '42 U.S.C. 1396a(a)(87)(B)' -> '42 U.S.C. 1396a'."""
    m = re.match(r"\s*(\d+\s+(?:CFR|U\.S\.C\.)\s+[0-9A-Za-z.]+?)(?=\(|;|\s|$)", citation or "")
    return m.group(1).rstrip(".") if m else (citation or "").strip()


def _paragraph(citation: str | None) -> str:
    """The first cited paragraph, spacing aside: '49 CFR 391.11(b)(5); ...' -> '49cfr391.11(b)(5)'."""
    return re.sub(r"\s+", "", (citation or "").split(";")[0]).lower()


def _coded_in_app(codes: set[str]) -> set[str]:
    """Rule codes the application refers to by name - each one is special handling in code that a
    replacement must keep or retire on purpose."""
    text = "\n".join(p.read_text(errors="ignore") for p in APP.rglob("*.py"))
    return {c for c in codes if f'"{c}"' in text or f"'{c}'" in text}


def compare(conn: Connection, translated: list[dict]) -> dict:
    # Only rules of the same jurisdictions as the file: a federal file says nothing about Georgia's
    # Medicaid manual, and must not be read as replacing it or leaving it orphaned.
    places = sorted({t["rule"]["jurisdiction"] for t in translated}) or ["US"]
    marks = ", ".join(f":j{i}" for i in range(len(places)))
    current = rows(conn, f"""
        SELECT recordid, code, name, subject, authoritycategory, evidencesource, citation,
               legalreview, recurrence, duestage, qualificationcode
        FROM compliancerules
        WHERE accountid IS NULL AND effectiveto IS NULL AND jurisdiction IN ({marks})
          AND authoritycategory IN ('MEDICAID', 'FEDERAL_NEMT', 'FMCSA_DOT')
    """, **{f"j{i}": p for i, p in enumerate(places)})
    special = _coded_in_app({c["code"] for c in current})

    # Every plausible pairing, scored; then the best pairs taken first, each side used once. One
    # requirement replaces at most one rule and one rule is replaced at most once - two new
    # requirements both claiming the pre-employment driving record is a load that would end it twice.
    def score(r: dict, c: dict) -> int:
        if c["subject"] != r["subject"]:
            return 0
        same_proof = bool(r["evidencesource"]) and c["evidencesource"] == r["evidencesource"]
        same_text = bool(c["citation"]) and _paragraph(c["citation"]) == _paragraph(r["citation"])
        if not (same_proof or same_text):
            return 0
        return (4 * same_proof + 3 * same_text + (c["recurrence"] == r["recurrence"])
                + (c["duestage"] == r["duestage"]))
    pairs = sorted(((score(t["rule"], c), i, j) for i, t in enumerate(translated)
                    for j, c in enumerate(current)), reverse=True)
    taken_new, taken_old = set(), set()
    for t in translated:
        t["replaces"] = []
    for sc, i, j in pairs:
        if sc == 0 or i in taken_new or j in taken_old:
            continue
        c = current[j]
        translated[i]["replaces"] = [{"recordid": c["recordid"], "code": c["code"], "name": c["name"],
                                      "qualificationcode": c["qualificationcode"],
                                      "legalreview": c["legalreview"], "special": c["code"] in special}]
        taken_new.add(i)
        taken_old.add(j)
    orphans = [{k: v for k, v in {**c, "special": c["code"] in special}.items() if k != "recordid"}
               for j, c in enumerate(current) if j not in taken_old]
    return {"orphans": orphans}


# --------------------------------------------------------------------------------------------------
# 5. Load
# --------------------------------------------------------------------------------------------------
# Not yet in force. Every query that reads the rules in force asks `effectiveto IS NULL` or
# `effectiveto >= :day`, and neither is true of this date, so a staged rule is invisible to them.
STAGED_UNTIL = "1000-01-01"
# The engine's evidencekind, by the file's evidence type.
EVIDENCE_KIND = {"license": "document", "license_copy": "document", "credential": "document",
                 "signature": "attestation", "exclusion_check": "query", "driving_record": "record",
                 "drug_test": "test", "company_role": "person", "policy": "policy", "fact": "fact",
                 "other": "record"}
QUALIFICATION_AREA = {"DRV": "licensing", "BKG": "background", "TRN": "training", "MED": "medical",
                      "DAT": "drugalcohol", "EMP": "employment"}


def load(conn: Connection, report: dict, sources: dict[str, dict], by: str | None = None) -> dict:
    """Stage every ready requirement. Nothing reaches any account until it is approved."""
    from app.db import newid, run, row as one
    staged, skipped = [], []
    allotted: dict[str, str] = {}

    def qualification(t: dict, req: dict) -> str:
        """The catalog qualification this rule proves. A file's code is the file's own label: it is
        used only where TripProof does not already use it for something else. A rule replacing one
        in force proves what that one proved."""
        replaced = t["replaces"][0] if t["replaces"] else None
        if replaced and replaced.get("qualificationcode"):
            return replaced["qualificationcode"]
        # The same proof for the same subject is the same qualification, whatever rule asks for it:
        # a federal "valid license" and the State's are one row on the driver's file, two reasons.
        if t["rule"]["evidencesource"]:
            same = one(conn, """SELECT qualificationcode FROM compliancerules
                                WHERE accountid IS NULL AND effectiveto IS NULL AND subject = :s
                                  AND evidencesource = :e AND qualificationcode IS NOT NULL
                                ORDER BY sortorder LIMIT 1""",
                       s=t["rule"]["subject"], e=t["rule"]["evidencesource"])
            if same:
                return same["qualificationcode"]
        code = t["rule"]["qualificationcode"]
        if code in allotted:
            return allotted[code]
        held = one(conn, "SELECT name FROM qualificationcatalog WHERE code = :c", c=code)
        if held is None or held["name"].strip().lower() == req["name"].strip().lower():
            allotted[code] = code
            return code
        prefix = code.split("-")[0]
        top = one(conn, "SELECT MAX(CAST(SUBSTRING_INDEX(code, '-', -1) AS UNSIGNED)) AS n "
                        "FROM qualificationcatalog WHERE code LIKE :p", p=f"{prefix}-%")
        fresh = f"{prefix}-{max(900, (top or {}).get('n') or 0) + 1:03d}"
        allotted[code] = fresh
        return fresh

    for t in report["ready"]:
        r, req = t["rule"], sources[t["id"]]
        if one(conn, "SELECT 1 AS x FROM compliancerules WHERE sourceref = :s AND accountid IS NULL "
                     "AND (staged = 1 OR effectiveto IS NULL)", s=t["id"]):
            skipped.append(t["id"])
            continue
        r = {**r, "qualificationcode": qualification(t, req)}
        if not one(conn, "SELECT 1 AS x FROM qualificationcatalog WHERE code = :c", c=r["qualificationcode"]):
            run(conn, """INSERT INTO qualificationcatalog (code, name, area, subject, sortorder)
                         VALUES (:c, :n, :a, :s, 900)""",
                c=r["qualificationcode"], n=req["name"][:128],
                a=QUALIFICATION_AREA.get(r["qualificationcode"][:3], "licensing"), s=r["subject"])
        source = r["evidencesource"] or ""
        if source.startswith("credential:"):
            code = source.split(":", 1)[1]
            if not one(conn, "SELECT 1 AS x FROM credentialtypes WHERE code = :c AND accountid IS NULL", c=code):
                ev = req["evidence"]
                run(conn, """INSERT INTO credentialtypes (recordid, accountid, code, name, subject, active)
                             VALUES (:i, NULL, :c, :n, :s, 1)""",
                    i=newid(), c=code, n=(ev.get("credential_name") or req["name"])[:128], s=r["subject"])
        replaces = t["replaces"][0] if t["replaces"] else None
        run(conn, """
            INSERT INTO compliancerules
              (recordid, accountid, code, qualificationcode, name, description, subject, evidencekind,
               authoritytype, authoritycategory, authority, jurisdiction, citation, sourceurl,
               applieswhen, program, evidencesource, recurrence, recurrencedays, recurrencemonths,
               warndays, duestage, duedays, gate, blocking, enforcement, legalreview,
               effectivefrom, effectiveto, supersedes, note, staged, sourceref, sortorder, added, addedby)
            VALUES
              (:id, NULL, :code, :q, :name, :description, :subject, :evidencekind,
               :authoritytype, :category, :authority, :jurisdiction, :citation, :sourceurl,
               :applieswhen, :program, :evidencesource, :recurrence, :recurrencedays, :recurrencemonths,
               :warndays, :duestage, :duedays, :gate, :blocking, :enforcement, 'draft',
               :effectivefrom, :staged_until, :supersedes, :note, 1, :ref, 900, UTC_TIMESTAMP(), :by)
        """, id=newid(), code=t["id"], q=r["qualificationcode"], name=r["name"][:160],
            evidencekind=EVIDENCE_KIND.get(req["evidence"]["type"], "record"),
            authoritytype=("contract" if r["authoritycategory"] == "BROKER_PAYER"
                           else "policy" if r["authoritycategory"] == "COMPANY"
                           else "statute" if "U.S.C." in r["citation"] else "regulation"),
            description=(r["description"] or "")[:1200], subject=r["subject"],
            category=r["authoritycategory"], authority=r["authority"][:96], jurisdiction=r["jurisdiction"],
            citation=r["citation"][:160], sourceurl=r["sourceurl"][:512],
            applieswhen=json.dumps(r["applieswhen"]) if r["applieswhen"] else None,
            program=r["program"], evidencesource=r["evidencesource"], recurrence=r["recurrence"],
            recurrencedays=r["recurrencedays"], recurrencemonths=r["recurrencemonths"],
            warndays=r["warndays"], duestage=r["duestage"], duedays=r["duedays"], gate=r["gate"],
            blocking=r["blocking"], enforcement=r["enforcement"], effectivefrom=r["effectivefrom"],
            staged_until=STAGED_UNTIL, supersedes=replaces["recordid"] if replaces else None,
            note=r["note"], ref=t["id"], by=by)
        staged.append({"id": t["id"], "replaces": replaces["code"] if replaces else None})
    return {"staged": staged, "already_staged": skipped}


def go_live(conn: Connection, recordid: str) -> dict:
    """Bring a staged rule into force, ending the rule it replaces in the same act. It takes over
    that rule's code, so everything that refers to the rule by name - and its version history -
    carries on unbroken."""
    from datetime import date
    from app.db import run, row as one
    r = one(conn, "SELECT recordid, code, supersedes FROM compliancerules WHERE recordid = :i AND staged = 1",
            i=recordid)
    if not r:
        return {"ok": False}
    code = r["code"]
    if r["supersedes"]:
        old = one(conn, "SELECT recordid, code FROM compliancerules WHERE recordid = :i AND effectiveto IS NULL",
                  i=r["supersedes"])
        if old:
            run(conn, "UPDATE compliancerules SET effectiveto = :d WHERE recordid = :i",
                d=date.today(), i=old["recordid"])
            code = old["code"]
    run(conn, "UPDATE compliancerules SET staged = 0, effectiveto = NULL, code = :c WHERE recordid = :i",
        c=code, i=recordid)
    return {"ok": True, "code": code}


# --------------------------------------------------------------------------------------------------
# The run
# --------------------------------------------------------------------------------------------------
def run_import(conn: Connection, paths: list[str], verify: bool = True) -> dict:
    docs, reqs, refused = [], [], []
    for p in paths:
        doc = json.loads(Path(p).read_text())
        errs = check_shape(doc)
        docs.append({"file": Path(p).name, "title": doc.get("title"), "requirements": len(doc.get("requirements", [])),
                     "shape_errors": errs})
        reqs += doc.get("requirements", []) if not errs else []
    ids = [r["id"] for r in reqs]
    dupes = {i for i in ids if ids.count(i) > 1}
    for i in dupes:
        refused.append({"id": i, "why": "the same id appears more than once"})
    cited = check_citations(reqs) if verify else {r["id"]: "not checked" for r in reqs}
    known = {
        "credentials": {r["code"] for r in rows(conn, "SELECT code FROM credentialtypes WHERE active = 1")},
        "policies": {(r["evidencesource"] or "").split(":", 1)[1] for r in rows(conn, """
            SELECT DISTINCT evidencesource FROM compliancerules WHERE evidencesource LIKE 'policy:%'""")},
    }
    translated = []
    for r in reqs:
        if r["id"] in dupes:
            continue
        if cited[r["id"]] not in ("verified", "not checked"):
            refused.append({"id": r["id"], "citation": r["citation"], "why": cited[r["id"]]})
            continue
        t = translate(r, known)
        t["id"], t["citation_check"] = r["id"], cited[r["id"]]
        translated.append(t)
    compared = compare(conn, translated)
    ready = [t for t in translated if not t["waiting"]]
    waiting = [t for t in translated if t["waiting"]]
    new_credentials = sorted({t["rule"]["evidencesource"].split(":", 1)[1] for t in translated
                              if (t["rule"]["evidencesource"] or "").startswith("credential:")
                              and t["rule"]["evidencesource"].split(":", 1)[1] not in known["credentials"]})
    return {
        "sources": {r["id"]: r for r in reqs},
        "files": docs,
        "totals": {"requirements": len(reqs), "ready": len(ready), "waiting": len(waiting),
                   "refused": len(refused), "orphans": len(compared["orphans"])},
        "ready": ready, "waiting": waiting, "refused": refused,
        "orphans": compared["orphans"], "new_credential_types": new_credentials,
    }
