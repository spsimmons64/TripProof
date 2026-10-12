###################################################################################################
# The online driver application: getting in by date of birth + SSN, the ten steps, the adopted
# signature, signing each document, and what a returning applicant is told.
###################################################################################################
import pytest

DOB = "1988-04-12"
SSN = "412-55-9087"


@pytest.fixture(scope="module")
def appl(client, db):
    from sqlalchemy import text
    from app.cli import create_account
    create_account("Apply Test Transport", "owner@applytest.test", "Owner A", "FL", "America/New_York",
                   "correct horse battery")
    with db.begin() as conn:
        acct = conn.execute(text("SELECT recordid, accountnumber FROM accounts WHERE name = 'Apply Test Transport'")).one()
    return {"accountid": acct[0], "number": str(acct[1]), "db": db}


def h(token):
    return {"Authorization": f"Bearer {token}"}


def test_company_page_and_bad_input(client, appl):
    r = client.get(f"/api/driverapply/{appl['number']}")
    assert r.status_code == 200 and r.json()["accountname"] == "Apply Test Transport"
    assert client.get("/api/driverapply/999999").status_code == 404
    # A made-up SSN is refused before anything is stored.
    bad = client.post(f"/api/driverapply/{appl['number']}/start", json={"dob": DOB, "ssn": "666-00-0000"})
    assert bad.status_code == 400


def test_application_end_to_end(client, appl):
    n = appl["number"]
    # First contact: unknown person, so the form asks for a name.
    first = client.post(f"/api/driverapply/{n}/start", json={"dob": DOB, "ssn": SSN}).json()
    assert first == {"state": "new", "needname": True}

    started = client.post(f"/api/driverapply/{n}/start",
                          json={"dob": DOB, "ssn": SSN, "firstname": "Dana", "lastname": "Reed"}).json()
    assert started["state"] == "started" and started["step"] == 1
    token = started["token"]

    # The SSN is never stored in the clear, and the lookup hash is scoped to this account.
    from sqlalchemy import text
    with appl["db"].connect() as conn:
        d = conn.execute(text("SELECT recordid, status, ssnhash FROM drivers WHERE accountid = :a AND lastname = 'Reed'"),
                         {"a": appl["accountid"]}).one()
        assert d[1] == "application" and len(d[2]) == 64
        assert conn.execute(text("SELECT COUNT(*) FROM drivers WHERE ssnhash LIKE '%4125%'")).scalar() == 0
        phirow = conn.execute(text("SELECT payload FROM phi WHERE ownerid = :d"), {"d": d[0]}).scalar()
        assert "9087" not in (phirow or "")

    # Steps 1-3 keep their answers, and step 1 feeds the driver record.
    client.put("/api/driverapply/session/step", headers=h(token), json={
        "step": 1, "answers": {"firstname": "Dana", "lastname": "Reed", "phone": "8135550111",
                               "employment": [{"employer": "Bay Transit", "from": "2023-01", "to": "2025-06"},
                                              {"employer": "Out of work", "from": "2025-06", "to": "2025-08", "gap": True}],
                               "everdenied": True, "deniedreason": "Suspended 2019, unpaid ticket"}})
    r = client.put("/api/driverapply/session/step", headers=h(token), json={
        "step": 2, "answers": {"licensenumber": "R123456789", "licensestate": "FL", "licenseclass": "E"}})
    assert r.status_code == 200
    state = client.get("/api/driverapply/session/state", headers=h(token)).json()
    assert state["data"]["steps"]["1"]["everdenied"] is True
    assert len(state["data"]["steps"]["1"]["employment"]) == 2
    with appl["db"].connect() as conn:
        assert conn.execute(text("SELECT licensenumber FROM drivers WHERE lastname = 'Reed'")).scalar() == "R123456789"

    # A file goes to encrypted storage; the application only remembers which document it is.
    up = client.post("/api/driverapply/session/upload", headers=h(token),
                     files={"file": ("front.png", b"\x89PNG\r\n\x1a\n" + b"pretend pixels", "image/png")}, data={"kind": "license_front"})
    assert up.status_code == 200
    state = client.get("/api/driverapply/session/state", headers=h(token)).json()
    assert state["uploads"]["license_front"]["filename"] == "front.png"

    # Only photographs and PDFs, judged by the bytes rather than what the browser claims.
    bad_type = client.post("/api/driverapply/session/upload", headers=h(token),
                           files={"file": ("notes.txt", b"just text", "text/plain")}, data={"kind": "license_back"})
    assert bad_type.status_code == 415
    spoofed = client.post("/api/driverapply/session/upload", headers=h(token),
                          files={"file": ("shell.png", b"#!/bin/sh\nrm -rf /", "image/png")}, data={"kind": "license_back"})
    assert spoofed.status_code == 415
    real_pdf = client.post("/api/driverapply/session/upload", headers=h(token),
                           files={"file": ("card.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf")}, data={"kind": "license_back"})
    assert real_pdf.status_code == 200

    # Sending the same bytes again is fine: the document already on file is reused.
    again = client.post("/api/driverapply/session/upload", headers=h(token),
                        files={"file": ("card-again.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf")},
                        data={"kind": "medical_certificate"})
    assert again.status_code == 200
    with appl["db"].connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM documents WHERE sha256 = :h"),
                            {"h": __import__("hashlib").sha256(b"%PDF-1.7\n1 0 obj\n").hexdigest()}).scalar() == 1

    # If the stored file has gone but the row remains, sending it again puts the file back.
    from app import storage
    with appl["db"].connect() as conn:
        key = conn.execute(text("SELECT storagekey FROM documents WHERE sha256 = :h"),
                           {"h": __import__("hashlib").sha256(b"%PDF-1.7\n1 0 obj\n").hexdigest()}).scalar()
    __import__("pathlib").Path(storage.settings.storage_path, key).unlink()
    assert client.get("/api/driverapply/session/upload/medical_certificate", headers=h(token)).status_code == 410
    client.post("/api/driverapply/session/upload", headers=h(token),
                files={"file": ("card.pdf", b"%PDF-1.7\n1 0 obj\n", "application/pdf")}, data={"kind": "medical_certificate"})
    assert client.get("/api/driverapply/session/upload/medical_certificate", headers=h(token)).status_code == 200

    # An applicant can read back what they sent, and nothing else.
    got = client.get("/api/driverapply/session/upload/license_back", headers=h(token))
    assert got.status_code == 200 and got.content.startswith(b"%PDF-")
    assert client.get("/api/driverapply/session/upload/i9_document", headers=h(token)).status_code == 404
    assert client.get("/api/driverapply/session/upload/passport", headers=h(token)).status_code == 400

    # No signature yet, so nothing can be signed.
    assert client.post("/api/driverapply/session/sign", headers=h(token), json={"doctype": "I9"}).status_code == 409

    # Adopting a signature re-checks date of birth and SSN.
    wrong = client.post("/api/driverapply/session/signature", headers=h(token),
                        json={"typedname": "Dana Reed", "fontkey": "signature", "dob": DOB, "ssn": "123-45-6789"})
    assert wrong.status_code == 403
    sig = client.post("/api/driverapply/session/signature", headers=h(token),
                      json={"typedname": "Dana Reed", "fontkey": "formal", "dob": DOB, "ssn": SSN})
    assert sig.status_code == 200 and sig.json()["fontkey"] == "formal"
    # Signing again reuses the signature already on file rather than making a second one.
    again = client.post("/api/driverapply/session/signature", headers=h(token), json={"dob": DOB, "ssn": SSN})
    assert again.status_code == 200 and again.json()["recordid"] == sig.json()["recordid"]
    with appl["db"].connect() as conn:
        assert conn.execute(text("""SELECT COUNT(*) FROM signatures s JOIN drivers d ON d.recordid = s.signerid
                                    WHERE d.lastname = 'Reed' AND s.revokedon IS NULL""")).scalar() == 1

    # Every document is signed against the server's own text, and its hash is recorded.
    doc = client.get("/api/driverapply/session/document/I9", headers=h(token)).json()
    assert "perjury" in doc["text"] and doc["version"]
    assert client.get("/api/driverapply/session/document/NOPE", headers=h(token)).status_code == 404

    # Submitting before everything is signed is refused, and says what is missing.
    early = client.post("/api/driverapply/session/submit", headers=h(token))
    assert early.status_code == 400 and "I9" in early.json()["detail"]

    for doctype in ("I9", "W4", "FCRA_SUMMARY", "FCRA_AUTH", "WORKPLACE_POLICY", "DRUG_POLICY", "CLEARINGHOUSE_CONSENT"):
        assert client.post("/api/driverapply/session/sign", headers=h(token), json={"doctype": doctype}).status_code == 200
    with appl["db"].connect() as conn:
        import hashlib
        from app import documents
        stored = conn.execute(text("""SELECT contentsha256 FROM documentsignatures d JOIN drivers dr ON dr.recordid = d.ownerid
                                      WHERE dr.lastname = 'Reed' AND d.doctype = 'DRUG_POLICY'""")).scalar()
        assert stored == hashlib.sha256(documents.driver_document("DRUG_POLICY")["text"].encode()).hexdigest()

    assert client.post("/api/driverapply/session/submit", headers=h(token)).json()["state"] == "submitted"
    assert client.post("/api/driverapply/session/submit", headers=h(token)).status_code == 409
    with appl["db"].connect() as conn:
        assert conn.execute(text("SELECT status FROM drivers WHERE lastname = 'Reed'")).scalar() == "pending"

    # Coming back once it is in: told where it stands, and handed no session.
    again = client.post(f"/api/driverapply/{n}/start", json={"dob": DOB, "ssn": SSN}).json()
    assert again["state"] == "pending" and "token" not in again

    # An active driver is told to call the office.
    with appl["db"].begin() as conn:
        conn.execute(text("UPDATE drivers SET status = 'active' WHERE lastname = 'Reed'"))
    assert client.post(f"/api/driverapply/{n}/start", json={"dob": DOB, "ssn": SSN}).json()["state"] == "active"

    # The same person at another company is a stranger: the hash is scoped per account.
    from app import signatures
    assert signatures.ssn_hash(appl["accountid"], SSN) != signatures.ssn_hash("other-account", SSN)


def test_progress_follows_the_document_steps(client, appl):
    """Signing your way through the documents counts as progress, so returning opens there."""
    n = appl["number"]
    started = client.post(f"/api/driverapply/{n}/start",
                          json={"dob": "1992-02-02", "ssn": "433-21-8890",
                                "firstname": "Wren", "lastname": "Tasker"}).json()
    token = started["token"]
    assert client.put("/api/driverapply/session/progress", headers=h(token), json={"step": 7}).json()["step"] == 7
    # It never goes backwards, and never past the last step.
    assert client.put("/api/driverapply/session/progress", headers=h(token), json={"step": 2}).json()["step"] == 7
    assert client.put("/api/driverapply/session/progress", headers=h(token), json={"step": 99}).json()["step"] == 9
    back = client.post(f"/api/driverapply/{n}/start", json={"dob": "1992-02-02", "ssn": "433-21-8890"}).json()
    assert back["state"] == "resume" and back["step"] == 9


def test_save_to_finish_later_keeps_your_place(client, appl):
    n = appl["number"]
    started = client.post(f"/api/driverapply/{n}/start",
                          json={"dob": "1993-08-02", "ssn": "433-18-7742",
                                "firstname": "Riley", "lastname": "Nash"}).json()
    # Saving to finish later stores the answers but does not move the applicant on a step.
    client.put("/api/driverapply/session/step", headers=h(started["token"]),
               json={"step": 1, "answers": {"city": "Clearwater"}, "advance": False})
    back = client.post(f"/api/driverapply/{n}/start", json={"dob": "1993-08-02", "ssn": "433-18-7742"}).json()
    assert back["state"] == "resume" and back["step"] == 1
    state = client.get("/api/driverapply/session/state", headers=h(back["token"])).json()
    assert state["data"]["steps"]["1"]["city"] == "Clearwater"


def test_only_misses_count_against_the_brake(client, appl):
    """Coming back to a real application never uses up the budget; guessing does."""
    from app.routers import driverapply
    n = appl["number"]
    driverapply._misses.clear()
    started = client.post(f"/api/driverapply/{n}/start",
                          json={"dob": "1990-12-01", "ssn": "433-44-1188",
                                "firstname": "Robin", "lastname": "Ferro"}).json()
    assert started["state"] == "started"
    before = len(driverapply._recent_misses("testclient"))
    for _ in range(30):
        r = client.post(f"/api/driverapply/{n}/start", json={"dob": "1990-12-01", "ssn": "433-44-1188"})
        assert r.status_code == 200 and r.json()["state"] == "resume"
    assert len(driverapply._recent_misses("testclient")) == before      # resuming costs nothing

    # A run of numbers that match nothing does add up, and then the door closes.
    for i in range(driverapply.MISS_LIMIT):
        client.post(f"/api/driverapply/{n}/start", json={"dob": "1961-01-01", "ssn": f"433-44-{2000 + i}"})
    blocked = client.post(f"/api/driverapply/{n}/start", json={"dob": "1961-01-01", "ssn": "433-44-9999"})
    assert blocked.status_code == 429
    driverapply._misses.clear()


def test_resume_where_they_left_off(client, appl):
    n = appl["number"]
    started = client.post(f"/api/driverapply/{n}/start",
                          json={"dob": "1979-11-03", "ssn": "455-12-3344",
                                "firstname": "Sam", "lastname": "Okafor"}).json()
    client.put("/api/driverapply/session/step", headers=h(started["token"]),
               json={"step": 1, "answers": {"city": "Tampa"}})
    back = client.post(f"/api/driverapply/{n}/start", json={"dob": "1979-11-03", "ssn": "455-12-3344"}).json()
    assert back["state"] == "resume" and back["step"] == 2 and back["firstname"] == "Sam"
    state = client.get("/api/driverapply/session/state", headers=h(back["token"])).json()
    assert state["data"]["steps"]["1"]["city"] == "Tampa"
