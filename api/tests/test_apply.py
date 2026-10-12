###################################################################################################
# The online application. Stripe isn't reachable from tests: the development path (no keys, card
# step skipped) runs for real, and the Stripe path runs with the three billing calls replaced.
###################################################################################################
from sqlalchemy import text

from app import billing
from app.config import settings

BASE = {"name": "Sunrise Mobility", "address1": "12 Palm Ave", "city": "Tampa", "state": "FL", "zip": "33602",
        "phone": "813-555-0199", "adminname": "Pat Applicant", "password": "a long password!"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def start(client, email, **over):
    return client.post("/api/apply/start", json={**BASE, "adminemail": email, **over})


def test_application_without_stripe(client, db):
    cfg = client.get("/api/apply/config").json()
    assert cfg["stripe"] is None and cfg["tosversion"]
    terms = client.get("/api/apply/terms").json()
    assert terms["text"].startswith("# TripProof Terms of Service") and len(terms["sha256"]) == 64

    r = start(client, "pat@sunrise.test")
    assert r.status_code == 200, r.text
    h = auth(r.json()["token"])
    st = client.get("/api/apply/state", headers=h).json()
    assert st["step"] == 2 and st["account"]["phone"] == "(813) 555-0199" and st["card"] is None and st["plan"] is None
    with db.connect() as conn:
        status, source = conn.execute(text("SELECT status, signupsource FROM accounts WHERE name = 'Sunrise Mobility'")).one()
    assert (status, source) == ("setup", "online")        # shows as Setup in the admin portal until finished

    ok = {"agree": True, "tosversion": terms["version"], "tossha256": terms["sha256"]}
    assert client.post("/api/apply/complete", json=ok, headers=h).status_code == 400          # no plan yet
    # Page 2: the plan follows from the fleet size.
    assert client.put("/api/apply/plan", json={"fleetsize": 0}, headers=h).status_code == 400
    assert client.put("/api/apply/plan", json={"fleetsize": 80}, headers=h).status_code == 409   # enterprise: contact us
    st = client.put("/api/apply/plan", json={"fleetsize": 8}, headers=h).json()
    assert st["plan"]["code"] == "GROWTH" and st["fleetsize"] == 8 and st["step"] == 3
    assert client.post("/api/apply/complete", json=ok, headers=h).status_code == 400          # no card yet
    assert client.post("/api/apply/card/verify", json={}, headers=h).status_code == 400       # skip must be explicit
    assert client.post("/api/apply/card/verify", json={"skip": True}, headers=h).json()["step"] == 4
    assert client.post("/api/apply/complete", json={**ok, "agree": False}, headers=h).status_code == 400
    assert client.post("/api/apply/complete", json={**ok, "tossha256": "0" * 64}, headers=h).status_code == 409
    done = client.post("/api/apply/complete", json=ok, headers=h)
    assert done.status_code == 200 and done.json()["email"] == "pat@sunrise.test"

    with db.connect() as conn:
        a = conn.execute(text("SELECT status, tosversion, tossha256, tosacceptedby, tosacceptedon, applicationcompletedon "
                              "FROM accounts WHERE name = 'Sunrise Mobility'")).mappings().one()
        sub = conn.execute(text("SELECT s.status, s.fleetsize, s.monthlyprice, s.trialend IS NOT NULL AS trial, p.code FROM subscriptions s "
                                "JOIN plans p ON p.recordid = s.planid JOIN accounts a ON a.recordid = s.accountid "
                                "WHERE a.name = 'Sunrise Mobility'")).mappings().one()
    assert (sub["code"], sub["fleetsize"], float(sub["monthlyprice"]), sub["status"], sub["trial"]) == ("GROWTH", 8, 249.0, "trialing", 1)
    assert a["status"] == "active" and a["tosversion"] == terms["version"] and a["tossha256"] == terms["sha256"]
    assert a["tosacceptedby"] and a["tosacceptedon"] and a["applicationcompletedon"]
    # Finished: the application endpoints close, and the login works.
    assert client.get("/api/apply/state", headers=h).status_code == 409
    assert client.post("/api/auth/login", json={"email": "pat@sunrise.test", "password": "a long password!"}).status_code == 200


def test_application_validation(client):
    assert start(client, "dup@sunrise.test").status_code == 200
    assert start(client, "DUP@sunrise.test").status_code == 409                 # one login per email
    assert start(client, "short@sunrise.test", password="short").status_code == 400
    assert start(client, "bot@sunrise.test", website="http://spam").status_code == 400   # honeypot
    assert start(client, "noaddr@sunrise.test", address1="").status_code == 400
    assert start(client, "bademail").status_code == 400


def test_resume_after_signing_in(client):
    """Someone who stops after step 1 can sign in later and pick up where they left off."""
    start(client, "later@sunrise.test")
    t = client.post("/api/auth/login", json={"email": "later@sunrise.test", "password": "a long password!"}).json()["token"]
    me = client.get("/api/auth/me", headers=auth(t)).json()
    assert me["accountstatus"] == "setup"
    assert client.get("/api/apply/state", headers=auth(t)).json()["step"] == 2   # picks up at the plan


def test_application_with_stripe(client, db, monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_x")
    calls = []
    monkeypatch.setattr(billing, "create_setup_intent", lambda acct, email: calls.append("intent") or {"id": "seti_1", "client_secret": "seti_1_secret"})
    monkeypatch.setattr(billing, "verified_card", lambda si: calls.append(("verify", si)) or
                        {"paymentmethod": "pm_1", "brand": "visa", "last4": "4242", "exp": "12/2030"})
    monkeypatch.setattr(billing, "create_customer", lambda acct, email, name, pm: calls.append(("customer", pm)) or "cus_1")
    monkeypatch.setattr(billing, "ensure_price", lambda plan: calls.append(("price", plan["code"])) or
                        {"stripeproductid": "prod_1", "stripepriceid": "price_1", "stripepriceamount": plan["monthlyprice"]})
    monkeypatch.setattr(billing, "create_subscription", lambda cus, price, trial, acct, n: calls.append(("sub", cus, price, trial, n)) or
                        {"id": "sub_1", "status": "trialing", "trial_end": 1893456000, "current_period_end": 1893456000})

    assert client.get("/api/apply/config").json()["stripe"] == "pk_test_x"
    h = auth(start(client, "card@sunrise.test").json()["token"])
    client.put("/api/apply/plan", json={"fleetsize": 3}, headers=h)
    # With Stripe on, the card step can't be skipped, and needs a SetupIntent first.
    assert client.post("/api/apply/card/verify", json={"skip": True}, headers=h).status_code == 400
    assert client.post("/api/apply/card/intent", headers=h).json()["clientsecret"] == "seti_1_secret"
    st = client.post("/api/apply/card/verify", json={}, headers=h).json()
    assert st["card"] == {"brand": "visa", "last4": "4242", "exp": "12/2030"} and ("verify", "seti_1") in calls
    terms = client.get("/api/apply/terms").json()
    assert client.post("/api/apply/complete", json={"agree": True, "tosversion": terms["version"],
                                                     "tossha256": terms["sha256"]}, headers=h).status_code == 200
    assert ("customer", "pm_1") in calls and ("price", "STARTER") in calls and ("sub", "cus_1", "price_1", 14, 3) in calls
    with db.connect() as conn:
        a = conn.execute(text("SELECT status, stripecustomerid, stripepaymentmethodid, cardlast4 FROM accounts "
                              "WHERE primaryuserid = (SELECT recordid FROM users WHERE email = 'card@sunrise.test')")).one()
    assert tuple(a) == ("active", "cus_1", "pm_1", "4242")
    with db.connect() as conn:
        assert conn.execute(text("SELECT stripesubscriptionid FROM subscriptions WHERE stripesubscriptionid = 'sub_1'")).scalar() == "sub_1"
        assert conn.execute(text("SELECT stripepriceid FROM plans WHERE code = 'STARTER'")).scalar() == "price_1"


def test_only_the_applicant_while_in_setup(client):
    h = auth(client.post("/api/apply/start", json={**BASE, "adminemail": "solo@sunrise.test"}).json()["token"])
    client.put("/api/apply/plan", json={"fleetsize": 2}, headers=h)
    client.post("/api/apply/card/verify", json={"skip": True}, headers=h)
    terms = client.get("/api/apply/terms").json()
    client.post("/api/apply/complete", json={"agree": True, "tosversion": terms["version"], "tossha256": terms["sha256"]}, headers=h)
    # An active account's owner gets a clear refusal, not a second application.
    assert client.post("/api/apply/card/verify", json={"skip": True}, headers=h).status_code == 409


def test_plans_are_public_and_tiered(client):
    plans = client.get("/api/apply/plans").json()
    codes = [p["code"] for p in plans]
    assert codes[:2] == ["STARTER", "GROWTH"] and plans[-1]["contact"] is True
