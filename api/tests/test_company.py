###################################################################################################
# The customer's own company profile (Settings -> Company).
###################################################################################################
import pytest

from tests.test_flow import login


@pytest.fixture(scope="module")
def acct(client, db):
    from app.cli import create_account
    create_account("Profile Test Transport", "owner@profile.test", "Owner P", "FL", "America/New_York", "correct horse battery")
    return {"h": login(client, "owner@profile.test", "correct horse battery"), "db": db}


def test_company_profile(client, acct):
    h = acct["h"]
    c = client.get("/api/company", headers=h).json()
    assert c["name"] == "Profile Test Transport" and c["state"] == "FL" and c["accountnumber"]

    r = client.put("/api/company", json={"phone": "8135550100", "npi": "123"}, headers=h)
    assert r.status_code == 400 and "NPI" in r.text
    r = client.put("/api/company", json={"phone": "8135550100", "npi": "1234567890", "city": "Tampa"}, headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["evaluation"] is not None                       # city decides local rules: re-checked
    c = client.get("/api/company", headers=h).json()
    assert c["phone"] == "(813) 555-0100" and c["npi"] == "1234567890" and c["city"] == "Tampa"
    assert client.put("/api/company", json={"npi": "1234567890"}, headers=h).json()["evaluation"] is None
    assert client.put("/api/company", json={"name": " "}, headers=h).status_code == 400
