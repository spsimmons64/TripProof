"""The requirements importer: a file in the published format becomes engine rules, and nothing it
cannot evaluate gets in unreported."""
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = Path(__file__).parent / "fixtures" / "requirements-example.json"


def test_the_importer_uses_the_published_schema():
    """The schema the importer checks against is the one handed to whoever prepares a file."""
    from app import catalogimport
    published = ROOT / "docs" / "requirements-format" / "requirements.schema.json"
    if not published.exists():
        pytest.skip("docs not present in this checkout")
    assert json.loads(catalogimport.SCHEMA.read_text()) == json.loads(published.read_text())


def test_the_example_file_translates_and_a_broken_one_is_refused(db, tmp_path):
    from app import catalogimport
    with db.connect() as conn:
        report = catalogimport.run_import(conn, [str(EXAMPLE)], verify=False)
    assert report["totals"]["requirements"] == 2 and report["totals"]["refused"] == 0
    rules = {t["id"]: t["rule"] for t in report["ready"] + report["waiting"]}
    lic, ada = rules["MED-DRV-001"], rules["FED-DRV-001"]
    assert lic["authoritycategory"] == "MEDICAID" and lic["evidencesource"] == "license"
    assert lic["program"] == "medicaid" and lic["gate"] == "hardstop" and lic["legalreview"] == "draft"
    assert ada["authoritycategory"] == "FEDERAL_NEMT" and ada["evidencesource"] == "credential:PASSENGER_ASSISTANCE"
    # A federal motor carrier citation is the DOT & CDL add-on whatever the file calls it.
    doc = json.loads(EXAMPLE.read_text())
    doc["requirements"][1]["citation"] = "49 CFR 391.11(b)(1)"
    doc["requirements"][1]["id"] = "FED-DRV-002"
    moved = tmp_path / "moved.json"
    moved.write_text(json.dumps(doc))
    with db.connect() as conn:
        again = catalogimport.run_import(conn, [str(moved)], verify=False)
    assert {t["id"]: t["rule"] for t in again["ready"] + again["waiting"]}["FED-DRV-002"]["authoritycategory"] == "FMCSA_DOT"
    # A broken file loads nothing and says why.
    doc["requirements"][0]["category"] = "LAW"
    broken = tmp_path / "broken.json"
    broken.write_text(json.dumps(doc))
    with db.connect() as conn:
        bad = catalogimport.run_import(conn, [str(broken)], verify=False)
    assert bad["files"][0]["shape_errors"] and bad["totals"]["requirements"] == 0


def test_fmcsa_biennial_update_suspension():
    """FMCSA suspended enforcement of biennial updates due on or after 06/01/2026 (notice updated
    09/10/2026). One missed before then is still overdue."""
    from datetime import date
    from app import rules
    today = date(2026, 11, 8)
    assert rules.biennial_paused(date(2026, 7, 31), today)
    assert rules.biennial_paused(date(2026, 6, 1), today)
    assert not rules.biennial_paused(date(2026, 5, 31), today)
    assert not rules.biennial_paused(None, today)


def test_loading_stages_rules_and_approval_brings_them_into_force(db, client):
    """Loading changes nothing on any account: the rule is staged, not in force. Approving it in
    Rule Review brings it in and ends the rule it replaces, which hands over its code."""
    import uuid
    from sqlalchemy import text
    from app import catalogimport
    from app.cli import create_admin
    with db.begin() as conn:
        report = catalogimport.run_import(conn, [str(EXAMPLE)], verify=False)
        loaded = catalogimport.load(conn, report, report["sources"])
    try:
        staged = {s["id"]: s for s in loaded["staged"]}
        assert set(staged) == {"MED-DRV-001", "FED-DRV-001"}, loaded
        # A rule that replaces one proves what that one proved: the file's own qualification label
        # is not trusted where TripProof already uses it for something else.
        if staged["FED-DRV-001"]["replaces"]:
            with db.connect() as conn:
                q = conn.execute(text("""SELECT n.qualificationcode = o.qualificationcode FROM compliancerules n
                                         JOIN compliancerules o ON o.recordid = n.supersedes
                                         WHERE n.sourceref = 'FED-DRV-001'""")).scalar()
            assert q == 1
        with db.connect() as conn:
            in_force = {r[0] for r in conn.execute(text(
                "SELECT sourceref FROM compliancerules WHERE effectiveto IS NULL AND sourceref IS NOT NULL"))}
            assert not in_force                                    # nothing staged is in force
        # Loading twice stages nothing twice.
        with db.begin() as conn:
            again = catalogimport.load(conn, report, report["sources"])
        assert not again["staged"] and set(again["already_staged"]) == set(staged)
        # Approved in Rule Review: in force, under the replaced rule's code, which has ended.
        replaced = staged["FED-DRV-001"]["replaces"]
        email = f"rules-{uuid.uuid4().hex[:6]}@tripproof.test"
        create_admin(email, "Rules", "admin password 123", "superadmin")
        token = client.post("/api/auth/login", json={"email": email, "password": "admin password 123"}).json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        listed = {r["code"]: r for r in client.get("/api/admin/rules?pagesize=1000", headers=h).json()["items"]}
        assert listed["FED-DRV-001"]["staged"] and listed["FED-DRV-001"]["replaces"] == replaced
        assert client.put("/api/admin/rules/FED-DRV-001/review", headers=h, json={"legalreview": "approved"}).status_code == 200
        with db.connect() as conn:
            live = conn.execute(text("SELECT code, staged FROM compliancerules WHERE sourceref = 'FED-DRV-001'")).one()
            assert live.staged == 0 and live.code == (replaced or "FED-DRV-001")
            if replaced:
                assert conn.execute(text("""SELECT COUNT(*) FROM compliancerules WHERE code = :c
                                            AND effectiveto IS NULL AND sourceref IS NULL"""), {"c": replaced}).scalar() == 0
    finally:
        # Put the catalog back for the tests that follow.
        with db.begin() as conn:
            for s in loaded["staged"]:
                if s["replaces"]:
                    conn.execute(text("""UPDATE compliancerules SET effectiveto = NULL
                                         WHERE code = :c AND sourceref IS NULL AND accountid IS NULL
                                         ORDER BY effectivefrom DESC LIMIT 1"""), {"c": s["replaces"]})
            conn.execute(text("DELETE FROM compliancerules WHERE sourceref IN ('MED-DRV-001', 'FED-DRV-001')"))
