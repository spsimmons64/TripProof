"""Acceptance tests for the rule engine, asked for by the legal reviews of 22 October 2026.

Not what the rules say - what TripProof DOES with them: which rule reaches which company, driver,
vehicle and trip; whether the evidence actually satisfies it; and what a decision does to dispatch.

Every test builds a company of its own from nothing, so none depends on another or on the order they
run in, and each goes through the paths the application itself uses - the requirements endpoint,
the trip check, the dispatch list - rather than handing a helper a dictionary.
"""
import json
import uuid
from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import bindparam, text

PASSWORD = "correct horse battery"


def login(client, email):
    r = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture
def make(client, db):
    """A new Florida company: an owner, one hired Florida driver, one vehicle, and a broker with a
    Florida Medicaid line. More lines, vehicles and drivers are added by the test that wants them."""
    def build():
        from app.cli import create_account
        tag = uuid.uuid4().hex[:8]
        email = f"owner-{tag}@acceptance.test"
        create_account(f"Acceptance {tag}", email, "Owner", "FL", "America/New_York", PASSWORD)
        h = login(client, email)
        acct = client.get("/api/auth/me", headers=h).json()["accountid"]
        co = {"h": h, "acct": acct, "db": db, "tag": tag, "client": client}
        co["driver"] = new_driver(co, "Ada")
        co["vehicle"] = new_vehicle(co, "AV1")
        co["payer"] = new_payer(co, "ACC BROKER")
        add_line(co, co["payer"], "FL")
        return co
    return build


def new_driver(co, first, **set_):
    d = co["client"].post("/api/drivers", json={"firstname": first, "lastname": "Test"},
                          headers=co["h"]).json()["recordid"]
    fields = {"status": "hired", "state": "FL", **set_}
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET " + ", ".join(f"{k} = :{k}" for k in fields)
                          + " WHERE recordid = :d"), {**fields, "d": d})
    return d


def new_vehicle(co, unit, **body):
    r = co["client"].post("/api/vehicles", headers=co["h"], json={"externalid": unit, **body})
    assert r.status_code == 200, r.text
    return r.json()["recordid"]


def new_payer(co, name):
    return co["client"].post("/api/company/payers", json={"name": name, "category": "broker"},
                             headers=co["h"]).json()["recordid"]


def add_line(co, payer, state):
    r = co["client"].post("/api/company/operating-profile/contracts", headers=co["h"],
                          json={"payerid": payer, "state": state})
    assert r.status_code == 200, r.text


def line(co, payer, state):
    with co["db"].connect() as conn:
        return dict(conn.execute(text("""SELECT recordid, state, program, broker, requiresapproval
                                         FROM companycontracts WHERE accountid = :a AND payerid = :p
                                           AND state = :s"""),
                                 {"a": co["acct"], "p": payer, "s": state}).mappings().one())


def approve(co, vehicle, contract, starts):
    r = co["client"].post(f"/api/vehicles/{vehicle}/authorizations/{contract['recordid']}",
                          headers=co["h"], json={"servicefrom": str(starts)})
    assert r.status_code == 200, r.text


def vehicle_rule(co, code, vehicle=None):
    from app import facts as factset, rules
    vehicle = vehicle or co["vehicle"]
    with co["db"].connect() as conn:
        f = factset.assemble(conn, co["acct"], vehicleid=vehicle)["facts"]
        return next(r for r in rules.for_vehicle(conn, co["acct"], vehicle, f) if r["code"] == code)


def requirement(co, code, driver=None):
    """The rule as the driver's own requirements screen reports it - the endpoint, not a helper."""
    driver = driver or co["driver"]
    items = co["client"].get(f"/api/drivers/{driver}/requirements", headers=co["h"]).json()["items"]
    for i in items:
        for s in (i.get("sources") or [i]):
            if s["code"] == code:
                return s
    return None


def credential(co, code, subject, subjectid, on, result=None, **extra):
    rid = f"c-{uuid.uuid4().hex[:12]}"
    with co["db"].begin() as conn:
        tid = conn.execute(text("SELECT recordid FROM credentialtypes WHERE code = :c"), {"c": code}).scalar()
        cols = {"recordid": rid, "accountid": co["acct"], "credentialtypeid": tid, "subject": subject,
                "subjectid": subjectid, "issuedon": on, "result": result, **extra}
        conn.execute(text(f"INSERT INTO credentials ({', '.join(cols)}, added) "
                          f"VALUES ({', '.join(':' + k for k in cols)}, NOW())"), cols)
    return rid


def approved(conn, *codes):
    """Approve rules inside the caller's own transaction - always rolled back after."""
    conn.execute(text("UPDATE compliancerules SET legalreview = 'approved' WHERE accountid IS NULL "
                      "AND effectiveto IS NULL AND code IN :c").bindparams(bindparam("c", expanding=True)),
                 {"c": list(codes)})


def defect(co, vehicle, note="BRAKES SOFT"):
    rid = f"d-{uuid.uuid4().hex[:12]}"
    with co["db"].begin() as conn:
        conn.execute(text("""INSERT INTO vehicledvirs (recordid, accountid, vehicleid, reportedon, kind,
                                                       defects, defectnote)
                             VALUES (:r, :a, :v, CURDATE(), 'posttrip', 1, :n)"""),
                     {"r": rid, "a": co["acct"], "v": vehicle, "n": note})
    return rid


# 1. A state's vehicle rule reaches only the vehicles its broker approved ----------------------------

def test_1_a_florida_only_medicaid_company_owes_no_georgia_rule(make):
    co = make()
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["applies"] is False
    got = requirement(co, "GA_NET_MVR")
    assert got is None or got["applies"] is False, got


def test_1b_a_georgia_line_reaches_only_vehicles_its_broker_approved(make):
    co = make()
    add_line(co, co["payer"], "GA")
    # Nobody has said which broker this vehicle serves: unknown, never "does not apply".
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["applies"] is None
    approve(co, co["vehicle"], line(co, co["payer"], "FL"), date.today())
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["applies"] is False


# 2. The Georgia inspection: satisfactory, in the initial window, then every six months ---------------

def georgian(make, starts):
    co = make()
    add_line(co, co["payer"], "GA")
    approve(co, co["vehicle"], line(co, co["payer"], "GA"), starts)
    return co


def test_2_the_initial_inspection_falls_within_sixty_days_before_service(make):
    starts = date.today() - timedelta(days=10)
    co = georgian(make, starts)

    def insp(on, result):
        credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], on, result)
    insp(starts + timedelta(days=5), "passed")        # only after it went into service
    got = vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")
    assert got["status"] == "failed" and "within the 60 days" in got["why"], got
    insp(starts - timedelta(days=75), "passed")       # more than sixty days before
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["status"] == "failed"
    insp(starts - timedelta(days=30), "failed")       # in the window, but failed
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["status"] == "failed"
    insp(starts - timedelta(days=20), "passed")       # in the window and passed
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["status"] == "satisfied"


def test_2b_an_uploaded_inspection_counts_only_once_recorded_passed(make):
    starts = date.today() - timedelta(days=10)
    co = georgian(make, starts)
    credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], starts - timedelta(days=20), "passed")
    latest = credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], date.today())
    got = vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")
    assert got["status"] == "review" and "passed" in got["why"], got

    def put(result, reason=None):
        return co["client"].put(f"/api/credentials/{latest}/result", headers=co["h"],
                                json={"result": result, "reason": reason})
    assert put("failed").status_code == 200
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["status"] == "failed"
    # Changing a recorded result needs the reason.
    assert put("passed").status_code == 400
    assert put("passed", "BROKER RE-INSPECTED AND PASSED").status_code == 200
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["status"] == "satisfied"


def test_2c_the_next_inspection_is_due_six_calendar_months_after_the_last(make):
    co = georgian(make, date(2026, 10, 20))
    credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], date(2026, 10, 10), "passed")
    assert vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")["expireson"] == date(2027, 4, 10)


def test_2d_a_vehicle_entering_service_later_is_told_when_its_first_inspection_falls(make):
    starts = date.today() + timedelta(days=30)
    co = georgian(make, starts)
    got = vehicle_rule(co, "GA_NET_VEHICLE_INSPECTION")
    assert got["status"] == "pending", got
    assert f"{starts - timedelta(days=60):%m/%d/%Y}" in got["why"] and f"{starts:%m/%d/%Y}" in got["why"]


def test_2e_the_inspection_restricts_only_trips_under_the_exact_georgia_line(make):
    """Approved for the Florida and Georgia lines, its latest Georgia inspection failed, the rule
    approved: it stops the Georgia line's trips - and not Florida Medicaid, private pay, or another
    Georgia broker's line the vehicle is not approved for."""
    from app import tripcheck
    starts = date.today() - timedelta(days=10)
    co = georgian(make, starts)
    approve(co, co["vehicle"], line(co, co["payer"], "FL"), starts)
    credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], starts - timedelta(days=20), "passed")
    credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], date.today(), "failed")
    other = new_payer(co, "OTHER GA BROKER")
    add_line(co, other, "GA")
    at = datetime.combine(date.today() + timedelta(days=1), datetime.min.time())
    conn = co["db"].connect()
    trans = conn.begin()
    try:
        approved(conn, "GA_NET_VEHICLE_INSPECTION")

        def ga(contract, program):
            return [b for b in tripcheck.vehicle_blockers(conn, co["acct"], co["vehicle"], "ambulatory",
                                                          at, None, program, contract)
                    if b["code"] == "GA_NET_VEHICLE_INSPECTION"]
        georgia = ga(line(co, co["payer"], "GA"), "medicaid")
        florida = ga(line(co, co["payer"], "FL"), "medicaid")
        private = ga(None, "privatepay")
        otherline = ga(line(co, other, "GA"), "medicaid")
    finally:
        trans.rollback()
        conn.close()
    assert georgia and georgia[0]["enforceable"], georgia
    assert not florida and not private and not otherline, (florida, private, otherline)


# 3. Results, not readings, answer a screening -----------------------------------------------------

def test_3_a_screening_read_and_found_not_eligible_fails(make):
    co = make()
    l1 = credential(co, "FL_LEVEL1", "driver", co["driver"], date.today(), provenance="fdle")
    with co["db"].begin() as conn:
        conn.execute(text("""INSERT INTO documentreads (recordid, accountid, subject, subjectid,
                                                        sourcetable, sourceid, note)
                             VALUES (UUID(), :a, 'driver', :d, 'credentials', :c, 'read')"""),
                     {"a": co["acct"], "d": co["driver"], "c": l1})
    assert requirement(co, "FL_LEVEL1_DRIVER")["status"] == "review"

    def put(result, reason=None):
        return co["client"].put(f"/api/credentials/{l1}/result", headers=co["h"],
                                json={"result": result, "reason": reason})
    assert put("ineligible").status_code == 200
    assert requirement(co, "FL_LEVEL1_DRIVER")["status"] == "failed"
    assert put("eligible").status_code == 400
    assert put("eligible", "WRONG DRIVER'S RESULT RECORDED").status_code == 200
    assert requirement(co, "FL_LEVEL1_DRIVER")["status"] == "satisfied"
    # The earlier determination is not lost: each change is kept with what it replaced.
    with co["db"].connect() as conn:
        kept = [json.loads(x) for x in conn.execute(text(
            "SELECT detail FROM activitylog WHERE accountid = :a AND action = 'result' "
            "AND entityid = :c ORDER BY added"), {"a": co["acct"], "c": l1}).scalars()]
    assert kept == [{"result": "ineligible", "was": None, "reason": None},
                    {"result": "eligible", "was": "ineligible", "reason": "WRONG DRIVER'S RESULT RECORDED"}], kept


def test_3b_an_optional_requirement_not_adopted_reaches_nobody(make):
    co = make()
    got = requirement(co, "ABUSE_REGISTRY_CHECK")
    assert got is None or (got["applies"] is False and got["status"] == "notapplicable"), got


def test_3c_a_background_report_with_adverse_findings_fails_though_reviewed(make):
    co = make()
    add_line(co, co["payer"], "GA")
    with co["db"].begin() as conn:
        conn.execute(text("""INSERT INTO driverreports (recordid, accountid, driverid, code, receivedon,
                                                        issuedon, outcome, reviewstate)
                             VALUES (UUID(), :a, :d, 'BACKGROUND_SCREENING', NOW(), CURDATE(),
                                     'flagged', 'reviewed')"""), {"a": co["acct"], "d": co["driver"]})
    got = requirement(co, "GA_NET_BACKGROUND")
    assert got["applies"] is True and got["status"] == "failed", got


# 4. Driving records and annual reviews are read as their findings --------------------------------

def driving_record(co, finding, note=None):
    """A Florida license, and a driving record on it read through the review endpoint."""
    c = co["client"]
    lic = c.post(f"/api/drivers/{co['driver']}/licenses", headers=co["h"], json={
        "number": f"L{co['tag']}", "state": "FL", "classification": "E", "commercial": False,
        "issued": "2020-01-01", "expires": "2030-01-01", "active": True}).json()["recordid"]
    mvr = f"m-{uuid.uuid4().hex[:12]}"
    with co["db"].begin() as conn:
        conn.execute(text("""INSERT INTO drivermvrs (recordid, accountid, driverid, licenseid, receivedon,
                                                     issuedon)
                             VALUES (:m, :a, :d, :l, NOW(), CURDATE())"""),
                     {"m": mvr, "a": co["acct"], "d": co["driver"], "l": lic})
    r = c.post(f"/api/drivers/{co['driver']}/mvrs/{mvr}/reviewed", headers=co["h"],
               json={"finding": finding, "note": note})
    assert r.status_code == 200, r.text
    return mvr


@pytest.mark.parametrize("finding,note,expected", [
    ("qualified", None, "satisfied"),
    ("restricted", "DAYLIGHT DRIVING ONLY", "review"),
    ("disqualified", "LICENSE SUSPENDED 2023", "failed"),
])
def test_4_a_georgia_driving_record_is_read_as_its_finding(make, finding, note, expected):
    """Restricted clears nobody outright, and a suspension within Georgia's five years read as
    disqualifying fails Georgia's rule whatever else is on file."""
    co = make()
    add_line(co, co["payer"], "GA")
    driving_record(co, finding, note)
    got = requirement(co, "GA_NET_MVR")
    assert got["status"] == expected, got
    if note:
        assert note in got["why"], got


def test_4b_a_changed_finding_keeps_the_first_one_on_the_record(make):
    co = make()
    add_line(co, co["payer"], "GA")
    mvr = driving_record(co, "qualified")
    r = co["client"].post(f"/api/drivers/{co['driver']}/mvrs/{mvr}/reviewed", headers=co["h"],
                          json={"finding": "disqualified", "note": "SUSPENSION FOUND ON SECOND READING"})
    assert r.status_code == 200
    assert requirement(co, "GA_NET_MVR")["status"] == "failed"
    with co["db"].connect() as conn:
        said = [json.loads(x)["finding"] for x in conn.execute(text(
            "SELECT detail FROM activitylog WHERE accountid = :a AND action = 'reviewed' "
            "AND entitytype = 'drivermvr' ORDER BY added"), {"a": co["acct"]}).scalars()]
    assert said == ["qualified", "disqualified"], said


@pytest.mark.parametrize("finding,expected", [
    ("qualified", "satisfied"), ("corrective", "review"), ("notqualified", "failed")])
def test_4c_an_annual_review_is_read_as_its_finding(make, finding, expected):
    """391.25: corrective action noted stays open until a later review records it done, and a new
    review can be started for it; disqualified under 391.15 fails."""
    from app import annualreview
    co = make()
    driver = new_driver(co, "Cdl", operation="cdlheavy")
    with co["db"].begin() as conn:
        # A Florida carrier that stays in Florida, running a heavy CMV: Part 391 reaches the driver
        # through Florida's adoption (F.S. 316.302), so the annual review is owed.
        conn.execute(text("INSERT INTO companyanswers (accountid, code, answer, updated) "
                          "VALUES (:a, 'INTERSTATE', 0, NOW())"), {"a": co["acct"]})
        conn.execute(text("""INSERT INTO annualreviews (recordid, accountid, driverid, reviewedon, finding, note)
                             VALUES (UUID(), :a, :d, CURDATE(), :f, 'COUNSEL ON SPEEDING')"""),
                     {"a": co["acct"], "d": driver, "f": finding})
    got = requirement(co, "MVR_ANNUAL", driver)
    assert got["status"] == expected, got
    if finding == "corrective":
        assert "COUNSEL ON SPEEDING" in got["why"], got
        with co["db"].connect() as conn:
            assert annualreview.due(conn, co["acct"], driver)["startable"]


# 5. Vehicle defects: held through dispatch until certified, by somebody allowed to -----------------

def test_5_a_defect_holds_the_vehicle_in_dispatch_until_certified(make):
    from app import dispatch
    co = make()
    # Two passenger vans for hire: a carrier running more than one CMV, so 396.11 reaches them.
    vans = [new_vehicle(co, f"V{i}", seats=12, forcompensation=True) for i in (1, 2)]
    report = defect(co, vans[0])
    when = datetime.combine(date.today() + timedelta(days=1), datetime.min.time()).replace(hour=9)

    def listed(van):
        conn = co["db"].connect()
        trans = conn.begin()
        try:
            approved(conn, "DVIR")
            return next(v for v in dispatch.best(conn, co["acct"], when=when, minutes=60)["vehicles"]
                        if v["vehicleid"] == van)
        finally:
            trans.rollback()
            conn.close()
    held, free = listed(vans[0]), listed(vans[1])
    assert not held["available"] and any("defect" in b.lower() for b in held["blocked"]), held
    assert free["available"], free
    # Certified as needing no repair, by somebody in the office: released, and who is recorded.
    r = co["client"].put(f"/api/vehicles/{vans[0]}/dvirs/{report}/corrected", headers=co["h"],
                         json={"correctedon": str(date.today()), "correction": "notneeded"})
    assert r.status_code == 200, r.text
    assert listed(vans[0])["available"]
    me = co["client"].get("/api/auth/me", headers=co["h"]).json()
    with co["db"].connect() as conn:
        held = conn.execute(text("SELECT correction, certifiedby FROM vehicledvirs WHERE recordid = :r"),
                            {"r": report}).mappings().one()
    assert held["correction"] == "notneeded" and held["certifiedby"] == me["recordid"], held


def test_5b_only_an_editor_of_the_same_company_may_certify_or_record_a_result(make):
    from app.routers import admin
    from app.security import hash_password
    co, other = make(), make()
    report = defect(co, co["vehicle"], "MIRROR")
    with co["db"].begin() as conn:
        auditor = admin._create_user(conn, co["acct"], f"aud-{co['tag']}@acceptance.test", "Auditor",
                                     "auditor", None, "America/New_York")
        conn.execute(text("UPDATE users SET passwordhash = :p WHERE recordid = :u"),
                     {"p": hash_password(PASSWORD), "u": auditor["recordid"]})
    insp = credential(co, "BROKER_VEHICLE_INSPECTION", "vehicle", co["vehicle"], date.today())
    certify = {"correctedon": str(date.today()), "correction": "notneeded"}
    c = co["client"]
    # A read-only login of the same company may do neither.
    ro = login(c, f"aud-{co['tag']}@acceptance.test")
    assert c.put(f"/api/vehicles/{co['vehicle']}/dvirs/{report}/corrected", headers=ro,
                 json=certify).status_code == 403
    assert c.put(f"/api/credentials/{insp}/result", headers=ro, json={"result": "passed"}).status_code == 403
    # Another company's owner cannot reach this company's records at all.
    assert c.put(f"/api/vehicles/{co['vehicle']}/dvirs/{report}/corrected", headers=other["h"],
                 json=certify).status_code == 404
    assert c.put(f"/api/credentials/{insp}/result", headers=other["h"],
                 json={"result": "passed"}).status_code == 404
    with co["db"].connect() as conn:
        assert conn.execute(text("SELECT correctedon FROM vehicledvirs WHERE recordid = :r"),
                            {"r": report}).scalar() is None
        assert conn.execute(text("SELECT result FROM credentials WHERE recordid = :r"),
                            {"r": insp}).scalar() is None


# 5b. One Social Security number is one person, on every company ---------------------------------

def test_5b_a_signature_is_created_only_for_an_ssn_nobody_else_holds(make):
    """First come holds the number. The same number is refused to a second company, refused with
    another birth date, and allowed only to the same person signing at the same company as the
    other of office user and driver."""
    from app import signatures
    one, two = make(), make()
    ssn, dob = f"433-{uuid.uuid4().int % 90 + 10:02d}-{uuid.uuid4().int % 9000 + 1000:04d}", date(1980, 5, 6)
    conn = one["db"].connect()
    trans = conn.begin()
    try:
        signatures.claim(conn, one["acct"], "driver", one["driver"], "PAT QUINN", ssn, dob)
        signatures.claim(conn, one["acct"], "driver", one["driver"], "PAT QUINN", ssn, dob)  # again: fine
        with pytest.raises(ValueError, match="already used"):
            signatures.claim(conn, two["acct"], "driver", two["driver"], "PAT QUINN", ssn, dob)
        with pytest.raises(ValueError, match="already used"):
            signatures.claim(conn, one["acct"], "user", "some-user", "PAT QUINN", ssn, date(1969, 1, 1))
        with pytest.raises(ValueError, match="already used"):
            signatures.claim(conn, one["acct"], "user", "some-user", "SOMEBODY ELSE", ssn, dob)
        signatures.claim(conn, one["acct"], "user", "some-user", "Pat  Quinn", ssn, dob)       # owner who drives
        with pytest.raises(ValueError, match="already used"):
            signatures.claim(conn, one["acct"], "user", "another-user", "PAT QUINN", ssn, dob)
        with pytest.raises(ValueError, match="needs the signer"):
            signatures.adopt(conn, one["acct"], "driver", one["driver"], "PAT QUINN", "PAT QUINN",
                             "modern", "dob_ssn")
    finally:
        trans.rollback()
        conn.close()


# 5c. A booked trip can be put right, within what its stage allows ---------------------------------

def test_5c_a_trip_is_edited_within_its_stage_and_the_driver_must_read_the_change(make):
    from app.routers import driverapp
    co = make()
    c, h = co["client"], co["h"]
    on = date.today() + timedelta(days=3)
    made = c.post("/api/trips", headers=h, json={
        "passenger": "EDIT TEST", "tripdate": str(on),
        "legs": [{"pickupat": f"{on}T09:00:00", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
                  "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}]}).json()
    tripid = made["recordid"]
    trip = c.get(f"/api/trips/{tripid}", headers=h).json()
    legid = trip["legs"][0]["recordid"]
    assert trip["edit"] == {"locked": None, "legs": {legid: "open"}, "tripfields": True,
                            "reasonrequired": False}

    def body(**over):
        b = {"passenger": "EDIT TEST", "servicelevel": "ambulatory", "payer": "private",
             "legs": [{"legid": legid, "pickupat": f"{on}T09:00:00",
                       "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
                       "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}]}
        for k, v in over.items():
            if k in ("pickupat", "pickupplace", "dropoffplace", "dropoffat", "miles"):
                b["legs"][0][k] = v
            else:
                b[k] = v
        return b

    # Before anybody sets off: anything, no reason needed, and nothing changed is said so.
    assert c.put(f"/api/trips/{tripid}", headers=h, json=body()).status_code == 400
    r = c.put(f"/api/trips/{tripid}", headers=h, json=body(passenger="Edit  Tested", pickupat=f"{on}T10:30:00"))
    assert r.status_code == 200, r.text
    with co["db"].connect() as conn:
        kept = conn.execute(text("SELECT passenger FROM trips WHERE recordid = :t"), {"t": tripid}).scalar()
        change = conn.execute(text("SELECT changes, driverid FROM tripchanges WHERE tripid = :t"),
                              {"t": tripid}).mappings().one()
    assert kept == "EDIT TESTED"
    assert {x["field"] for x in json.loads(change["changes"])} == {"Passenger", "Pickup time"}
    assert change["driverid"] is None                      # nobody on it to tell

    # Under way, with a driver on it: only the drop-off, with a reason, and the driver must read it.
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE triplegs SET driverid = :d, executionstate = 'enroute' WHERE recordid = :l"),
                     {"d": co["driver"], "l": legid})
    assert c.get(f"/api/trips/{tripid}", headers=h).json()["edit"]["reasonrequired"] is True
    refused = c.put(f"/api/trips/{tripid}", headers=h, json=body(passenger="EDIT TESTED", servicelevel="wheelchair",
                                                                 pickupat=f"{on}T10:30:00"))
    assert refused.status_code == 409 and "started" in refused.text, refused.text
    moved = body(passenger="EDIT TESTED", pickupat=f"{on}T10:30:00", dropoffplace="9 ELM ST, ORLANDO, FL 32801")
    assert c.put(f"/api/trips/{tripid}", headers=h, json=moved).status_code == 400   # no reason
    r = c.put(f"/api/trips/{tripid}", headers=h, json={**moved, "reason": "PASSENGER ASKED"})
    assert r.status_code == 200, r.text
    with co["db"].connect() as conn:
        driver = {"accountid": co["acct"], "recordid": co["driver"]}
        unread = driverapp._unread(conn, driver, legid)
    assert len(unread) == 1 and unread[0]["changes"][0]["new"] == "9 ELM ST, ORLANDO, FL 32801"

    # Billed: nothing.
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE trips SET billingstatus = 'billed' WHERE recordid = :t"), {"t": tripid})
    billed = c.put(f"/api/trips/{tripid}", headers=h, json={**moved, "reason": "X", "note": "LATE NOTE"})
    assert billed.status_code == 409 and "billed" in billed.text
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE trips SET billingstatus = 'unbilled' WHERE recordid = :t"), {"t": tripid})
    # Finished: nothing at all, and the trip says so.
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE tripchanges SET seenon = UTC_TIMESTAMP() WHERE tripid = :t"), {"t": tripid})
        conn.execute(text("UPDATE triplegs SET executionstate = 'completed', dropoffat = :d WHERE recordid = :l"),
                     {"d": f"{on} 11:40:00", "l": legid})
    assert "finished" in c.get(f"/api/trips/{tripid}", headers=h).json()["edit"]["locked"]
    done = body(passenger="EDIT TESTED", pickupat=f"{on}T10:30:00", dropoffplace="9 ELM ST, ORLANDO, FL 32801")
    refused = c.put(f"/api/trips/{tripid}", headers=h, json={**done, "reason": "ODOMETER READ WRONG",
                                                             "legs": [{**done["legs"][0], "miles": 14.2}]})
    assert refused.status_code == 409 and "finished" in refused.text, refused.text
    # Leave nothing behind for the grids other tests count.
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE trips SET deleted = UTC_TIMESTAMP() WHERE recordid = :t"), {"t": tripid})


def test_5d_a_will_call_is_booked_without_a_time_and_released_when_the_passenger_calls(make):
    co = make()
    c, h = co["client"], co["h"]
    on = date.today() + timedelta(days=4)
    there = {"pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207", "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}
    back = {"pickupplace": there["dropoffplace"], "dropoffplace": there["pickupplace"], "pickupat": None}
    assert c.post("/api/trips", headers=h, json={"passenger": "WILL CALL", "tripdate": str(on),
                                                 "legs": [{**there, "pickupat": None}]}).status_code == 400
    made = c.post("/api/trips", headers=h, json={"passenger": "WILL CALL", "tripdate": str(on),
                                                 "legs": [{**there, "pickupat": f"{on}T08:00:00"}, back]})
    assert made.status_code == 200, made.text
    with co["db"].connect() as conn:
        ret = conn.execute(text("SELECT recordid, pickupat FROM triplegs WHERE tripid = :t AND legnumber = 2"),
                           {"t": made.json()["recordid"]}).mappings().one()
    assert ret["pickupat"] is None

    def board(day):
        return {i["legid"] for i in c.get(f"/api/dispatch/board?day={day}&state=all&pagesize=200",
                                          headers=h).json()["items"]}
    # Waiting for the call, it is on every day's board; canceled, only on the day it was canceled.
    other = c.post("/api/trips", headers=h, json={"passenger": "WILL CALL TWO", "tripdate": str(on),
                                                  "legs": [{**there, "pickupat": f"{on}T08:00:00"}, back]})
    with co["db"].connect() as conn:
        gone = conn.execute(text("SELECT recordid FROM triplegs WHERE tripid = :t AND legnumber = 2"),
                            {"t": other.json()["recordid"]}).scalar()
    assert gone in board(on + timedelta(days=9))
    assert c.post(f"/api/trips/{other.json()['recordid']}/cancel", headers=h,
                  json={"reason": "passenger"}).status_code == 200
    assert gone not in board(on + timedelta(days=9))
    assert gone in board(date.today()) or gone in board(date.today() - timedelta(days=1))   # UTC edge
    assert ret["recordid"] in board(on + timedelta(days=9))
    # A call is not always "come and get me". Not ready: written down, still waiting. Not needed:
    # the return is closed as canceled, with why - and "something else" has to say what.
    third = c.post("/api/trips", headers=h, json={"passenger": "WILL CALL THREE", "tripdate": str(on),
                                                  "legs": [{**there, "pickupat": f"{on}T08:00:00"}, back]})
    with co["db"].connect() as conn:
        late = conn.execute(text("SELECT recordid FROM triplegs WHERE tripid = :t AND legnumber = 2"),
                            {"t": third.json()["recordid"]}).scalar()
    assert c.post(f"/api/legs/{late}/call", headers=h,
                  json={"answer": "notready", "note": "CALL BACK AT 3"}).status_code == 200
    waiting = next(i for i in c.get(f"/api/dispatch/board?day={on}&state=all&pagesize=200",
                                    headers=h).json()["items"] if i["legid"] == late)
    assert waiting["outcomestate"] is None and "NOT READY YET - CALL BACK AT 3" in waiting["lastcall"]
    assert c.post(f"/api/legs/{late}/call", headers=h,
                  json={"answer": "notneeded", "reason": "other"}).status_code == 400
    assert c.post(f"/api/legs/{late}/call", headers=h,
                  json={"answer": "notneeded", "reason": "admitted"}).status_code == 200
    with co["db"].connect() as conn:
        assert conn.execute(text("SELECT outcomestate FROM triplegs WHERE recordid = :l"),
                            {"l": late}).scalar() == "cancelled"
        assert conn.execute(text("SELECT outcomestate FROM triplegs WHERE tripid = :t AND legnumber = 1"),
                            {"t": third.json()["recordid"]}).scalar() is None
    r = c.post(f"/api/legs/{ret['recordid']}/release", headers=h, json={"pickupat": f"{on}T11:45:00", "note": "AT THE FRONT DOOR"})
    assert r.status_code == 200, r.text
    assert c.post(f"/api/legs/{ret['recordid']}/release", headers=h,
                  json={"pickupat": f"{on}T12:00:00"}).status_code == 409
    with co["db"].connect() as conn:
        kept = conn.execute(text("SELECT pickupat FROM triplegs WHERE recordid = :l"), {"l": ret["recordid"]}).scalar()
        said = conn.execute(text("SELECT reason, changes FROM tripchanges WHERE legid = :l"),
                            {"l": ret["recordid"]}).mappings().one()
        conn.execute(text("UPDATE trips SET deleted = UTC_TIMESTAMP() WHERE recordid = :t"), {"t": made.json()["recordid"]})
        conn.commit()
    assert kept == datetime(on.year, on.month, on.day, 11, 45)
    assert said["reason"] == "PASSENGER CALLED - AT THE FRONT DOOR"
    assert json.loads(said["changes"])[0]["old"] == "Will-call"


def test_5e_the_validity_panel_carries_what_recurs_by_the_month_and_the_driving_record_stays_listed(make):
    """An obligation that comes round every twelve months - the annual review of the driving
    record - is on the validity-tracked panel with when it is next due, before it has ever been
    done; and the driving record itself stays on a hired driver's requirements."""
    co = make()
    driving_record(co, "qualified")
    with co["db"].begin() as conn:
        # Interstate, and a commercial-vehicle driver: Part 391 reaches them, so the driving record
        # and its annual review are theirs to keep.
        conn.execute(text("INSERT INTO companyanswers (accountid, code, answer, updated) "
                          "VALUES (:a, 'INTERSTATE', 1, NOW())"), {"a": co["acct"]})
        conn.execute(text("UPDATE drivers SET status = 'hired', hiredon = CURDATE(), operation = 'cmv' "
                          "WHERE recordid = :d"), {"d": co["driver"]})
    dash = co["client"].get(f"/api/drivers/{co['driver']}/dashboard", headers=co["h"]).json()
    items = co["client"].get(f"/api/drivers/{co['driver']}/requirements", headers=co["h"]).json()["items"]
    # Every document on file with an end date is on the panel, whatever its rule's recurrence; so
    # is every interval check owed and not yet due; and the driving record, with its year.
    live = [i for i in items if i["applies"] is True and i.get("evidencekind") != "record"]
    mvr_on = any((i.get("evidencesource") or "").startswith("mvr") and i.get("on") for i in live)
    owed = {i["code"] for i in live
            if not (mvr_on and i.get("evidencesource") == "annualreview")
            and ((i.get("on") and i.get("expireson"))
                 or (not i.get("on") and i.get("dueon") and i.get("recurrence") in ("days", "months")
                     and i["status"] in ("pending", "overdue")))}
    owed |= {i["code"] for i in live if (i.get("evidencesource") or "").startswith("mvr") and i.get("on")}
    shown = {x["code"] for x in dash["tracked"]}
    assert "MVR_PREEMPLOYMENT" in owed                  # the case this is about is actually here
    assert owed <= shown, (owed - shown, dash["tracked"])
    assert all(x["expireson"] for x in dash["tracked"])
    # Owed but not yet due is not waiting on anybody today: the annual review sits on the validity
    # panel with its date, not in "Waiting On Us".
    waiting = {x["code"] for lst in dash["waiting"].values() for x in lst}
    assert "MVR_ANNUAL" not in waiting, dash["waiting"]
    mvr = next(i for i in items if i["code"] == "MVR_PREEMPLOYMENT")
    assert mvr["evidencesource"].startswith("mvr")     # what keeps it on the hired driver's list


def test_5f_a_driving_record_runs_out_twelve_months_after_it_was_pulled_and_is_said_so_everywhere(make):
    co = make()
    driving_record(co, "qualified")
    pulled = date.today() - timedelta(days=355)          # runs out in about ten days
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE drivermvrs SET issuedon = :p WHERE driverid = :d"), {"p": pulled, "d": co["driver"]})
        conn.execute(text("INSERT INTO companyanswers (accountid, code, answer, updated) "
                          "VALUES (:a, 'INTERSTATE', 1, NOW())"), {"a": co["acct"]})
        conn.execute(text("UPDATE drivers SET status = 'hired', hiredon = CURDATE(), operation = 'cmv' "
                          "WHERE recordid = :d"), {"d": co["driver"]})
    c, h = co["client"], co["h"]
    runsout = c.get(f"/api/drivers/{co['driver']}/dashboard", headers=h).json()
    mvr = [x for x in runsout["tracked"] if x["code"] == "MVR_PREEMPLOYMENT"]
    assert mvr and mvr[0]["band"] == "expiring", runsout["tracked"]
    assert any(x["code"] == "MVR_PREEMPLOYMENT" for x in runsout["expiring"]), runsout["expiring"]
    board = c.get("/api/dashboard", headers=h).json()
    assert any(x["typename"] == "Motor vehicle record" and x["subjectid"] == co["driver"]
               for x in board["expiring"]), board["expiring"]
    # The first annual review is counted from the record too, not only from the day of hire.
    from app import rules
    rule = {"duestage": "ongoing", "recurrence": "months", "recurrencemonths": 12,
            "evidencesource": "annualreview"}
    assert rules.deadline(rule, date.today(), None, pulled) < date.today() + timedelta(days=30)


def test_5g_a_working_sign_in_is_renewed_and_an_expired_one_is_not(make):
    import jwt as pyjwt
    from app.config import settings
    co = make()
    c, h = co["client"], co["h"]
    renewed = c.post("/api/auth/refresh", headers=h, json={})
    assert renewed.status_code == 200, renewed.text
    claims = pyjwt.decode(renewed.json()["token"], settings.jwt_secret, algorithms=["HS256"])
    assert claims["exp"] - claims["iat"] == settings.jwt_minutes * 60
    assert c.get("/api/auth/me", headers={"Authorization": f"Bearer {renewed.json()['token']}"}).status_code == 200
    gone = pyjwt.encode({"sub": claims["sub"], "iat": 1, "exp": 2}, settings.jwt_secret, algorithm="HS256")
    assert c.post("/api/auth/refresh", headers={"Authorization": f"Bearer {gone}"}, json={}).status_code == 401


# 5h. On a trip, the vehicle decides what the driver is operating ---------------------------------

def test_5h_the_vehicle_on_the_trip_decides_whether_the_commercial_and_1490_rules_reach_the_driver(make):
    """CF-1 and CF-5 from the MODIVTEST run: a driver ticked for no commercial vehicles, put in a
    15-passenger bus, is held to Part 391 for that trip; one ticked for commercial vehicles, in a
    sedan, is not. The driver's own file - no vehicle - still reads the ticks."""
    from app import facts as factset
    co = make()
    bus = new_vehicle(co, "BUS15", seats=15, gvwr=14500, forcompensation=True)
    car = new_vehicle(co, "CAR5", seats=5, gvwr=4500, forcompensation=True)
    with co["db"].begin() as conn:
        conn.execute(text("INSERT INTO companyanswers (accountid, code, answer, updated) "
                          "VALUES (:a, 'INTERSTATE', 1, NOW())"), {"a": co["acct"]})
    def reach(operation, vehicle):
        with co["db"].begin() as conn:
            conn.execute(text("UPDATE drivers SET operation = :o WHERE recordid = :d"),
                         {"o": operation, "d": co["driver"]})
            f = factset.assemble(conn, co["acct"], co["driver"], vehicle)["facts"]
        return f["driver.cmv"], f["reach.part391"]
    assert reach("noncmv", bus) == (True, True)        # in the bus: a CMV driver for this trip
    assert reach("cmv", car) == (False, False)          # in the sedan: not one
    assert reach("cmv", None) == (True, True)           # their file still reads the tick
    assert reach("noncmv", None)[0] is False
    # CF-3: a line that approves its vehicles refuses one it has not approved, like a driver.
    from app import tripcheck
    line_ = {"requiresapproval": 1, "recordid": "no-such-line", "broker": "TESTBROKER", "state": "GA",
             "program": "medicaid"}
    with co["db"].begin() as conn:
        found = tripcheck.vehicle_blockers(conn, co["acct"], car, None, datetime.now(), ["GA"],
                                           "medicaid", line_)
    assert any(b["code"] == "VEHICLEAPPROVAL" and b["enforceable"] for b in found), found
    # CF-4: securement training follows the vehicle on the trip, and the fleet on the driver's file.
    lift = new_vehicle(co, "LIFTVAN", seats=7, gvwr=9500, forcompensation=True, lift=True)
    with co["db"].begin() as conn:
        def wc(vehicle):
            return factset.assemble(conn, co["acct"], co["driver"], vehicle)["facts"]["driver.wheelchairvehicle"]
        assert wc(car) is False and wc(lift) is True and wc(None) is True


def test_5i_adding_a_driver_keeps_everything_on_the_form(make):
    """B-01 from the MODIVTEST run: the create endpoint wrote only names, licence and dates, so the
    address, the operation, the emergency contact and English proficiency were dropped."""
    co = make()
    c, h = co["client"], co["h"]
    form = {"firstname": "GINA", "lastname": "FORM", "address1": "12 OAK ST", "city": "VALDOSTA",
            "state": "ga", "zip": "31601", "operation": "cdl", "englishproficient": True,
            "emergencyname": "PAT FORM", "emergencyphone": "(229) 555-0100",
            "endorsementsneeded": "p, s", "phone": "(229) 555-0199", "email": "gina@form.test"}
    made = c.post("/api/drivers", headers=h, json=form)
    assert made.status_code == 200, made.text
    kept = c.get(f"/api/drivers/{made.json()['recordid']}", headers=h).json()
    assert (kept["address1"], kept["city"], kept["state"], kept["zip"]) == ("12 OAK ST", "VALDOSTA", "GA", "31601")
    assert kept["operation"] == "cdl" and kept["englishproficient"] == 1
    assert kept["emergencyname"] == "PAT FORM" and kept["endorsementsneeded"] == "PS"


def test_5j_a_rules_own_interval_beats_an_expiry_only_assumed_from_the_document_type():
    """B-02 from the MODIVTEST run: a Georgia inspection on 08/15 ended 02/13, by the type's assumed
    183 days, instead of 02/15 by the rule's six calendar months. A date printed on the document
    still stands where it is earlier."""
    from app import rules
    six = {"recurrence": "months", "recurrencemonths": 6}
    assumed = {"effectiveon": date(2026, 8, 15), "expireson": date(2027, 2, 13), "assumedexpiry": True}
    printed = {"effectiveon": date(2026, 8, 15), "expireson": date(2027, 1, 31), "assumedexpiry": False}
    assert rules.horizon(six, assumed) == date(2027, 2, 15)
    assert rules.horizon(six, printed) == date(2027, 1, 31)
    yearly = {"recurrence": "months", "recurrencemonths": 12}
    assert rules.horizon(yearly, {"effectiveon": date(2026, 3, 1), "expireson": date(2027, 2, 28),
                                  "assumedexpiry": True}) == date(2027, 3, 1)


def test_5k_a_driver_the_office_entered_answers_both_questions_by_link(make):
    """B-04 from the MODIVTEST run: the questionnaire and the license question were read only off an
    online application, so a driver the office entered could never answer either. Both are asked by
    link now, answered and signed by the driver, and the answers are what the engine reads."""
    from app import facts as factset, signatures
    co = make()
    c, h = co["client"], co["h"]
    ssn, dob = f"433-{uuid.uuid4().int % 90 + 10:02d}-{uuid.uuid4().int % 9000 + 1000:04d}", "1985-03-04"
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET dob = :b, ssnhash = :h WHERE recordid = :d"),
                     {"b": dob, "h": signatures.ssn_hash(co["acct"], ssn), "d": co["driver"]})
        assert not conn.execute(text("SELECT 1 FROM driverapplications WHERE driverid = :d"),
                                {"d": co["driver"]}).first()
    def answer(code, **form):
        asked = c.post(f"/api/drivers/{co['driver']}/upload-requests", headers=h, json={"code": code})
        assert asked.status_code == 200, asked.text
        token = asked.json()["link"].rsplit("/upload/", 1)[1]
        r = c.post(f"/api/upload-request/{token}",
                   data={"dob": dob, "ssn": ssn, "signature": "ADA TEST", "fontkey": "modern", **form})
        assert r.status_code == 200, r.text
    answer("LICENSE_ACTION_QUESTION", licenseaction="no")
    answer("PREEMP_DA_QUESTIONNAIRE", priorviolation="no")
    with co["db"].connect() as conn:
        f = factset.assemble(conn, co["acct"], co["driver"])["facts"]
    assert f["driver.licenseaction"] is False and f["driver.priorviolation"] is False


def test_5l_a_driver_without_a_cdl_has_an_answer_to_the_spe_question(make):
    """B-05: the SPE question waited for a driving record carrying medical information, which only a
    CDL holder's record ever carries. Without a CDL, no SPE certificate on file is a definite no."""
    from app import facts as factset
    co = make()
    driving_record(co, "qualified")                       # a Florida Class E, not commercial
    with co["db"].connect() as conn:
        assert factset.assemble(conn, co["acct"], co["driver"])["facts"]["driver.spevariance"] is False


def test_5m_the_wording_names_the_rule_that_failed_and_reads_as_english():
    """B-08: under 21 is said in the terms of the rule that failed, not always the federal one.
    B-10: "an AL line", "a GA line"."""
    from app import rules, tripcheck
    georgia = {"code": "GA_NET_AGE21", "authority": "Georgia DCH",
               "citation": "DCH NEMT Part II (October 2026), Section 914.2.1", "recurrence": "once"}
    federal = {**georgia, "authority": "FMCSA", "citation": "49 CFR 391.11(b)(1)"}
    under = {"determination": "notage21", "effectiveon": date.today()}
    assert "914.2.1" in rules.stand(georgia, under, date.today())[1]
    assert "391.11(b)(1)" in rules.stand(federal, under, date.today())[1]
    assert (tripcheck._a("AL"), tripcheck._a("GA"), tripcheck._a("FL")) == ("an", "a", "an")


def test_5n_a_programs_own_shortfall_does_not_disqualify_the_driver_from_everything(make):
    """Faye, 19: only Georgia Medicaid requires 21. Her banner said "Disqualified From Safety-Sensitive
    Functions" while dispatch put her on Florida trips. The banner reads general sources only, as
    dispatch does; the program's own shortfall stays on the program's line."""
    co = make()
    add_line(co, co["payer"], "GA")
    nineteen = date.today().replace(year=date.today().year - 19) - timedelta(days=10)
    with co["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET dob = :b, status = 'hired', hiredon = CURDATE() "
                          "WHERE recordid = :d"), {"b": nineteen, "d": co["driver"]})
    standing = co["client"].get(f"/api/drivers/{co['driver']}/standing", headers=co["h"]).json()
    assert not any("age" in x["name"].lower() for x in standing["stops"]), standing["stops"]


# 5o. The day's shifts ---------------------------------------------------------------------------

def test_5o_a_days_shifts_pair_drivers_with_vehicles_only_where_the_rules_allow(make):
    """One shift per driver a day, one vehicle per shift at a time, never an unlawful pairing - all
    refused on the server - and Auto Generate proposes without saving."""
    co = make()
    c, h = co["client"], co["h"]
    day = (date.today() + timedelta(days=5)).isoformat()
    second = new_vehicle(co, "AV2")
    bea = new_driver(co, "Bea")
    applicant = new_driver(co, "Cy", status="new")
    shift = {"day": day, "driverid": co["driver"], "vehicleid": co["vehicle"],
             "startsat": "08:00", "endsat": "16:00"}
    first = c.post("/api/shifts", headers=h, json=shift)
    assert first.status_code == 200, first.text
    assert c.post("/api/shifts", headers=h, json=shift).status_code == 409            # driver twice
    overlap = c.post("/api/shifts", headers=h, json={**shift, "driverid": bea, "startsat": "15:00",
                                                     "endsat": "23:00"})
    assert overlap.status_code == 409 and "AV1" in overlap.text                         # vehicle taken
    later = c.post("/api/shifts", headers=h, json={**shift, "driverid": bea, "startsat": "16:00",
                                                   "endsat": "23:00"})
    assert later.status_code == 200, later.text                                         # back to back
    refused = c.post("/api/shifts", headers=h, json={**shift, "driverid": applicant, "vehicleid": second})
    assert refused.status_code == 409 and "Not hired" in refused.text
    # Generating proposes, and saves nothing until the plan is saved.
    got = c.post("/api/shifts/generate", headers=h, json={"day": day, "drivers": [
        {"driverid": co["driver"], "startsat": "07:00", "endsat": "17:00"}]})
    assert got.status_code == 200, got.text
    proposal = got.json()["proposal"]
    # AV1 is her usual vehicle, but Bea has it from 16:00 and this runs to 17:00: AV2.
    assert proposal[0]["vehicleid"] == second, proposal
    assert co["driver"] in c.post("/api/shifts/eligible", headers=h, json={"day": day}).json()["drivers"]
    before = c.get(f"/api/shifts?day={day}", headers=h).json()["shifts"]
    assert {s["startsat"] for s in before if s["driverid"] == co["driver"]} == {"08:00"}
    saved_ = c.post("/api/shifts/plan", headers=h, json={"day": day, "shifts": [
        {**{k: proposal[0][k] for k in ("driverid", "vehicleid", "startsat", "endsat")},
         "day": day, "reasons": proposal[0]["reasons"], "source": "auto"}]})
    assert saved_.status_code == 200, saved_.text
    after = c.get(f"/api/shifts?day={day}", headers=h).json()["shifts"]
    mine = [s for s in after if s["driverid"] == co["driver"]]
    assert len(mine) == 1 and mine[0]["startsat"] == "07:00" and mine[0]["source"] == "auto"
    assert mine[0]["vehicleid"] == second
    # Changing vehicles at noon: the morning shift ends there and the afternoon one starts. Without
    # saying it is a switch, the overlap is refused.
    noon = {"day": day, "driverid": co["driver"], "vehicleid": co["vehicle"], "startsat": "12:00",
            "endsat": "15:00"}
    assert c.post("/api/shifts", headers=h, json=noon).status_code == 409
    switched = c.post("/api/shifts", headers=h, json={**noon, "switch": True})
    assert switched.status_code == 200, switched.text
    hers = sorted((s["startsat"], s["endsat"], s["vehicleid"]) for s in
                  c.get(f"/api/shifts?day={day}", headers=h).json()["shifts"] if s["driverid"] == co["driver"])
    assert hers == [("07:00", "12:00", second), ("12:00", "15:00", co["vehicle"])], hers


def test_5p_a_trip_goes_to_a_driver_on_shift_in_the_shifts_vehicle(make):
    """Dropped on a driver, a trip takes the vehicle of the shift they are on at the pickup - and a
    driver on no shift then is refused. Auto Assign proposes only drivers on shift, saves nothing,
    and what it saves passes the ordinary gate."""
    co = make()
    c, h = co["client"], co["h"]
    on = date.today() + timedelta(days=6)
    bea = new_driver(co, "Bea")
    assert c.post("/api/shifts", headers=h, json={"day": str(on), "driverid": co["driver"],
                                                  "vehicleid": co["vehicle"], "startsat": "08:00",
                                                  "endsat": "16:00"}).status_code == 200
    trip = c.post("/api/trips", headers=h, json={
        "passenger": "SHIFT TEST", "tripdate": str(on),
        "legs": [{"pickupat": f"{on}T10:00:00", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
                  "dropoffplace": "1 MAIN ST, JACKSONVILLE, FL 32202"},
                 {"pickupat": None, "pickupplace": "1 MAIN ST, JACKSONVILLE, FL 32202",
                  "dropoffplace": "40 BAY ST, JACKSONVILLE, FL 32207"}]})
    assert trip.status_code == 200, trip.text
    with co["db"].connect() as conn:
        legid, back = [r[0] for r in conn.execute(text("SELECT recordid FROM triplegs WHERE tripid = :t "
                                                       "ORDER BY legnumber"), {"t": trip.json()["recordid"]})]

    def leg():
        with co["db"].connect() as conn:
            return conn.execute(text("SELECT driverid, vehicleid FROM triplegs WHERE recordid = :l"),
                                {"l": legid}).mappings().one()

    # The Assign dialog asks again once a vehicle is chosen: the drivers judged in that vehicle,
    # and no vehicle list - it has been chosen.
    invan = c.get(f"/api/legs/{legid}/candidates?vehicleid={co['vehicle']}", headers=h)
    assert invan.status_code == 200 and invan.json()["vehicles"] == [], invan.text
    assert co["driver"] in {d["driverid"] for d in invan.json()["drivers"]}
    offshift = c.post("/api/dispatch/place", headers=h, json={"legid": legid, "driverid": bea})
    assert offshift.status_code == 409 and "has no vehicle assigned on" in offshift.text, offshift.text
    assert leg()["driverid"] is None
    planned = c.post("/api/dispatch/autoplan", headers=h, json={"day": str(on)})
    assert planned.status_code == 200, planned.text
    item = next(p for p in planned.json()["proposal"] if p["legid"] == legid)
    assert item["driverid"] in (co["driver"], None) and item["driverid"] != bea, item
    assert leg()["driverid"] is None                                                    # nothing saved
    if item["driverid"]:
        assert item["vehicleid"] == co["vehicle"] and item["reasons"][0] == "On shift in AV1", item
        got = c.post("/api/dispatch/autoplan/save", headers=h, json={"items": [
            {"legid": legid, "driverid": item["driverid"], "vehicleid": item["vehicleid"]}]})
        assert got.status_code == 200 and got.json() == {"saved": 1, "refused": []}, got.text
    else:
        assert item["blocked"], item
        placed = c.post("/api/dispatch/place", headers=h,
                        json={"legid": legid, "driverid": co["driver"], "overridereason": "TEST"})
        assert placed.status_code == 200, placed.text
    assert dict(leg()) == {"driverid": co["driver"], "vehicleid": co["vehicle"]}
    # The will-call return is not scheduled until the passenger calls: no driver before then.
    early = c.post("/api/dispatch/place", headers=h,
                   json={"legid": back, "driverid": co["driver"], "overridereason": "TEST"})
    assert early.status_code == 409 and "once the passenger calls" in early.text, early.text
    # Called: it has a time, and goes to the driver in the day's vehicle like any other leg.
    assert c.post(f"/api/legs/{back}/release", headers=h,
                  json={"pickupat": f"{on}T14:00:00"}).status_code == 200
    returned = c.post("/api/dispatch/place", headers=h,
                      json={"legid": back, "driverid": co["driver"], "overridereason": "TEST"})
    assert returned.status_code == 200, returned.text
    with co["db"].connect() as conn:
        assert conn.execute(text("SELECT vehicleid FROM triplegs WHERE recordid = :l"),
                            {"l": back}).scalar() == co["vehicle"]


# 6. Drafts never block; approved rules do; the facts of a trip always do -------------------------

def test_6_a_prohibition_and_an_uncorrected_defect_block_while_their_rules_are_draft():
    """382.501 and 396.11(a)(3) are facts on the record, not interpretations: they refuse a trip
    whether or not a reviewer has approved the rule that states them. Any other draft rule still
    only warns."""
    from app import tripcheck
    def item(code):
        return {"code": code, "name": code, "applies": True, "blocking": True, "status": "failed",
                "legalreview": "draft", "why": "x"}
    got = tripcheck.judge_items([item("DA_PROHIBITION"), item("DVIR"), item("DRIVER_LICENSE_COPY")],
                                None, datetime.now())
    refused = {b["code"] for b in got[0] if b["enforceable"]}
    assert refused == {"DA_PROHIBITION", "DVIR"}, got



def test_6_a_draft_rule_never_blocks_dispatch_and_an_approved_one_does(make):
    from app import dispatch
    co = make()
    on = date.today() + timedelta(days=1)
    when = datetime.combine(on, datetime.min.time()).replace(hour=9)
    trip = {"vehicleid": None, "pickupat": when, "tripdate": on, "brokerid": None, "payer": "private",
            "servicelevel": "ambulatory", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
            "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801", "originplace": "40 BAY ST, JACKSONVILLE, FL 32207"}
    conn = co["db"].connect()
    trans = conn.begin()
    try:
        def mine():
            return next(d for d in dispatch.best(conn, co["acct"], when=when, minutes=60, trip=trip)["drivers"]
                        if d["driverid"] == co["driver"])
        before = mine()
        from app import tripcheck
        judged = lambda: tripcheck.check(conn, co["acct"], co["driver"], proposed=trip, at=when,
                                         record=False)["decision"]
        # B-03: a draft shortfall is not a refusal, so it is not "not qualified" either.
        drafted = judged()
        approved(conn, "DRIVER_LICENSE_COPY")
        after = mine()
        enforced = judged()
    finally:
        trans.rollback()
        conn.close()
    # Said as a note, and nothing has to be accepted for it - not a warning a supervisor signs off.
    assert before["available"] and any("not yet approved" in w for w in before["drafts"]), before
    assert not any("not yet approved" in w for w in before["warnings"]), before
    assert drafted != "notqualified" and enforced == "notqualified", (drafted, enforced)
    assert not after["available"] and after["blocked"], after


def test_6b_an_operational_restriction_applies_while_every_rule_is_a_draft(make):
    from app import dispatch
    co = make()
    when = datetime.combine(date.today() + timedelta(days=3), datetime.min.time()).replace(hour=10)
    with co["db"].connect() as conn:
        got = dispatch.best(conn, co["acct"], when=when, minutes=60, service="wheelchair")
    mine = next(v for v in got["vehicles"] if v["vehicleid"] == co["vehicle"])
    assert not mine["available"] and any("lift" in b.lower() for b in mine["blocked"]), mine


# 7. A decision can be reproduced against the rules and the engine of its day -----------------------

def test_7_a_decision_keeps_the_engine_and_the_exact_rules_it_read(make):
    """Each decision stores the engine version and, for every rule it read, the version and the
    hash of its immutable snapshot. A later change to a rule gives later decisions a new version
    and hash, and leaves the earlier decision as it was."""
    from app import ruleversions, tripcheck
    from app.engine import ENGINE_VERSION
    co = make()
    on = date.today() + timedelta(days=1)
    leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()), "tripdate": on,
           "brokerid": None, "payer": "private", "servicelevel": "ambulatory",
           "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207", "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}
    conn = co["db"].connect()
    trans = conn.begin()
    try:
        def read_of(evaluationid, code):
            return next(r for r in json.loads(conn.execute(
                text("SELECT rulesread FROM tripeligibility WHERE recordid = :i"),
                {"i": evaluationid}).scalar()) if r["code"] == code)
        first = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=True)
        kept = conn.execute(text("SELECT engineversion, rulesread FROM tripeligibility WHERE recordid = :i"),
                            {"i": first["evaluationid"]}).mappings().one()
        one = next(r for r in json.loads(kept["rulesread"]) if r["version"] and r["sha"])
        snap = conn.execute(text("SELECT snapshot FROM compliancerulesversions WHERE rulecode = :c "
                                 "AND version = :v AND accountid IS NULL AND snapshotsha = :h"),
                            {"c": one["code"], "v": one["version"], "h": one["sha"]}).scalar()
        # The rule changes, and its new version is captured as a migration does.
        conn.execute(text("UPDATE compliancerules SET note = CONCAT(COALESCE(note, ''), ' (changed)') "
                          "WHERE code = :c AND accountid IS NULL AND effectiveto IS NULL"), {"c": one["code"]})
        ruleversions.capture(conn, reason="acceptance test")
        second = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=True)
        later, again = read_of(second["evaluationid"], one["code"]), read_of(first["evaluationid"], one["code"])
    finally:
        trans.rollback()
        conn.close()
    assert kept["engineversion"] == ENGINE_VERSION
    assert snap, "the exact rule a decision names can be read back by its hash"
    assert later["version"] == one["version"] + 1 and later["sha"] != one["sha"]
    assert again == one


def test_7b_a_decision_keeps_the_facts_and_evidence_it_was_made_from(make):
    from app import tripcheck
    co = make()
    on = date.today() + timedelta(days=1)
    leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()), "tripdate": on,
           "brokerid": None, "payer": "private", "servicelevel": "ambulatory",
           "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207", "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}
    with co["db"].begin() as conn:
        said = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=True)
        kept = conn.execute(text("SELECT factsread, standingread FROM tripeligibility WHERE recordid = :i"),
                            {"i": said["evaluationid"]}).mappings().one()
    facts, standing = json.loads(kept["factsread"]), json.loads(kept["standingread"])
    assert facts["company.state"] == "FL" and facts["company.medicaidstates"] == ["FL"]
    assert standing and all({"code", "applies", "status"} <= set(s) for s in standing)


# 8. A restricted driving record on an actual trip --------------------------------------------------

@pytest.mark.parametrize("finding,note", [("restricted", "DAYLIGHT DRIVING ONLY"),
                                          ("disqualified", "LICENSE SUSPENDED 2023")])
def test_8_an_approved_georgia_mvr_rule_on_a_georgia_trip(make, finding, note):
    """TripProof cannot judge a trip against a restriction's terms, so it does not claim to: under
    an approved rule a restricted record holds the trip for an owner or admin to accept, with the
    restriction named. A disqualifying record refuses it."""
    from app import tripcheck
    co = make()
    add_line(co, co["payer"], "GA")
    driving_record(co, finding, note)
    on = date.today() + timedelta(days=1)
    leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()).replace(hour=21),
           "tripdate": on, "brokerid": co["payer"], "payer": "broker", "servicelevel": "ambulatory",
           "pickupplace": "12 OAK ST, VALDOSTA, GA 31601", "dropoffplace": "9 ELM ST, MACON, GA 31201",
           "originplace": "12 OAK ST, VALDOSTA, GA 31601"}
    conn = co["db"].connect()
    trans = conn.begin()
    try:
        approved(conn, "GA_NET_MVR")
        said = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=False)
    finally:
        trans.rollback()
        conn.close()
    mvr = lambda found: [x for x in found if x.get("code") == "GA_NET_MVR"]  # noqa: E731
    if finding == "restricted":
        assert not mvr(said["enforceable"]) and not mvr(said["blockers"]), said
        held = mvr(said["holds"])
        assert held and note in (held[0].get("reason") or ""), said["holds"]
        assert not said["eligible"] and said["decision"] in ("needsreview", "notqualified")
    else:
        assert mvr(said["enforceable"]), said


# 9. One company cannot reach another's records ----------------------------------------------------

def test_9_another_company_cannot_read_or_change_these_records(make):
    co, other = make(), make()
    c = co["client"]
    d, v = co["driver"], co["vehicle"]
    lic = c.post(f"/api/drivers/{d}/licenses", headers=co["h"], json={
        "number": f"T{co['tag']}", "state": "FL", "classification": "E", "commercial": False,
        "issued": "2020-01-01", "expires": "2030-01-01", "active": True}).json()["recordid"]
    l1 = credential(co, "FL_LEVEL1", "driver", d, date.today(), provenance="vendor")
    fl = line(co, co["payer"], "FL")
    with co["db"].begin() as conn:
        mvr = f"m-{uuid.uuid4().hex[:12]}"
        conn.execute(text("INSERT INTO drivermvrs (recordid, accountid, driverid, licenseid, receivedon) "
                          "VALUES (:m, :a, :d, :l, NOW())"), {"m": mvr, "a": co["acct"], "d": d, "l": lic})
    calls = [
        ("get", f"/api/drivers/{d}/requirements", None),
        ("get", f"/api/drivers/{d}/licenses", None),
        ("get", f"/api/vehicles/{v}/authorizations", None),
        ("post", f"/api/drivers/{d}/licenses/{lic}/commercial", {"commercial": True}),
        ("post", f"/api/drivers/{d}/authorizations/{fl['recordid']}", {}),
        ("post", f"/api/vehicles/{v}/authorizations/{fl['recordid']}", {"servicefrom": str(date.today())}),
        ("post", f"/api/drivers/{d}/mvrs/{mvr}/reviewed", {"finding": "qualified"}),
        ("put", f"/api/credentials/{l1}/provenance", {"provenance": "fdle"}),
        ("put", f"/api/credentials/{l1}/result", {"result": "eligible"}),
    ]
    for method, url, body in calls:
        r = getattr(c, method)(url, headers=other["h"], **({} if body is None else {"json": body}))
        assert r.status_code in (403, 404), (method, url, r.status_code, r.text)
    with co["db"].connect() as conn:
        assert conn.execute(text("SELECT commercial FROM driverlicenses WHERE recordid = :l"), {"l": lic}).scalar() == 0
        assert not conn.execute(text("SELECT COUNT(*) FROM driverauthorizations WHERE driverid = :d"), {"d": d}).scalar()
        assert not conn.execute(text("SELECT COUNT(*) FROM vehicleauthorizations WHERE vehicleid = :v"), {"v": v}).scalar()
        assert conn.execute(text("SELECT reviewstate FROM drivermvrs WHERE recordid = :m"), {"m": mvr}).scalar() == "pending"
        assert conn.execute(text("SELECT CONCAT(COALESCE(provenance, '-'), '/', COALESCE(result, '-')) "
                                 "FROM credentials WHERE recordid = :c"), {"c": l1}).scalar() == "vendor/-"


# 10. The tests never wipe a database not named for them --------------------------------------------

def test_10_the_test_database_guard():
    from app.dbguard import refuse_unsafe
    assert refuse_unsafe("tripproof_test", "tripproof") is None
    assert refuse_unsafe("tripproof", "tripproof")                 # the live database
    assert refuse_unsafe("tripproof_copy", None)                   # not named for tests
    assert refuse_unsafe("tripproof_test", "tripproof_test")       # the configured live database


def test_8b_only_an_owner_or_admin_can_accept_a_restricted_driver_for_a_trip(make):
    """The hold on an actual leg: a staff login is refused, an owner accepts it with the reason, and
    the acceptance is kept with the assignment."""
    from app.routers import admin
    from app.security import hash_password
    co = make()
    add_line(co, co["payer"], "GA")
    driving_record(co, "restricted", "DAYLIGHT DRIVING ONLY")
    c = co["client"]
    on = date.today() + timedelta(days=2)
    trip = c.post("/api/trips", headers=co["h"], json={
        "passenger": "HOLD TEST", "tripdate": str(on), "payer": "broker", "brokerid": co["payer"],
        "legs": [{"pickupat": f"{on}T10:00:00", "pickupplace": "12 OAK ST, VALDOSTA, GA 31601",
                  "dropoffplace": "9 ELM ST, MACON, GA 31201"}]})
    assert trip.status_code == 200, trip.text
    with co["db"].begin() as conn:
        legid = conn.execute(text("SELECT recordid FROM triplegs WHERE tripid = :t"),
                             {"t": trip.json()["recordid"]}).scalar()
        staff = admin._create_user(conn, co["acct"], f"staff-{co['tag']}@acceptance.test", "Staff",
                                   "staff", None, "America/New_York")
        conn.execute(text("UPDATE users SET passwordhash = :p WHERE recordid = :u"),
                     {"p": hash_password(PASSWORD), "u": staff["recordid"]})
        # The driver is approved for the line, so nothing but the restriction stands in the way.
        conn.execute(text("""INSERT INTO driverauthorizations (recordid, accountid, driverid, contractid,
                                                               approvedon)
                             VALUES (UUID(), :a, :d, :c, NOW())"""),
                     {"a": co["acct"], "d": co["driver"], "c": line(co, co["payer"], "GA")["recordid"]})
        conn.execute(text("UPDATE compliancerules SET legalreview = 'approved' WHERE code = 'GA_NET_MVR' "
                          "AND accountid IS NULL AND effectiveto IS NULL"))
    try:
        mine = next(d for d in c.get(f"/api/legs/{legid}/candidates", headers=co["h"]).json()["drivers"]
                    if d["driverid"] == co["driver"])
        assert mine["available"] and mine["holds"] and "DAYLIGHT DRIVING ONLY" in mine["holds"][0], mine
        body = {"driverid": co["driver"], "vehicleid": None, "overridereason": "DAYTIME PICKUP CONFIRMED"}
        refused = c.post(f"/api/legs/{legid}/assign", headers=login(c, f"staff-{co['tag']}@acceptance.test"),
                         json=body)
        assert refused.status_code == 403 and "owner or admin" in refused.text, refused.text
        assert c.post(f"/api/legs/{legid}/assign", headers=co["h"],
                      json={**body, "overridereason": ""}).status_code == 400
        accepted = c.post(f"/api/legs/{legid}/assign", headers=co["h"], json=body)
        assert accepted.status_code == 200, accepted.text
        with co["db"].connect() as conn:
            kept = conn.execute(text("SELECT override, overridereason, assignedby FROM tripassignments "
                                     "WHERE legid = :l AND endedon IS NULL"), {"l": legid}).mappings().one()
        me = c.get("/api/auth/me", headers=co["h"]).json()
        assert kept["override"] == 1 and kept["overridereason"] == "DAYTIME PICKUP CONFIRMED"
        assert kept["assignedby"] == me["recordid"]
    finally:
        with co["db"].begin() as conn:
            conn.execute(text("UPDATE compliancerules SET legalreview = 'draft' WHERE code = 'GA_NET_MVR' "
                              "AND accountid IS NULL AND effectiveto IS NULL"))
            # An unpriced test trip is not left on the platform's at-risk figures.
            conn.execute(text("UPDATE trips SET deleted = NOW() WHERE recordid = :t"),
                         {"t": trip.json()["recordid"]})


def test_7c_a_decision_replays_from_what_was_kept_after_everything_live_has_changed(make):
    """Recorded, then the rules, the facts and the evidence all change: the live answer moves, the
    replay of the recorded decision does not, and every rule it read is still recoverable."""
    from app import tripcheck
    co = make()
    on = date.today() + timedelta(days=1)
    leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()), "tripdate": on,
           "brokerid": None, "payer": "private", "servicelevel": "ambulatory",
           "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207", "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}
    conn = co["db"].connect()
    trans = conn.begin()
    try:
        first = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=True)
        # Everything live changes: a rule is approved, the company crosses state lines, and the
        # driver is made a CDL operator - different rules now reach them.
        approved(conn, "DRIVER_LICENSE_COPY")
        conn.execute(text("INSERT INTO companyanswers (accountid, code, answer, updated) "
                          "VALUES (:a, 'INTERSTATE', 1, NOW())"), {"a": co["acct"]})
        conn.execute(text("UPDATE drivers SET operation = 'cdlheavy' WHERE recordid = :d"), {"d": co["driver"]})
        live = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=False)
        again = tripcheck.replay(conn, co["acct"], first["evaluationid"])
    finally:
        trans.rollback()
        conn.close()
    assert {b["code"] for b in live["blockers"]} != {b["code"] for b in first["blockers"]}
    assert again["replayable"] and again["sameengine"] and again["rulesrecoverable"], again
    assert again["matches"], again
    assert {b["code"] for b in again["blockers"]} == {b["code"] for b in first["blockers"]
                                                       if b["code"] in {b2["code"] for b2 in again["blockers"]}}



def test_10b_a_test_login_that_can_see_live_data_is_named():
    from app.dbguard import reaches_beyond
    assert reaches_beyond(["information_schema", "tripproof_test"]) == []
    assert reaches_beyond(["information_schema", "tripproof", "tripproof_test"]) == ["tripproof"]



def test_11_a_stage_of_rules_can_be_tried_against_past_decisions_before_it_is_approved(make):
    """Shadow against enforced: recorded decisions judged again with a stage of rules taken as
    approved - nothing live changes, and the rules stay drafts."""
    from app import tripcheck
    co = make()
    on = date.today() + timedelta(days=1)
    leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()), "tripdate": on,
           "brokerid": None, "payer": "private", "servicelevel": "ambulatory",
           "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207", "dropoffplace": "1 MAIN ST, ORLANDO, FL 32801"}
    with co["db"].begin() as conn:
        said = tripcheck.check(conn, co["acct"], co["driver"], proposed=leg, record=True)
        assert not said["enforceable"]                       # every rule a draft
        failing = [b["code"] for b in said["blockers"]]
        assert failing
        trial = tripcheck.what_if(conn, co["acct"], failing[:1])
        none = tripcheck.what_if(conn, co["acct"], ["NO_SUCH_RULE"])
        still = conn.execute(text("SELECT legalreview FROM compliancerules WHERE code = :c AND accountid IS NULL "
                                  "AND effectiveto IS NULL"), {"c": failing[0]}).scalar()
    assert trial["refused"] == 1 and trial["byrule"] == {failing[0]: 1}, trial
    assert none["refused"] == 0
    assert still == "draft"


def test_5q_places_and_passengers_are_kept_to_be_chosen_from(make):
    """Book A Trip chooses the drop-off and the passenger from the company's own lists: added with a
    name, an address and a telephone, upper-cased, and never twice."""
    co = make()
    c, h = co["client"], co["h"]
    for kind in ("places", "passengers"):
        dob = {"dob": "1950-03-04"} if kind == "passengers" else {}
        assert c.post(f"/api/{kind}", headers=h, json={"name": "BAYFRONT", "address": "", **dob}).status_code == 400
        if kind == "passengers":                     # a passenger needs a date of birth
            assert c.post(f"/api/{kind}", headers=h, json={"name": "BAYFRONT HOSPITAL",
                                                           "address": "1 MAIN ST"}).status_code == 400
        where = {"city": "St Petersburg", "state": "FL", "zip": "33701"}
        assert c.post(f"/api/{kind}", headers=h, json={"name": "BAYFRONT HOSPITAL", "address": "701 6TH ST S",
                                                       **dob}).status_code == 400      # no city/state/ZIP
        got = c.post(f"/api/{kind}", headers=h, json={"name": "Bayfront Hospital", "address": "701 6th St S",
                                                     **where, "phone": "727-823-1234", **dob})
        assert got.status_code == 200, got.text
        assert got.json()["name"] == "BAYFRONT HOSPITAL"
        assert got.json()["full"] == "701 6TH ST S, ST PETERSBURG, FL 33701"
        again = c.post(f"/api/{kind}", headers=h, json={"name": "BAYFRONT HOSPITAL", "address": "701 6TH ST S",
                                                       **where, **dob})
        assert again.status_code == 409
        items = c.get(f"/api/{kind}", headers=h).json()["items"]
        assert [(i["name"], i["phone"]) for i in items] == [("BAYFRONT HOSPITAL", "727-823-1234")]


def test_5r_hours_of_operation_set_the_dispatch_day(make):
    """The company's hours, day by day, are kept on the Company page and handed to Dispatch with
    the day: open and close, closed, or not set."""
    co = make()
    c, h = co["client"], co["h"]
    bad = c.put("/api/company", headers=h, json={"hours": {"0": {"open": "08:00", "close": ""}}})
    assert bad.status_code == 400 and "Monday" in bad.text
    assert c.put("/api/company", headers=h, json={"hours": {
        "0": {"open": "07:30", "close": "18:00"}, "6": None}}).status_code == 200
    kept = c.get("/api/company", headers=h).json()["hours"]
    assert kept["0"] == {"open": "07:30", "close": "18:00"} and kept["6"] is None and kept["2"] == "unset"
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    assert c.get(f"/api/shifts?day={monday}", headers=h).json()["hours"] == {"open": "07:30", "close": "18:00"}
    assert c.get(f"/api/shifts?day={monday + timedelta(days=6)}", headers=h).json()["hours"] == {"closed": True}
    assert c.get(f"/api/shifts?day={monday + timedelta(days=2)}", headers=h).json()["hours"] is None


def test_5r_hours_of_operation_set_the_dispatch_day(make):
    """The company's hours, day by day, are kept on the Company page and handed to Dispatch with
    the day: open and close, closed, or not set."""
    co = make()
    c, h = co["client"], co["h"]
    bad = c.put("/api/company", headers=h, json={"hours": {"0": {"open": "08:00", "close": ""}}})
    assert bad.status_code == 400 and "Monday" in bad.text
    assert c.put("/api/company", headers=h, json={"hours": {
        "0": {"open": "07:30", "close": "18:00"}, "6": None}}).status_code == 200
    kept = c.get("/api/company", headers=h).json()["hours"]
    assert kept["0"] == {"open": "07:30", "close": "18:00"} and kept["6"] is None and kept["2"] == "unset"
    monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
    assert c.get(f"/api/shifts?day={monday}", headers=h).json()["hours"] == {"open": "07:30", "close": "18:00"}
    assert c.get(f"/api/shifts?day={monday + timedelta(days=6)}", headers=h).json()["hours"] == {"closed": True}
    assert c.get(f"/api/shifts?day={monday + timedelta(days=2)}", headers=h).json()["hours"] is None
    # And when each driver's phone last reported, for the GPS line under their name on Dispatch.
    assert isinstance(c.get(f"/api/shifts?day={monday}", headers=h).json()["gps"], dict)
    # A vehicle assignment falls within those hours, and none is made on a day the company is closed.
    base = {"driverid": co["driver"], "vehicleid": co["vehicle"]}
    early = c.post("/api/shifts", headers=h, json={**base, "day": str(monday), "startsat": "06:00", "endsat": "12:00"})
    assert early.status_code == 409 and "Monday hours are 7:30 AM to 6:00 PM" in early.text, early.text
    shut = c.post("/api/shifts", headers=h, json={**base, "day": str(monday + timedelta(days=6)),
                                                 "startsat": "08:00", "endsat": "12:00"})
    assert shut.status_code == 409 and "closed on Sundays" in shut.text, shut.text
    inside = c.post("/api/shifts", headers=h, json={**base, "day": str(monday), "startsat": "07:30", "endsat": "18:00"})
    assert inside.status_code == 200, inside.text


def test_5s_an_edit_can_set_a_legs_appointment_time(make):
    """Edit Trip carries the appointment time Book A Trip does, and the change is written down."""
    co = make()
    c, h = co["client"], co["h"]
    on = date.today() + timedelta(days=3)
    trip = c.post("/api/trips", headers=h, json={"passenger": "APPT EDIT", "tripdate": str(on), "legs": [
        {"pickupat": f"{on}T09:00:00", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
         "dropoffplace": "1 MAIN ST, JACKSONVILLE, FL 32202"}]}).json()
    held = c.get(f"/api/trips/{trip['recordid']}", headers=h).json()
    leg = held["legs"][0]
    assert leg["appointmentat"] is None
    got = c.put(f"/api/trips/{trip['recordid']}", headers=h, json={
        "passenger": "APPT EDIT", "servicelevel": held["servicelevel"], "legs": [
            {"legid": leg["recordid"], "pickupat": f"{on}T09:15:00", "appointmentat": f"{on}T10:00:00"}]})
    assert got.status_code == 200, got.text
    after = c.get(f"/api/trips/{trip['recordid']}", headers=h).json()
    assert after["legs"][0]["appointmentat"].startswith(f"{on}T10:00")
    assert any(ch["field"] == "Appointment time" for x in after["changes"] for ch in x["changes"]), after["changes"]


def test_5t_saved_passengers_and_places_are_searched_changed_and_removed(make):
    """The Passengers and Locations screens: a page of the list, searched; an entry put right; an
    entry taken off the list - and gone from what Book A Trip chooses from."""
    co = make()
    c, h = co["client"], co["h"]
    where = {"city": "Tampa", "state": "FL", "zip": "33606"}
    for name in ("ALPHA CLINIC", "BETA HOSPITAL", "GAMMA LAB"):
        assert c.post("/api/places", headers=h, json={"name": name, "address": "1 MAIN ST", **where}).status_code == 200
    page = c.get("/api/places?page=1&pagesize=2&sort=name&dir=desc", headers=h).json()
    assert page["total"] == 3 and [i["name"] for i in page["items"]] == ["GAMMA LAB", "BETA HOSPITAL"]
    found = c.get("/api/places?page=1&q=beta", headers=h).json()
    assert found["total"] == 1
    beta = found["items"][0]["recordid"]
    changed = c.put(f"/api/places/{beta}", headers=h, json={"name": "Beta Hospital East", "address": "2 Main St",
                                                            **where, "phone": "813-555-0100"})
    assert changed.status_code == 200 and changed.json()["full"] == "2 MAIN ST, TAMPA, FL 33606", changed.text
    assert c.delete(f"/api/places/{beta}", headers=h).status_code == 200
    assert "BETA HOSPITAL EAST" not in {i["name"] for i in c.get("/api/places", headers=h).json()["items"]}
    assert c.delete(f"/api/places/{beta}", headers=h).status_code == 404
    # A passenger keeps needing a date of birth when put right.
    p = c.post("/api/passengers", headers=h, json={"name": "PAT", "address": "3 OAK ST", **where, "dob": "1950-01-02"}).json()
    assert c.put(f"/api/passengers/{p['recordid']}", headers=h,
                 json={"name": "PAT", "address": "3 OAK ST", **where}).status_code == 400
    assert c.put(f"/api/passengers/{p['recordid']}", headers=h,
                 json={"name": "PAT SMITH", "address": "3 OAK ST", **where, "dob": "1950-01-02"}).status_code == 200


def test_5u_a_driver_problem_alerts_until_somebody_has_seen_it(make):
    """A problem a driver reports comes up as an alert on every page until the office presses Seen
    (or Deal With It); it stays open on Dispatch until it is resolved."""
    co = make()
    c, h = co["client"], co["h"]
    on = date.today() + timedelta(days=1)
    trip = c.post("/api/trips", headers=h, json={"passenger": "ALERT TEST", "tripdate": str(on), "legs": [
        {"pickupat": f"{on}T09:00:00", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
         "dropoffplace": "1 MAIN ST, JACKSONVILLE, FL 32202"}]}).json()
    with co["db"].begin() as conn:
        legid = conn.execute(text("SELECT recordid FROM triplegs WHERE tripid = :t"), {"t": trip["recordid"]}).scalar()
        conn.execute(text("""INSERT INTO tripissues (recordid, accountid, tripid, legid, driverid, kind, note, raisedon)
                             VALUES (UUID(), :a, :t, :l, :d, 'traffic', 'STUCK ON I-95', UTC_TIMESTAMP())"""),
                     {"a": co["acct"], "t": trip["recordid"], "l": legid, "d": co["driver"]})
    got = c.get("/api/issues/unseen", headers=h).json()
    mine = [i for i in got["items"] if i["legid"] == legid]
    assert len(mine) == 1 and mine[0]["note"] == "STUCK ON I-95" and got["kinds"]["traffic"]
    assert c.post(f"/api/issues/{mine[0]['recordid']}/seen", headers=h).status_code == 200
    assert not [i for i in c.get("/api/issues/unseen", headers=h).json()["items"] if i["legid"] == legid]
    board = c.get("/api/dispatch/board?state=attention&pagesize=200", headers=h).json()
    assert any(i["legid"] == legid and i["issueid"] for i in board["items"])      # still open on Dispatch
