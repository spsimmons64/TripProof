###################################################################################################
# The qualification restructure, end to end through the HTTP API: payer lines and the programs they
# decide, fee schedules by payer and state, the driver record, the license class, transit programs,
# and the requirement explanations. Each test is something that broke or changed on 2026-10-21 and
# was put right - here so it cannot come back quietly.
#
# Plus the unit tests that need no database: the migration splitter, and the admin customer model.
###################################################################################################
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import text

MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"


# --- no database ------------------------------------------------------------------------------

def test_a_comment_after_a_string_still_ends_the_statement():
    """024 put "-- note" after "'FCRA_FORMS');". Cutting comments only from lines with no quote
    glued that statement to the next, and an empty database could not be built."""
    from app.cli import split_sql
    got = split_sql("UPDATE t SET a = 1 WHERE c IN (\n  'X');   -- a note, with 'quotes'\n"
                    "UPDATE t SET b = '-- not a comment';\n")
    assert got == ["UPDATE t SET a = 1 WHERE c IN (\n  'X')", "UPDATE t SET b = '-- not a comment'"]


def test_every_migration_splits_into_whole_statements():
    from app.cli import split_sql
    glued = []
    for f in sorted(MIGRATIONS.glob("*.sql")):
        for stmt in split_sql(f.read_text()):
            if re.search(r";\s*\n\s*(UPDATE|INSERT|ALTER|CREATE|DELETE|DROP)\b", stmt, re.I):
                glued.append(f.name)
    assert not glued, glued


def test_admin_customer_model_takes_every_profile_field():
    """create_account reads every PROFILE_FIELDS name off the body; dba, usdot and mcnumber were
    missing, and every customer created from the admin side crashed."""
    from app.profiles import PROFILE_FIELDS
    from app.routers.admin import AccountIn
    assert set(PROFILE_FIELDS) <= set(AccountIn.model_fields)


def test_admin_broker_model_keeps_the_address():
    """The admin broker save had no address fields, and the shared writer blanked them."""
    from app.rates import ADDRESS
    from app.routers.admin import PayerIn
    assert set(ADDRESS) <= set(PayerIn.model_fields)


# --- through the API --------------------------------------------------------------------------

def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def q(client, db):
    from app.cli import create_account
    create_account("Qualification Test Transport", "owner@q.test", "Owner Q", "FL",
                   "America/New_York", "correct horse battery")
    h = login(client, "owner@q.test", "correct horse battery")
    me = client.get("/api/auth/me", headers=h).json()
    driver = client.post("/api/drivers", json={"firstname": "Pat", "lastname": "Quinn"},
                         headers=h).json()["recordid"]
    with db.begin() as conn:
        # Past the application, so the office may edit the record.
        conn.execute(text("UPDATE drivers SET status = 'pending' WHERE recordid = :d"), {"d": driver})
    payer = client.post("/api/company/payers", json={"name": "Q BROKER", "category": "broker"},
                        headers=h).json()["recordid"]
    return {"h": h, "acct": me["accountid"], "driver": driver, "payer": payer, "db": db}


def facts(client, q):
    return client.get(f"/api/drivers/{q['driver']}/requirements", headers=q["h"]).json()["facts"]


def item(client, q, name):
    items = client.get(f"/api/drivers/{q['driver']}/requirements", headers=q["h"]).json()["items"]
    return next(i for i in items if i["name"].lower() == name.lower())


def test_driver_save_keeps_the_operating_ticks(client, q):
    """The Dispatch ID default once sent the driver number as a number; the whole save was refused
    and the ticks never stuck."""
    h, d = q["h"], q["driver"]
    r = client.put(f"/api/drivers/{d}", headers=h, json={
        "firstname": "Pat", "lastname": "Quinn", "externalid": "1001", "operation": "cdlheavy"})
    assert r.status_code == 200, r.text
    got = client.get(f"/api/drivers/{d}", headers=h).json()
    assert got["operation"] == "cdlheavy" and got["externalid"] == "1001"
    # A number where text belongs is refused outright, so the screen must send text.
    bad = client.put(f"/api/drivers/{d}", headers=h, json={
        "firstname": "Pat", "lastname": "Quinn", "externalid": 1001, "operation": "cdlheavy"})
    assert bad.status_code == 422


def test_wrong_license_class_says_which_license_and_what_to_do(client, q):
    h, d = q["h"], q["driver"]
    soon = (date.today() + timedelta(days=700)).isoformat()
    client.post(f"/api/drivers/{d}/licenses", headers=h, json={
        "number": "Q1", "state": "FL", "classification": "C", "issued": "2024-01-01",
        "expires": soon, "active": True})
    client.post(f"/api/drivers/{d}/licenses", headers=h, json={
        "number": "Q2", "state": "FL", "classification": "B", "issued": "2024-01-01",
        "expires": soon})
    lic = item(client, q, "Valid driver's license")
    assert lic["status"] == "failed"
    # Names the license, what the work needs, and the way out.
    assert "FL Class C (Q1)" in lic["why"] and "Class A or B" in lic["why"]
    assert "FL Class B (Q2)" in lic["why"] and "Make Active" in lic["why"]


def test_payer_lines_decide_the_programs_and_inactive_stops_them(client, q):
    h, p = q["h"], q["payer"]
    r = client.post("/api/company/operating-profile/contracts", headers=h,
                    json={"payerid": p, "state": "FL"})
    assert r.status_code == 200, r.text
    assert "medicaid" in facts(client, q)["company.programs"]     # a broker carries Medicaid
    # Off at the company's own say, and its line stops counting.
    st = client.put(f"/api/company/payers/{p}/status", headers=h,
                    json={"active": False, "contactname": None, "contactemail": None})
    assert st.status_code == 200, st.text
    assert "medicaid" not in facts(client, q)["company.programs"]
    client.put(f"/api/company/payers/{p}/status", headers=h,
               json={"active": True, "contactname": None, "contactemail": None})
    assert "medicaid" in facts(client, q)["company.programs"]


def test_a_line_carries_only_its_payer_types_programs(client, q):
    bad = client.post("/api/company/operating-profile/contracts", headers=q["h"],
                      json={"payerid": q["payer"], "state": "GA", "program": "facility"})
    assert bad.status_code == 400


def schedule(client, h, name, payertype, amount, **more):
    body = {"name": name, "payertype": payertype, "effectivefrom": more.pop("start", None),
            "rates": [{"ratetype": "base", "name": "BASE", "unit": "trip", "amount": amount}], **more}
    r = client.post("/api/company/rates", headers=h, json=body)
    assert r.status_code == 200, r.text
    return r.json()["recordid"]


def quote(client, h, payer, state, on=None):
    on = on or date.today().isoformat()
    return client.get("/api/dispatch/quote", headers=h, params={
        "servicelevel": "ambulatory", "on": on, "payerid": payer, "state": state}).json()


def test_fee_schedules_are_chosen_by_payer_then_state(client, q):
    h, p = q["h"], q["payer"]
    # A schedule of the payer's own type only.
    flat = schedule(client, h, "Q FLAT", "flatcontract", 10)
    assert client.put(f"/api/company/payers/{p}/schedule", headers=h,
                      json={"scheduleid": flat}).status_code == 400
    # Every payer is paid under one.
    assert client.put(f"/api/company/payers/{p}/schedule", headers=h,
                      json={"scheduleid": None}).status_code == 400

    base = schedule(client, h, "Q BROKER RATES", "broker", 50)
    assert client.put(f"/api/company/payers/{p}/schedule", headers=h,
                      json={"scheduleid": base}).json()["ok"]
    assert quote(client, h, p, "FL")["schedulename"] == "Q BROKER RATES"
    # No line in Georgia: not carried for there, so no price.
    assert quote(client, h, p, "GA")["schedulename"] is None

    # A Georgia line paid differently overrides the payer's own schedule there.
    ga = schedule(client, h, "Q BROKER GEORGIA", "broker", 70)
    r = client.post("/api/company/operating-profile/contracts", headers=h,
                    json={"payerid": p, "state": "GA", "scheduleid": ga})
    assert r.status_code == 200, r.text
    assert quote(client, h, p, "GA")["schedulename"] == "Q BROKER GEORGIA"
    assert quote(client, h, p, "FL")["schedulename"] == "Q BROKER RATES"

    # A replacement takes over from its start; until then the one it replaces prices the day.
    later = (date.today() + timedelta(days=30)).isoformat()
    schedule(client, h, "Q BROKER RATES 2", "broker", 55, start=later, supersedes=base)
    assert quote(client, h, p, "FL")["schedulename"] == "Q BROKER RATES"
    assert quote(client, h, p, "FL", on=later)["schedulename"] == "Q BROKER RATES 2"


def test_transit_programs_reach_drivers_and_vehicles(client, q):
    h, d = q["h"], q["driver"]
    assert client.put("/api/company/operating-profile/transit/FL_1490", headers=h,
                      json={"determination": "covered"}).status_code == 200
    assert facts(client, q)["driver.transit.FL_1490"] is False      # not assigned yet
    assert client.put(f"/api/drivers/{d}/transit-programs", headers=h,
                      json={"codes": ["FL_1490"]}).status_code == 200
    assert facts(client, q)["driver.transit.FL_1490"] is True
    # Under review is unknown, never exempt.
    client.put("/api/company/operating-profile/transit/FL_1490", headers=h,
               json={"determination": "review"})
    assert facts(client, q)["driver.transit.FL_1490"] is None

    vehicle = client.post("/api/vehicles", headers=h, json={"externalid": "QV1"}).json()["recordid"]
    client.put("/api/company/operating-profile/transit/FL_1490", headers=h,
               json={"determination": "covered"})
    from app.facts import vehicle_facts
    with q["db"].connect() as conn:
        assert vehicle_facts(conn, q["acct"], vehicle)["vehicle.transit.FL_1490"] is None
    assert client.put(f"/api/company/operating-profile/vehicles/{vehicle}/transit/FL_1490",
                      headers=h, json={"determination": "covered"}).status_code == 200
    with q["db"].connect() as conn:
        assert vehicle_facts(conn, q["acct"], vehicle)["vehicle.transit.FL_1490"] is True


def test_a_company_medical_standard_folds_the_florida_exam_into_the_certificate(client, q):
    names = lambda: [i["name"].lower() for i in client.get(  # noqa: E731
        f"/api/drivers/{q['driver']}/requirements", headers=q["h"]).json()["items"]]
    with q["db"].begin() as conn:
        conn.execute(text("""INSERT INTO companyanswers (accountid, code, answer) VALUES (:a, 'TRANSIT_MEDICAL_ALT', 0)
                             ON DUPLICATE KEY UPDATE answer = 0"""), {"a": q["acct"]})
    assert "bus transit medical examination" in names()
    with q["db"].begin() as conn:
        conn.execute(text("UPDATE companyanswers SET answer = 1 WHERE accountid = :a AND code = 'TRANSIT_MEDICAL_ALT'"),
                     {"a": q["acct"]})
    assert "bus transit medical examination" not in names()
    # Folded into the certificate's row, as one more source behind it.
    cert = item(client, q, "Medical certificate")
    assert "FL_TRANSIT_MEDICAL" in {s["code"] for s in cert["sources"]}


def test_the_questionnaire_can_be_asked_for(client, q):
    """Its catalog row was retired in 220, and asking for it failed ever since."""
    r = client.post(f"/api/drivers/{q['driver']}/upload-requests", headers=q["h"],
                    json={"code": "PREEMP_DA_QUESTIONNAIRE"})
    assert r.status_code == 200, r.text


def test_a_record_worked_out_live_never_expires(q):
    """An at-fault count or a securement clearance is read afresh from the file each time; given an
    expiry it showed on the Validity-Tracked Documents panel as "Nothing on file"."""
    with q["db"].connect() as conn:
        wrong = conn.execute(text("""SELECT code FROM compliancerules
                                     WHERE effectiveto IS NULL AND evidencekind = 'record'
                                       AND recurrence IN ('days', 'ondocument')""")).scalars().all()
    assert not wrong, wrong


def test_a_document_signed_on_request_is_one_line_of_activity(client, q):
    """It is written to the log when signed and is also among the signatures; both were shown, and
    with the code for a name - "The PREV7_ONDUTY was signed by"."""
    with q["db"].begin() as conn:
        conn.execute(text("""INSERT INTO signatures (recordid, accountid, signertype, signername,
                                                     typedname, verifiedby)
                             VALUES ('sig-act-1', :a, 'driver', 'PAT QUINN', 'PAT QUINN', 'dob_ssn')"""),
                     {"a": q["acct"]})
        conn.execute(text("""INSERT INTO documentsignatures (recordid, accountid, signatureid, doctype,
                                                             ownertype, ownerid, contentsha256, signedon)
                             VALUES ('ds-act-1', :a, 'sig-act-1', 'PREV7_ONDUTY', 'driver', :d,
                                     REPEAT('0', 64), NOW())"""),
                     {"a": q["acct"], "d": q["driver"]})
        conn.execute(text("""INSERT INTO activitylog (recordid, action, accountid, entitytype, entityid,
                                                      detail, added)
                             VALUES ('log-act-1', 'signed-on-request', :a, 'driver', :d,
                                     '{"doctype": "PREV7_ONDUTY"}', NOW())"""),
                     {"a": q["acct"], "d": q["driver"]})
    events = client.get(f"/api/drivers/{q['driver']}/application/activity",
                        headers=q["h"]).json()["events"]
    signed = [e["what"] for e in events if "signed" in e["what"].lower()]
    assert len(signed) == 1, signed
    assert "PREV7" not in signed[0] and "On-Duty" in signed[0], signed


def test_a_trip_is_held_to_both_states_and_is_interstate_when_it_crosses(q):
    """Only the pickup was read: a Georgia pickup for a Florida doctor was judged as a Georgia trip
    within Georgia, and Florida's rules and the federal reach of an interstate trip were lost."""
    from app import facts as factset, tripcheck
    assert tripcheck.trip_states({"pickupplace": "12 OAK ST, VALDOSTA, GA 31601",
                                  "dropoffplace": "40 BAY ST, JACKSONVILLE, FL 32207"}) == ["GA", "FL"]
    assert tripcheck.trip_states({"pickupplace": "12 OAK ST, VALDOSTA, GA 31601",
                                  "dropoffplace": "9 ELM ST, MACON, GA 31201"}) == ["GA"]
    assert tripcheck.trip_states({"pickupplace": "SOMEWHERE", "dropoffplace": None}) == []
    with q["db"].connect() as conn:
        crossing = factset.assemble(conn, q["acct"], q["driver"], states=["GA", "FL"])["facts"]
        within = factset.assemble(conn, q["acct"], q["driver"], states=["GA"])["facts"]
    assert crossing["company.operatingstates"] == ["GA", "FL"]
    assert crossing["operation.interstate"] is True
    assert crossing["reach.authority"] is True
    assert within["company.operatingstates"] == ["GA"]
    assert within.get("operation.interstate") is not True


def test_a_payer_line_is_matched_by_the_state_the_trip_begins_in(client, q):
    """A payer with only a Florida line was matched to it for a Georgia pickup, and the trip was
    checked against the Florida contract. Now it is refused at booking and blocked at the check."""
    from app import tripcheck
    h = q["h"]
    p = client.post("/api/company/payers", json={"name": "Q LINE BROKER", "category": "broker"},
                    headers=h).json()["recordid"]
    assert client.post("/api/company/operating-profile/contracts", headers=h,
                       json={"payerid": p, "state": "FL"}).status_code == 200
    on = date.today() + timedelta(days=1)
    trip = {"passenger": "Q PASSENGER", "tripdate": on.isoformat(), "payer": "broker",
            "brokerid": p, "legs": [{"pickupat": f"{on}T09:00:00",
                                     "pickupplace": "12 OAK ST, VALDOSTA, GA 31601",
                                     "dropoffplace": "40 BAY ST, JACKSONVILLE, FL 32207"}]}
    refused = client.post("/api/trips", headers=h, json=trip)
    assert refused.status_code == 400 and "not set up for GA" in refused.text, refused.text
    # Begun in Florida, the same payer is carried for - the return into Georgia included.
    trip["legs"] = [{"pickupat": f"{on}T09:00:00", "pickupplace": "40 BAY ST, JACKSONVILLE, FL 32207",
                     "dropoffplace": "12 OAK ST, VALDOSTA, GA 31601"}]
    assert client.post("/api/trips", headers=h, json=trip).status_code == 200
    with q["db"].connect() as conn:
        leg = {"vehicleid": None, "pickupat": datetime.combine(on, datetime.min.time()),
               "tripdate": on, "brokerid": p, "payer": "broker", "servicelevel": "ambulatory",
               "pickupplace": "12 OAK ST, VALDOSTA, GA 31601",
               "dropoffplace": "40 BAY ST, JACKSONVILLE, FL 32207"}
        said = tripcheck.check(conn, q["acct"], q["driver"], proposed=leg, record=False)
    assert any(b["code"] == "PAYERLINE" for b in said["blockers"]), said["blockers"]
    assert said["states"] == ["GA", "FL"]
    # The booking screen's suggestion is put to the same check.
    got = client.get("/api/trips/suggest", headers=h, params={
        "when": f"{on}T09:00:00", "payerid": p, "payer": "broker",
        "pickupplace": leg["pickupplace"], "dropoffplace": leg["dropoffplace"]})
    assert got.status_code == 200, got.text


def test_six_months_is_six_calendar_months():
    """DCH 910.2 says six months; 183 days lands on a different date."""
    from app import rules
    six = {"recurrence": "months", "recurrencemonths": 6}
    assert rules.renewed(six, date(2026, 1, 15)) == date(2026, 7, 15)
    assert rules.renewed(six, date(2026, 8, 31)) == date(2027, 2, 28)
    assert rules.renewed({"recurrence": "days", "recurrencedays": 10}, date(2026, 1, 1)) == date(2026, 1, 11)
    assert rules.renewed({"recurrence": "once"}, date(2026, 1, 1)) is None


def test_the_federal_age_does_not_reach_a_florida_intrastate_driver(q):
    """F.S. 316.302(2)(a) excuses the Florida intrastate driver the federal twenty-one, and (4)
    sets eighteen; DRIVER_AGE once demanded twenty-one of them."""
    from app import facts as factset
    with q["db"].connect() as conn:
        f = factset.assemble(conn, q["acct"], q["driver"], states=["GA", "FL"])["facts"]
        rules_ = {r["code"]: json.loads(r["applieswhen"]) for r in conn.execute(text(
            "SELECT code, applieswhen FROM compliancerules WHERE effectiveto IS NULL AND accountid IS NULL "
            "AND code IN ('DRIVER_AGE', 'FL_INTRASTATE_AGE18')")).mappings()}
    assert rules_["DRIVER_AGE"] == {"fact": "reach.part391interstate", "is": True}
    assert "FL_INTRASTATE_AGE18" in rules_
    # Crossing a state line, Part 391 reaches a CMV driver by the federal rules themselves.
    assert f["reach.part391interstate"] == f["driver.cmv"]


def test_a_typed_expiry_cannot_outlast_the_rules_interval():
    """A Georgia inspection filed as good for a year still lapses six months after it was done;
    the six months never showed because the typed date won."""
    from app import rules
    six = {"recurrence": "months", "recurrencemonths": 6}
    filed = {"effectiveon": date(2026, 10, 2), "expireson": date(2027, 10, 2)}
    assert rules.horizon(six, filed) == date(2027, 4, 2)
    # An earlier date on the record still wins.
    assert rules.horizon(six, {**filed, "expireson": date(2027, 1, 1)}) == date(2027, 1, 1)
    # A rule with no interval keeps the record's own date.
    assert rules.horizon({"recurrence": "ondocument"}, filed) == date(2027, 10, 2)


def test_years_are_counted_in_calendar_months(q):
    """A two-year medical printed good through 09/30/2028 lapsed on 09/29 - 730 days across a leap
    year. Every yearly and monthly interval is now calendar months."""
    from app import mvr, rules
    with q["db"].connect() as conn:
        left = conn.execute(text("""SELECT code, recurrencedays FROM compliancerules
                                    WHERE accountid IS NULL AND effectiveto IS NULL
                                      AND recurrence = 'days' AND recurrencedays <> 3""")).all()
        medical = conn.execute(text("""SELECT recurrence, recurrencedays, recurrencemonths FROM compliancerules
                                       WHERE code = 'FL_TRANSIT_MEDICAL' AND accountid IS NULL
                                         AND effectiveto IS NULL""")).mappings().one()
    assert not left, left
    assert rules.horizon(dict(medical), {"effectiveon": date(2026, 9, 30),
                                         "expireson": date(2028, 9, 30)}) == date(2028, 9, 30)
    yearly = mvr.horizon({"recurrence": "months", "recurrencemonths": 12})
    assert yearly(date(2027, 2, 28)) == date(2028, 2, 28)
    assert mvr.horizon({"recurrence": "once"}) is None


def test_second_audit_corrections(q):
    """The signed Clearinghouse consent lasts the employment, so it is asked once per hire; and a
    Class C license stands in for a road test only where the work calls for a CDL."""
    with q["db"].connect() as conn:
        got = {r["code"]: r for r in conn.execute(text(
            "SELECT code, recurrence, alternatewhen FROM compliancerules WHERE accountid IS NULL "
            "AND effectiveto IS NULL AND code IN ('CLEARINGHOUSE_CONSENT', 'ROAD_TEST')")).mappings()}
    assert got["CLEARINGHOUSE_CONSENT"]["recurrence"] == "perhire"
    assert {"fact": "driver.cdl", "is": True} in json.loads(got["ROAD_TEST"]["alternatewhen"])["all"]


def test_a_programs_hard_stop_does_not_grey_out_a_driver_for_every_trip():
    """The dispatch list's 'may they drive at all' read every hard stop, a Georgia Medicaid one
    included, and so refused a private pay run over a Medicaid shortfall."""
    from app import rules
    item = {"code": "X", "status": "failed", "applies": True, "gate": "hardstop",
            "sources": [{"code": "GA_ONLY", "program": "medicaid", "status": "failed", "applies": True}]}
    assert rules.for_program(item, None) is None
    item["sources"].append({"code": "ALL", "program": None, "status": "satisfied", "applies": True})
    assert rules.for_program(item, None)["status"] == "satisfied"


def test_a_license_says_whether_it_is_commercial(client, q):
    """The class letter cannot say CDL - Georgia's ordinary license is a Class C - so the license
    carries the answer, and a CDL driver on a license recorded as not commercial is on the wrong one."""
    from app import facts as factset, rules
    h, d = q["h"], q["driver"]
    r = client.post(f"/api/drivers/{d}/licenses", headers=h, json={
        "number": "Q1234567", "state": "GA", "classification": "C", "commercial": False,
        "issued": "2024-01-01", "expires": "2030-01-01", "active": True})
    assert r.status_code == 200, r.text
    lic = next(l for l in r.json()["licenses"] if l["number"] == "Q1234567")
    assert lic["commercial"] in (0, False)
    with q["db"].connect() as conn:
        assert factset.assemble(conn, q["acct"], d)["facts"]["driver.licensecommercial"] is False
    assert rules._license_verdict({"active": 1, "classification": "C", "commercial": 0},
                                  {"driver.cdl": True}) == "wrongclass"
    assert rules._license_verdict({"active": 1, "classification": "C", "commercial": None},
                                  {"driver.cdl": True}) == "qualified"
    said = client.post(f"/api/drivers/{d}/licenses/{lic['recordid']}/commercial", headers=h,
                       json={"commercial": True})
    assert said.status_code == 200, said.text
    with q["db"].connect() as conn:
        assert factset.assemble(conn, q["acct"], d)["facts"]["driver.licensecommercial"] is True


def test_georgia_medicaid_takes_a_georgia_or_home_border_state_license(q):
    """DCH 914.2.1: a Georgia license, or one from the bordering state the driver lives in."""
    from app import rules
    with q["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET state = 'FL' WHERE recordid = :d"), {"d": q["driver"]})
        ga = rules._georgia_license(conn, q["acct"], q["driver"], {"state": "GA"})
        fl = rules._georgia_license(conn, q["acct"], q["driver"], {"state": "FL"})
        al = rules._georgia_license(conn, q["acct"], q["driver"], {"state": "AL"})
        tx = rules._georgia_license(conn, q["acct"], q["driver"], {"state": "TX"})
        conn.execute(text("UPDATE drivers SET state = NULL WHERE recordid = :d"), {"d": q["driver"]})
        unknown = rules._georgia_license(conn, q["acct"], q["driver"], {"state": "FL"})
    assert (ga, fl, al, tx, unknown) == ("qualified", "qualified", "notgeorgia", "notgeorgia",
                                         "residenceunknown")


def test_a_bus_transit_vehicle_is_inspected_before_it_goes_out_each_day(q):
    """A week-old inspection report satisfied the Florida daily pre-trip check. The trip now asks
    for today's pre-trip check by this driver, and a defect nobody has certified holds the vehicle."""
    from app.routers import driverapp
    driver = {"accountid": q["acct"], "recordid": q["driver"]}
    with q["db"].begin() as conn:
        vehicle = conn.execute(text("SELECT recordid FROM vehicles WHERE accountid = :a AND externalid = 'QV1'"),
                               {"a": q["acct"]}).scalar()
        assert vehicle, "made by test_transit_programs_reach_drivers_and_vehicles"
        today = driverapp._today(conn, q["acct"])
        conn.execute(text("""INSERT INTO vehicledvirs (recordid, accountid, vehicleid, driverid, reportedon,
                                                       kind, defects)
                             VALUES ('dvir-old', :a, :v, :d, :on, 'pretrip', 0)"""),
                     {"a": q["acct"], "v": vehicle, "d": q["driver"], "on": today - timedelta(days=7)})
        held = driverapp._before_setting_off(conn, driver, vehicle, {})
        assert held and held["kind"] == "pretrip" and held["enforced"] is False, held
        conn.execute(text("""INSERT INTO vehicledvirs (recordid, accountid, vehicleid, driverid, reportedon,
                                                       kind, defects)
                             VALUES ('dvir-today', :a, :v, :d, :on, 'pretrip', 0)"""),
                     {"a": q["acct"], "v": vehicle, "d": q["driver"], "on": today})
        assert driverapp._before_setting_off(conn, driver, vehicle, {}) is None
        conn.execute(text("""INSERT INTO vehicledvirs (recordid, accountid, vehicleid, driverid, reportedon,
                                                       kind, defects, defectnote)
                             VALUES ('dvir-bad', :a, :v, :d, :on, 'posttrip', 1, 'BRAKES')"""),
                     {"a": q["acct"], "v": vehicle, "d": q["driver"], "on": today})
        assert driverapp._before_setting_off(conn, driver, vehicle, {})["kind"] == "defect"


def test_a_states_medicaid_rules_follow_its_medicaid_payer_lines(client, q):
    """A Florida Medicaid provider that drives into Georgia, with no Georgia Medicaid line, was held
    to every Georgia NEMT rule because Georgia was an operating state."""
    from app import rules
    with q["db"].connect() as conn:
        lines = conn.execute(text("""SELECT DISTINCT state FROM companycontracts
                                     WHERE accountid = :a AND status = 'active' AND program = 'medicaid'"""),
                             {"a": q["acct"]}).scalars().all()
        conditions = {json.dumps(json.loads(r)) for r in conn.execute(text(
            "SELECT applieswhen FROM compliancerules WHERE accountid IS NULL AND effectiveto IS NULL "
            "AND code LIKE 'GA\\_NET\\_%' AND applieswhen LIKE '%medicaid%'")).scalars()}
    assert facts(client, q)["company.medicaidstates"] == sorted(lines)
    assert conditions == {json.dumps({"fact": "company.medicaidstates", "has": "GA"})}, conditions
    ga = {"fact": "company.medicaidstates", "has": "GA"}
    floridian = {"company.state": "FL", "company.operatingstates": ["FL", "GA"],
                 "company.medicaid": True, "company.medicaidstates": ["FL"]}
    assert rules.applies(ga, floridian) is False
    assert rules.applies(ga, {**floridian, "company.medicaidstates": ["FL", "GA"]}) is True


def test_vehicle_rules_carry_their_program_and_adoption(q):
    """A vehicle rule offered for adoption reached every vehicle, and a Medicaid-only vehicle rule
    could stop a private pay trip."""
    from app import facts as factset, rules
    with q["db"].connect() as conn:
        vehicle = conn.execute(text("SELECT recordid FROM vehicles WHERE accountid = :a AND externalid = 'QV1'"),
                               {"a": q["acct"]}).scalar()
        got = {v["code"]: v for v in rules.for_vehicle(
            conn, q["acct"], vehicle, factset.assemble(conn, q["acct"], vehicleid=vehicle)["facts"])}
    assert got["LIFT_LOAD_TEST"]["status"] == "notapplicable"
    assert got["GA_NET_VEHICLE_INSPECTION"]["program"] == "medicaid"


def test_georgia_training_is_owed_before_driving(q):
    """DCH 916.1 says before driving; 916.2's 90 days was being granted to every new driver."""
    with q["db"].connect() as conn:
        got = conn.execute(text("""SELECT code, duestage, duedays FROM compliancerules
                                   WHERE accountid IS NULL AND effectiveto IS NULL
                                     AND code IN ('GA_NET_DRIVER_TRAINING', 'GA_NET_FIRST_AID',
                                                  'GA_NET_SPILL_KIT', 'GA_NET_PASSENGER_ASSIST',
                                                  'GA_NET_SAFETY_SENSITIVITY')""")).mappings().all()
    assert len(got) == 5 and all(r["duestage"] == "predrive" and r["duedays"] is None for r in got), got
