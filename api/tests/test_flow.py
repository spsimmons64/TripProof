###################################################################################################
# End to end through the HTTP API: vault -> trip import -> exposure -> renewal -> revocation ->
# audit packet, plus the guarantees that matter for HIPAA (PHI only ciphertext at rest, access
# logged, log append-only) and tenancy (another account sees nothing).
###################################################################################################
import hashlib
import io
import zipfile

import pytest
from sqlalchemy import text

CSV = b"""Trip #,Date of Service,Pickup Time,Driver ID,Driver,Vehicle,Payer,Level of Service,Billed Amount,Member Name,Medicaid ID,Pickup Address,Dropoff Address,Signature,GPS
T1001,03/20/2026,9:15 AM,DRV-7,Maria Lopez,V12,ModivCare,AMB,$45.00,Jane Doe,123456789,1 Main St Tampa,2 Clinic Rd,Y,Y
T1002,04/02/2026,3:00 PM,DRV-7,Maria Lopez,V12,ModivCare,AMB,$45.00,Jane Doe,123456789,1 Main St Tampa,2 Clinic Rd,Y,Y
T1003,04/03/2026,8:00 AM,DRV-7,Maria Lopez,V12,ModivCare,AMB,$40.00,John Roe,987654321,9 Bay Dr,2 Clinic Rd,Y,N
T1004,06/01/2026,8:00 AM,DRV-7,Maria Lopez,V12,ModivCare,AMB,$50.00,John Roe,987654321,9 Bay Dr,2 Clinic Rd,Y,Y
T1005,03/21/2026,10:00 AM,DRV-7,Maria Lopez,V12,ModivCare,WC,$60.00,Ann Poe,555000111,4 Palm Ave,7 Dialysis Way,Y,Y
T1006,03/22/2026,11:00 AM,,Sam Stub,V99,MTM,AMB,$25.00,Ann Poe,555000111,4 Palm Ave,7 Dialysis Way,N,N
"""


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def ctx(client, db):
    from app.cli import create_account
    create_account("Bay Test Transport", "owner@a.test", "Owner A", "FL", "America/New_York", "correct horse battery")
    create_account("Other Co", "owner@b.test", "Owner B", "FL", "America/New_York", "correct horse battery")
    h = login(client, "owner@a.test", "correct horse battery")
    hb = login(client, "owner@b.test", "correct horse battery")
    types = {t["code"]: t["recordid"] for t in client.get("/api/credentialtypes", headers=h).json()}
    return {"h": h, "hb": hb, "types": types, "db": db}


def add_cred(client, ctx, code, subjectid, issued, expires=None, file=None):
    data = {"credentialtypeid": ctx["types"][code], "subjectid": subjectid, "issuedon": issued}
    if expires:
        data["expireson"] = expires
    files = {"file": file} if file else None
    r = client.post("/api/credentials", data=data, files=files, headers=ctx["h"])
    assert r.status_code == 200, r.text
    return r.json()["recordid"]


def trips_by_ext(client, ctx):
    items = client.get("/api/trips", params={"pagesize": 500}, headers=ctx["h"]).json()["items"]
    return {t["externalid"]: t for t in items}


def exposure(client, ctx):
    return client.get("/api/dashboard", headers=ctx["h"]).json()["risk"]


def test_full_flow(client, ctx):
    """Imported trips are judged by the trip check an assignment goes through (evaluator 2.0)."""
    h = ctx["h"]
    me = client.get("/api/auth/me", headers=h).json()

    # --- vault -------------------------------------------------------------------------------
    driver = client.post("/api/drivers", json={"firstname": "Maria", "lastname": "Lopez", "externalid": "DRV-7"}, headers=h).json()["recordid"]
    vehicle = client.post("/api/vehicles", json={"externalid": "V12", "vin": "1FTBW3XM0LKA00001", "modelyear": 2020}, headers=h).json()["recordid"]
    add_cred(client, ctx, "CPR", driver, "2024-04-02", "2026-04-02")
    add_cred(client, ctx, "VEHICLE_REGISTRATION", vehicle, "2025-07-01", "2027-06-30")
    add_cred(client, ctx, "AUTO_LIABILITY_COI", me["accountid"], "2026-01-01", "2027-01-01")

    # --- stage: headers are recognised, preview says what commit will do ----------------------
    r = client.post("/api/imports", files={"file": ("export.csv", CSV, "text/csv")}, headers=h)
    assert r.status_code == 200, r.text
    staged = r.json()
    assert staged["mapping"]["tripid"] == "Trip #"
    assert staged["mapping"]["pickupat"] == "Pickup Time"
    assert staged["mapping"]["tripdate"] == "Date of Service"
    assert staged["summary"]["tripcount"] == 6
    assert staged["summary"]["newdrivers"] == ["Sam Stub"]
    assert staged["summary"]["newvehicles"] == ["V99"]
    assert staged["errors"] == []

    r = client.post(f"/api/imports/{staged['recordid']}/accept", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["trips"] == 6 and r.json()["driverscreated"] == 1 and r.json()["vehiclescreated"] == 1

    # The same bytes cannot be imported twice.
    assert client.post("/api/imports", files={"file": ("again.csv", CSV, "text/csv")}, headers=h).status_code == 409

    # --- exposure: nobody on these trips has been hired -----------------------------------------
    t = trips_by_ext(client, ctx)
    for ext in ("T1001", "T1002", "T1003", "T1004", "T1005", "T1006"):
        assert t[ext]["failures"] and "not been hired" in t[ext]["reasons"], ext
    risk = exposure(client, ctx)
    assert (risk["trips"], float(risk["amount"])) == (6, 265.0)
    mx = client.get(f"/api/drivers/{driver}", headers=h).json()["exposure"]
    assert (mx["trips"], float(mx["amount"])) == (5, 240.0)

    # --- hired: the trips are now held to the driver's requirements -------------------------------
    with ctx["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET status = 'hired' WHERE recordid = :d"), {"d": driver})
    run = client.post("/api/evaluate", headers=h)
    assert run.status_code == 200, run.text
    t = trips_by_ext(client, ctx)
    assert "not been hired" not in (t["T1001"]["reasons"] or "")
    assert t["T1001"]["failures"]                                # her file is far from complete
    assert "not been hired" in t["T1006"]["reasons"]             # the stub driver still is not
    # A wheelchair trip asks for securement training on top.
    assert "wheelchair securement" in t["T1005"]["reasons"].lower()

    # --- trip detail: each check names the rule that judged it -----------------------------------
    d = client.get(f"/api/trips/{t['T1001']['recordid']}", headers=h).json()
    assert d["run"]["engineversion"] == "2.0"
    failed = [c for c in d["checks"] if c["outcome"] == "fail"]
    assert failed and all(c["code"] and c["description"] for c in failed)
    with ctx["db"].connect() as conn:
        known = {r[0] for r in conn.execute(text("SELECT code FROM compliancerules"))}
    assert any(c["code"] in known and c["version"] for c in failed)

    # --- audit packet --------------------------------------------------------------------------
    audit = client.post("/api/audits", json={"requester": "ModivCare Program Integrity", "reference": "PI-2026-044",
                                             "receivedon": "2026-09-15"}, headers=h).json()["recordid"]
    r = client.post("/api/packets", json={"trips": "T1001-T1003, T1004\nT9999", "auditrequestid": audit}, headers=h)
    assert r.status_code == 200, r.text
    packet = r.json()
    assert packet["tripcount"] == 4 and packet["notfound"] == ["T9999"]
    z = client.get(f"/api/packets/{packet['recordid']}/download", headers=h)
    assert z.status_code == 200
    assert hashlib.sha256(z.content).hexdigest() == packet["sha256"]
    with zipfile.ZipFile(io.BytesIO(z.content)) as zf:
        names = zf.namelist()
        assert {"summary.pdf", "trips.csv", "checks.json", "rules.json", "SHA256SUMS"} <= set(names)
        for line in zf.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest
        assert zf.read("summary.pdf").startswith(b"%PDF")
        assert b"Jane Doe" in zf.read("trips.csv")
        # The rules the run read are named by version, so the packet can be explained later.
        assert b'"engine": "tripcheck"' in zf.read("rules.json")

    # --- PHI: ciphertext at rest, reads logged --------------------------------------------------
    with ctx["db"].connect() as conn:
        dump = " ".join(str(v) for tbl in ("trips", "triplegs", "phi", "importbatches")
                        for r in conn.execute(text(f"SELECT * FROM {tbl}")) for v in r)
        assert "Jane Doe" not in dump and "123456789" not in dump and "Main St" not in dump
    p = client.get(f"/api/trips/{t['T1001']['recordid']}/phi", headers=h).json()
    assert p["member"]["membername"] == "Jane Doe"
    with ctx["db"].connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM activitylog WHERE entitytype = 'trip' AND action = 'view' AND phi = 1")).scalar()
        assert n == 1
    with pytest.raises(Exception, match="append-only"):
        with ctx["db"].begin() as conn:
            conn.execute(text("DELETE FROM activitylog"))

    # --- tenancy -----------------------------------------------------------------------------------
    hb = ctx["hb"]
    assert client.get(f"/api/trips/{t['T1001']['recordid']}", headers=hb).status_code == 404
    assert client.get(f"/api/trips/{t['T1001']['recordid']}/phi", headers=hb).status_code == 404
    assert client.get(f"/api/drivers/{driver}", headers=hb).status_code == 404
    assert client.get(f"/api/packets/{packet['recordid']}/download", headers=hb).status_code == 404
    assert client.get("/api/trips", headers=hb).json()["total"] == 0
    assert client.post("/api/credentials", data={"credentialtypeid": ctx["types"]["CPR"], "subjectid": driver,
                                                 "issuedon": "2026-01-01"}, headers=hb).status_code == 404


def test_rejects_bad_login(client, ctx):
    assert client.post("/api/auth/login", json={"email": "owner@a.test", "password": "nope"}).status_code == 401
    assert client.get("/api/dashboard").status_code == 401
