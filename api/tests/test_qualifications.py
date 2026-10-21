###################################################################################################
# The qualification restructure, end to end through the HTTP API: payer lines and the programs they
# decide, fee schedules by payer and state, the driver record, the license class, transit programs,
# and the requirement explanations. Each test is something that broke or changed on 2026-10-21 and
# was put right - here so it cannot come back quietly.
#
# Plus the unit tests that need no database: the migration splitter, and the admin customer model.
###################################################################################################
import re
from datetime import date, timedelta
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
