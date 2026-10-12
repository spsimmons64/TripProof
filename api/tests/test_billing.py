###################################################################################################
# Billing after signup: the Stripe webhook, billing holds, and the customer changing their card.
# Stripe isn't reachable from tests - events are signed here with the test secret, and the calls
# that read from or write to Stripe are replaced.
###################################################################################################
import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import text

from app import billing
from app.config import settings

SECRET = "whsec_test_secret"
BASE = {"name": "Keystone Rides", "address1": "1 Main St", "city": "Orlando", "state": "FL", "zip": "32801",
        "phone": "407-555-0100", "adminname": "Kim Keystone", "password": "a long password!"}


def auth(token):
    return {"Authorization": f"Bearer {token}"}


def signed(client, event: dict, secret: str = SECRET):
    payload = json.dumps(event)
    t = int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.{payload}".encode(), hashlib.sha256).hexdigest()
    return client.post("/api/billing/webhook", content=payload,
                       headers={"stripe-signature": f"t={t},v1={sig}", "content-type": "application/json"})


def event(eid: str, kind: str, objid: str) -> dict:
    return {"id": eid, "object": "event", "type": kind, "livemode": False, "created": int(time.time()),
            "data": {"object": {"id": objid}}}


def sub(sid: str, status: str, customer: str = "cus_k1", **over) -> dict:
    return {"id": sid, "status": status, "customer": customer, "trial_end": None, "current_period_end": 1893456000,
            "cancel_at_period_end": False, "canceled_at": None, "ended_at": None, "metadata": {}, "price": "price_k",
            "unit_amount": 9900, **over}


def inv(iid: str, status: str, paid: float = 0, due: float = 99, failure=None, sid: str = "sub_k1") -> dict:
    return {"id": iid, "customer": "cus_k1", "number": f"KR-{iid[-4:]}", "status": status, "subscription": sid,
            "amount_due": due, "amount_paid": paid, "currency": "usd", "created": int(time.time()),
            "period_start": int(time.time()), "period_end": int(time.time()) + 30 * 86400,
            "paid_at": int(time.time()) if status == "paid" else None, "attempt_count": 1,
            "next_payment_attempt": int(time.time()) + 3 * 86400 if status == "open" else None,
            "hosted_invoice_url": "https://invoice.stripe.test/x", "invoice_pdf": "https://invoice.stripe.test/x.pdf",
            "failure": failure}


@pytest.fixture
def stripe_on(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_x")
    monkeypatch.setattr(settings, "stripe_publishable_key", "pk_test_x")
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    state = {"subs": {}, "invoices": {}}
    monkeypatch.setattr(billing, "subscription", lambda sid: state["subs"][sid])
    monkeypatch.setattr(billing, "invoice", lambda iid: state["invoices"][iid])
    return state


def signup(client, db, monkeypatch, tag: str) -> dict:
    """A customer signed up online (Stripe calls replaced): customer cus_<tag>, trialing on sub_<tag>."""
    from app.routers import apply
    apply._starts.clear()                   # the per-IP signup brake would trip across test files
    monkeypatch.setattr(billing, "create_setup_intent", lambda a, e: {"id": "seti_k", "client_secret": "seti_k_secret"})
    monkeypatch.setattr(billing, "verified_card", lambda si: {"paymentmethod": "pm_k", "brand": "visa", "last4": "4242", "exp": "12/2030"})
    monkeypatch.setattr(billing, "create_customer", lambda *a: f"cus_{tag}")
    monkeypatch.setattr(billing, "ensure_price", lambda plan: {"stripeproductid": "prod_k", "stripepriceid": "price_k",
                                                              "stripepriceamount": plan["monthlyprice"]})
    monkeypatch.setattr(billing, "create_subscription", lambda *a: sub(f"sub_{tag}", "trialing", customer=f"cus_{tag}", trial_end=1893456000))
    h = auth(client.post("/api/apply/start", json={**BASE, "name": f"Keystone {tag}", "adminemail": f"{tag}@keystone.test"}).json()["token"])
    client.put("/api/apply/plan", json={"fleetsize": 4}, headers=h)
    client.post("/api/apply/card/intent", headers=h)
    client.post("/api/apply/card/verify", json={}, headers=h)
    t = client.get("/api/apply/terms").json()
    r = client.post("/api/apply/complete", json={"agree": True, "tosversion": t["version"], "tossha256": t["sha256"]}, headers=h)
    assert r.status_code == 200, r.text
    with db.connect() as conn:
        acct = conn.execute(text("SELECT recordid FROM accounts WHERE stripecustomerid = :c"), {"c": f"cus_{tag}"}).scalar()
    return {"h": h, "accountid": acct}


def account(db, acct):
    with db.connect() as conn:
        return dict(conn.execute(text("SELECT status, holdreason FROM accounts WHERE recordid = :a"), {"a": acct}).mappings().one())


def current(db, acct):
    with db.connect() as conn:
        return dict(conn.execute(text("SELECT * FROM subscriptions WHERE accountid = :a ORDER BY status IN ('unpaid', 'canceled', 'incomplete_expired'), startedon DESC, added DESC LIMIT 1"),
                                 {"a": acct}).mappings().one())


def test_webhook_needs_a_valid_signature(client, db, monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    assert client.post("/api/billing/webhook", content="{}").status_code == 503          # not set up
    monkeypatch.setattr(settings, "stripe_webhook_secret", SECRET)
    assert client.post("/api/billing/webhook", content="{}").status_code == 400          # unsigned
    assert signed(client, event("evt_bad", "invoice.paid", "in_x"), secret="whsec_other").status_code == 400
    r = signed(client, event("evt_other", "charge.succeeded", "ch_x"))
    assert r.status_code == 200 and r.json()["outcome"] == "ignored"


def test_billing_lifecycle(client, db, stripe_on, monkeypatch):
    customer = signup(client, db, monkeypatch, "k1")
    h, acct = customer["h"], customer["accountid"]
    b = client.get("/api/billing", headers=h).json()
    assert b["plan"]["name"] == "Starter" and b["subscription"]["status"] == "trialing" and b["card"]["last4"] == "4242"
    assert b["hold"] is False and b["stripe"] == "pk_test_x"

    # Trial ends; Stripe charges the card.
    stripe_on["subs"]["sub_k1"] = sub("sub_k1", "active")
    stripe_on["invoices"]["in_k0001"] = inv("in_k0001", "paid", paid=99)
    assert signed(client, event("evt_1", "invoice.paid", "in_k0001")).json()["outcome"] == "invoice synced"
    assert signed(client, event("evt_2", "customer.subscription.updated", "sub_k1")).json()["outcome"] == "subscription synced"
    assert signed(client, event("evt_1", "invoice.paid", "in_k0001")).json()["outcome"] == "duplicate"   # redelivery
    s = current(db, acct)
    assert s["status"] == "active" and float(s["lastpaidamount"]) == 99 and s["lastpaymenterror"] is None
    b = client.get("/api/billing", headers=h).json()
    assert [(i["number"], i["status"], float(i["amountpaid"])) for i in b["invoices"]] == [("KR-0001", "paid", 99)]

    # Next month the card is declined: past due, still full access, with the reason recorded.
    stripe_on["invoices"]["in_k0002"] = inv("in_k0002", "open", failure="Your card was declined.")
    stripe_on["subs"]["sub_k1"] = sub("sub_k1", "past_due")
    signed(client, event("evt_3", "invoice.payment_failed", "in_k0002"))
    signed(client, event("evt_4", "customer.subscription.updated", "sub_k1"))
    s = current(db, acct)
    assert s["status"] == "past_due" and s["pastduesince"] and s["lastpaymenterror"] == "Your card was declined." and s["nextattempt"]
    assert account(db, acct) == {"status": "active", "holdreason": None}
    me = client.get("/api/auth/me", headers=h).json()
    assert me["subscription"]["status"] == "past_due" and me["billinghold"] is False
    assert client.get("/api/dashboard", headers=h).status_code == 200

    # Retries exhausted, Stripe cancels: a billing hold. They can sign in, but only to Billing.
    stripe_on["subs"]["sub_k1"] = sub("sub_k1", "canceled", ended_at=int(time.time()))
    signed(client, event("evt_5", "customer.subscription.deleted", "sub_k1"))
    assert account(db, acct) == {"status": "inactive", "holdreason": "billing"}
    login = client.post("/api/auth/login", json={"email": "k1@keystone.test", "password": BASE["password"]})
    assert login.status_code == 200
    h = auth(login.json()["token"])
    assert client.get("/api/auth/me", headers=h).json()["billinghold"] is True
    assert client.get("/api/dashboard", headers=h).status_code == 402
    assert client.get("/api/billing", headers=h).json()["hold"] is True

    # They enter a new card: it becomes the default and a new subscription starts (no trial).
    made = []
    monkeypatch.setattr(billing, "customer_setup_intent", lambda cus, a: {"id": "seti_new", "client_secret": "seti_new_secret"})
    monkeypatch.setattr(billing, "set_default_card", lambda cus, si: made.append(("default", cus, si)) or
                        {"paymentmethod": "pm_new", "brand": "mastercard", "last4": "4444", "exp": "01/2031"})
    monkeypatch.setattr(billing, "ensure_price", lambda plan: {"stripeproductid": "prod_k", "stripepriceid": "price_k",
                                                              "stripepriceamount": plan["monthlyprice"]})
    monkeypatch.setattr(billing, "create_subscription", lambda cus, price, trial, a, n: made.append(("sub", trial)) or sub("sub_k2", "active"))
    assert client.post("/api/billing/card/intent", headers=h).json()["clientsecret"] == "seti_new_secret"
    r = client.post("/api/billing/card", headers=h).json()
    assert ("default", "cus_k1", "seti_new") in made and ("sub", 0) in made
    assert "active again" in r["message"] and r["card"]["last4"] == "4444" and r["hold"] is False
    assert account(db, acct) == {"status": "active", "holdreason": None}
    assert current(db, acct)["stripesubscriptionid"] == "sub_k2"
    assert client.get("/api/dashboard", headers=h).status_code == 200

    # A late event about the old, canceled subscription doesn't put the hold back.
    signed(client, event("evt_6", "customer.subscription.updated", "sub_k1"))
    assert account(db, acct)["status"] == "active"


def test_staff_hold_is_not_lifted_by_payment(client, db, stripe_on, monkeypatch):
    customer = signup(client, db, monkeypatch, "s1")
    from app.cli import create_admin
    create_admin("billing-root@tripproof.test", "Billing Root", "admin password 123", "superadmin")
    staff = auth(client.post("/api/auth/login", json={"email": "billing-root@tripproof.test", "password": "admin password 123"}).json()["token"])
    acct = customer["accountid"]
    assert client.patch(f"/api/admin/accounts/{acct}", json={"status": "inactive"}, headers=staff).status_code == 200
    stripe_on["subs"]["sub_s1"] = sub("sub_s1", "active", customer="cus_s1")
    signed(client, event("evt_s1", "customer.subscription.updated", "sub_s1"))
    assert account(db, acct) == {"status": "inactive", "holdreason": None}
    # Staff see the subscription in the customer record.
    detail = client.get(f"/api/admin/accounts/{acct}", headers=staff).json()
    assert detail["subscription"]["status"] == "active" and detail["stripedashboard"].endswith("/test/customers/cus_s1")
    row = next(i for i in client.get("/api/admin/accounts", params={"q": "Keystone s1"}, headers=staff).json()["items"] if i["recordid"] == acct)
    assert row["substatus"] == "active"


def test_events_for_other_customers_are_ignored(client, db, stripe_on):
    stripe_on["subs"]["sub_nobody"] = sub("sub_nobody", "active", customer="cus_nobody")
    assert signed(client, event("evt_n1", "customer.subscription.created", "sub_nobody")).json()["outcome"] == "not ours"


def test_launched_staff_cannot_change_the_card(client, db, stripe_on, monkeypatch):
    customer = signup(client, db, monkeypatch, "l1")
    from app.cli import create_admin
    create_admin("billing-launcher@tripproof.test", "Billing Launcher", "admin password 123", "superadmin")
    staff = auth(client.post("/api/auth/login", json={"email": "billing-launcher@tripproof.test", "password": "admin password 123"}).json()["token"])
    token = client.post(f"/api/admin/accounts/{customer['accountid']}/launch", headers=staff).json()["token"]
    assert client.get("/api/billing", headers=auth(token)).status_code == 200
    assert client.post("/api/billing/card/intent", headers=auth(token)).status_code == 403


def add_vehicles(db, acct, n, stub=0):
    import uuid
    with db.begin() as conn:
        for _ in range(n):
            conn.execute(text("INSERT INTO vehicles (recordid, accountid, externalid, stub) VALUES (:id, :a, :x, :s)"),
                         {"id": str(uuid.uuid4()), "a": acct, "x": uuid.uuid4().hex[:12], "s": stub})


def test_fleet_size_is_rechecked_before_each_renewal(client, db, stripe_on, monkeypatch):
    customer = signup(client, db, monkeypatch, "r1")            # signed up with 4 vehicles: Starter
    acct = customer["accountid"]
    moved = []
    monkeypatch.setattr(billing, "ensure_price", lambda plan: {"stripeproductid": "prod_r", "stripepriceid": f"price_{plan['code']}",
                                                              "stripepriceamount": plan["monthlyprice"]})
    monkeypatch.setattr(billing, "change_price", lambda sid, price, n: moved.append((sid, price, n)) or sub(sid, "active"))
    upcoming = lambda eid: {"id": eid, "type": "invoice.upcoming", "created": int(time.time()), "livemode": False,
                            "data": {"object": {"object": "invoice", "customer": "cus_r1", "subscription": "sub_r1"}}}

    # No vehicles entered yet: billed on the size given at signup.
    assert signed(client, upcoming("evt_r0")).json()["outcome"] == "unchanged (STARTER, 4 vehicles)"
    # The fleet grew to 8 (stub vehicles from trip imports don't count): Growth from the next invoice.
    add_vehicles(db, acct, 8)
    add_vehicles(db, acct, 3, stub=1)
    assert signed(client, upcoming("evt_r1")).json()["outcome"] == "plan changed STARTER -> GROWTH (8 vehicles)"
    assert moved == [("sub_r1", "price_GROWTH", 8)]
    s = current(db, acct)
    assert float(s["monthlyprice"]) == 249 and s["fleetsize"] == 8
    b = client.get("/api/billing", headers=customer["h"]).json()
    assert b["plan"]["name"] == "Growth" and b["billablefleet"] == 8
    # Same fleet at the next renewal: nothing to change.
    assert signed(client, upcoming("evt_r2")).json()["outcome"].startswith("unchanged (GROWTH")
    assert len(moved) == 1
    # Past the priced tiers: keeps the current price and is flagged for a quote.
    add_vehicles(db, acct, 52)
    assert signed(client, upcoming("evt_r3")).json()["outcome"] == "quote needed (60 vehicles)"
    assert len(moved) == 1
