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
    h = ctx["h"]
    me = client.get("/api/auth/me", headers=h).json()

    # --- vault -------------------------------------------------------------------------------
    driver = client.post("/api/drivers", json={"firstname": "Maria", "lastname": "Lopez", "externalid": "DRV-7"}, headers=h).json()["recordid"]
    vehicle = client.post("/api/vehicles", json={"externalid": "V12", "vin": "1FTBW3XM0LKA00001", "modelyear": 2020}, headers=h).json()["recordid"]
    add_cred(client, ctx, "DRIVER_LICENSE", driver, "2022-01-01", "2030-01-01")
    add_cred(client, ctx, "CPR", driver, "2024-04-02", "2026-04-02")
    add_cred(client, ctx, "FIRST_AID", driver, "2024-04-02", "2028-04-02")
    background = add_cred(client, ctx, "BACKGROUND_CHECK", driver, "2025-06-01",
                          file=("bg-maria.pdf", b"%PDF-1.4 background check result", "application/pdf"))
    for d in ("2026-03-15", "2026-04-01", "2026-05-15"):
        add_cred(client, ctx, "OIG_EXCLUSION", driver, d)
    add_cred(client, ctx, "VEHICLE_INSPECTION", vehicle, "2026-01-10")
    add_cred(client, ctx, "VEHICLE_REGISTRATION", vehicle, "2025-07-01", "2027-06-30")
    add_cred(client, ctx, "VEHICLE_INSURANCE", vehicle, "2026-01-01", "2027-01-01")
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

    # --- exposure ---------------------------------------------------------------------------
    t = trips_by_ext(client, ctx)
    assert t["T1001"]["failures"] is None                       # before CPR lapsed
    assert t["T1002"]["failures"] is None                       # last day of the CPR card
    assert "CPR/AED certification expired 2026-04-02" in t["T1003"]["reasons"]
    assert "CPR/AED certification expired 2026-04-02" in t["T1004"]["reasons"]
    assert "older than 365 days as of 2026-06-01" in t["T1004"]["reasons"]
    assert "PASS" in t["T1005"]["reasons"]     # wheelchair trip, no securement training
    assert t["T1006"]["failures"] > 0                           # stub driver/vehicle, nothing on file
    risk = exposure(client, ctx)
    assert (risk["trips"], float(risk["amount"])) == (4, 175.0)
    assert float(risk["unbilledamount"]) == 175.0
    # Per-driver exposure counts only trips failing on the driver's own credentials, each once.
    mx = client.get(f"/api/drivers/{driver}", headers=h).json()["exposure"]
    assert (mx["trips"], float(mx["amount"])) == (3, 150.0)
    board = {d["name"]: d for d in client.get("/api/dashboard", headers=h).json()["drivers"]}
    assert board["Maria Lopez"]["trips"] == 3

    # --- renewal: a new card, the old one untouched ----------------------------------------------
    add_cred(client, ctx, "CPR", driver, "2026-04-03", "2028-04-03")
    t = trips_by_ext(client, ctx)
    assert t["T1003"]["failures"] is None
    assert "CPR" not in t["T1004"]["reasons"] and "365 days" in t["T1004"]["reasons"]
    risk = exposure(client, ctx)
    assert (risk["trips"], float(risk["amount"])) == (3, 135.0)

    # --- revocation: trips before it stay covered ----------------------------------------------
    r = client.post(f"/api/credentials/{background}/revoke",
                    json={"revokedon": "2026-03-21T09:00:00", "reason": "Disqualifying offense reported"}, headers=h)
    assert r.status_code == 200, r.text
    t = trips_by_ext(client, ctx)
    assert t["T1001"]["failures"] is None                       # 03-20, before the revocation
    assert "revoked 2026-03-21 09:00" in t["T1005"]["reasons"]
    assert "revoked" in t["T1002"]["reasons"]
    risk = exposure(client, ctx)
    assert (risk["trips"], float(risk["amount"])) == (5, 220.0)

    # --- trip detail: saved checks point at the credential that covered the pickup --------------
    d = client.get(f"/api/trips/{t['T1001']['recordid']}", headers=h).json()
    passes = [c for c in d["checks"] if c["code"] == "DRIVER_BACKGROUND_365"]
    assert passes and passes[0]["outcome"] == "pass" and passes[0]["credentialid"] == background

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
        assert f"documents/{background}_bg-maria.pdf" in names
        for line in zf.read("SHA256SUMS").decode().splitlines():
            digest, name = line.split("  ", 1)
            assert hashlib.sha256(zf.read(name)).hexdigest() == digest
        assert zf.read("summary.pdf").startswith(b"%PDF")
        assert b"Jane Doe" in zf.read("trips.csv")

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
