###################################################################################################
# Billing sync - keeping TripProof's copy of each subscription and invoice in step with Stripe.
#
# Stripe charges on its own schedule (trial end, then monthly on that day) and retries failed
# payments per the dashboard's retry settings. Its webhooks land in handle_event():
#
#   customer.subscription.*   status, trial end, next billing date, cancel-at-period-end
#   invoice.*                 billing history; paid clears the payment error, payment_failed
#                             records it and the next retry
#
# Access follows the account's current subscription:
#   trialing / active                 full access
#   past_due                          full access, with a "payment failed" banner (Stripe is retrying)
#   unpaid / canceled / incomplete_expired
#                                     the account goes inactive with holdreason 'billing': its users
#                                     can sign in only to the Billing page, and a successful payment
#                                     (or a new subscription) lifts the hold. A hold staff put on
#                                     (holdreason NULL) is never lifted here.
#
# Plans are priced by fleet size, and fleets change. Before each renewal - Stripe's
# invoice.upcoming (sent ahead of every renewal, trial end included) and
# customer.subscription.trial_will_end - reprice() counts the vehicles on file and, if that puts
# the account in a different tier, moves the subscription to that tier's price for the coming
# period. `python -m app.cli reprice` does the same for every subscription, as a safety net.
###################################################################################################
from datetime import datetime, timezone

from sqlalchemy.engine import Connection

from app import billing, plans
from app.activity import log
from app.db import newid, row, run, utcnow

LAPSED = ("unpaid", "canceled", "incomplete_expired")
GOOD = ("trialing", "active")
DUE = ("past_due", "unpaid")


def ts(t) -> datetime | None:
    return datetime.fromtimestamp(t, timezone.utc).replace(tzinfo=None) if t else None


def _account_for(conn: Connection, customer: str | None, metadata: dict | None = None) -> dict | None:
    acct = (metadata or {}).get("tripproof_account")
    if acct:
        a = row(conn, "SELECT recordid, status, holdreason, planid, fleetsize FROM accounts WHERE recordid = :a", a=acct)
        if a:
            return a
    if customer:
        return row(conn, "SELECT recordid, status, holdreason, planid, fleetsize FROM accounts WHERE stripecustomerid = :c",
                   c=customer)
    return None


# The subscription that decides an account's access: a live one if there is one (a customer who
# resubscribed after a lapse has the new one), else the most recent. Same order everywhere.
CURRENT_ORDER = f"status IN {LAPSED!r}, startedon DESC, added DESC"


def current_subscription(conn: Connection, accountid: str) -> dict | None:
    return row(conn, f"SELECT * FROM subscriptions WHERE accountid = :a ORDER BY {CURRENT_ORDER} LIMIT 1", a=accountid)


def sync_subscription(conn: Connection, s: dict) -> str | None:
    """Store a subscription's current state (from billing.subscription) and apply its effect on the
    account. Returns the account id, or None for a subscription that isn't ours."""
    sub = row(conn, "SELECT recordid, accountid FROM subscriptions WHERE stripesubscriptionid = :s", s=s["id"])
    now = utcnow()
    if not sub:
        a = _account_for(conn, s.get("customer"), s.get("metadata"))
        if not a or not a["planid"]:
            return None
        # Made outside the application (e.g. in the Stripe dashboard): adopt it on the account's plan.
        plan = row(conn, "SELECT monthlyprice FROM plans WHERE recordid = :p", p=a["planid"])
        sub = {"recordid": newid(), "accountid": a["recordid"]}
        run(conn, """INSERT INTO subscriptions (recordid, accountid, planid, status, fleetsize, monthlyprice, stripesubscriptionid)
                     VALUES (:id, :a, :p, :st, :n, :price, :sid)""",
            id=sub["recordid"], a=a["recordid"], p=a["planid"], st=s["status"], n=a["fleetsize"] or 0,
            price=(s["unit_amount"] / 100) if s.get("unit_amount") is not None else (plan or {}).get("monthlyprice") or 0,
            sid=s["id"])
    ended = ts(s.get("ended_at") or s.get("canceled_at")) if s["status"] in ("canceled", "incomplete_expired") else None
    run(conn, """
        UPDATE subscriptions SET status = :st, trialend = :trial, currentperiodend = :pe, cancelatperiodend = :cape,
               canceledon = COALESCE(:ended, canceledon),
               pastduesince = CASE WHEN :due THEN COALESCE(pastduesince, :now) WHEN :good THEN NULL ELSE pastduesince END,
               nextattempt = CASE WHEN :good THEN NULL ELSE nextattempt END,
               syncedon = :now, updated = :now
        WHERE recordid = :id
    """, st=s["status"][:12], trial=ts(s.get("trial_end")), pe=ts(s.get("current_period_end")),
        cape=1 if s.get("cancel_at_period_end") else 0, ended=ended, due=s["status"] in DUE, good=s["status"] in GOOD,
        now=now, id=sub["recordid"])
    apply_access(conn, sub["accountid"])
    return sub["accountid"]


def apply_access(conn: Connection, accountid: str):
    """Put on or lift a billing hold to match the account's current subscription."""
    a = row(conn, "SELECT status, holdreason FROM accounts WHERE recordid = :a", a=accountid)
    sub = current_subscription(conn, accountid)
    if not a or not sub:
        return
    if sub["status"] in LAPSED and a["status"] == "active":
        run(conn, "UPDATE accounts SET status = 'inactive', holdreason = 'billing', updated = :now WHERE recordid = :a",
            now=utcnow(), a=accountid)
        log(conn, None, "billing-hold", "account", accountid, {"subscription": sub["stripesubscriptionid"], "status": sub["status"]},
            accountid=accountid)
    elif sub["status"] in GOOD + ("past_due",) and a["status"] == "inactive" and a["holdreason"] == "billing":
        run(conn, "UPDATE accounts SET status = 'active', holdreason = NULL, updated = :now WHERE recordid = :a",
            now=utcnow(), a=accountid)
        log(conn, None, "billing-hold-lifted", "account", accountid,
            {"subscription": sub["stripesubscriptionid"], "status": sub["status"]}, accountid=accountid)


def billable_fleet(conn: Connection, accountid: str) -> int:
    """The fleet size the next period is billed on: the vehicles on file (not deleted; vehicles seen
    only in trip imports - stubs - aren't counted until someone confirms them). Until any are
    entered, the size given at signup."""
    n = row(conn, "SELECT COUNT(*) AS n FROM vehicles WHERE accountid = :a AND deleted IS NULL AND stub = 0",
            a=accountid)["n"]
    if n:
        return n
    return (row(conn, "SELECT fleetsize FROM accounts WHERE recordid = :a", a=accountid) or {}).get("fleetsize") or 1


def reprice(conn: Connection, accountid: str) -> str:
    """Put the account's live subscription on the plan its current fleet size calls for, effective
    from the next invoice. Returns what happened, for the event log."""
    sub = current_subscription(conn, accountid)
    if not sub or sub["status"] in LAPSED or not sub["stripesubscriptionid"]:
        return "no live subscription"
    fleet = billable_fleet(conn, accountid)
    plan = plans.plan_for_fleet(conn, fleet)
    now = utcnow()
    if not plan or plan["contact"]:
        # Grown past the priced tiers: keep billing the current plan and flag it for staff to quote.
        run(conn, "UPDATE subscriptions SET fleetsize = :n, updated = :now WHERE recordid = :id", n=fleet, now=now, id=sub["recordid"])
        log(conn, None, "billing-quote-needed", "account", accountid,
            {"fleetsize": fleet, "plan": plan["code"] if plan else None}, accountid=accountid)
        return f"quote needed ({fleet} vehicles)"
    if plan["recordid"] == sub["planid"]:
        run(conn, "UPDATE subscriptions SET fleetsize = :n, updated = :now WHERE recordid = :id", n=fleet, now=now, id=sub["recordid"])
        run(conn, "UPDATE accounts SET fleetsize = :n WHERE recordid = :a", n=fleet, a=accountid)
        return f"unchanged ({plan['code']}, {fleet} vehicles)"
    old = row(conn, "SELECT code FROM plans WHERE recordid = :p", p=sub["planid"])
    price = billing.ensure_price(plan)
    run(conn, """UPDATE plans SET stripeproductid = :prod, stripepriceid = :price, stripepriceamount = :amt
                 WHERE recordid = :p""", prod=price["stripeproductid"], price=price["stripepriceid"],
        amt=price["stripepriceamount"], p=plan["recordid"])
    billing.change_price(sub["stripesubscriptionid"], price["stripepriceid"], fleet)
    run(conn, """UPDATE subscriptions SET planid = :p, monthlyprice = :price, fleetsize = :n, updated = :now
                 WHERE recordid = :id""", p=plan["recordid"], price=plan["monthlyprice"], n=fleet, now=now, id=sub["recordid"])
    run(conn, "UPDATE accounts SET planid = :p, fleetsize = :n, updated = :now WHERE recordid = :a",
        p=plan["recordid"], n=fleet, now=now, a=accountid)
    log(conn, None, "billing-plan-changed", "account", accountid,
        {"from": old["code"] if old else None, "to": plan["code"], "fleetsize": fleet, "monthlyprice": plan["monthlyprice"]},
        accountid=accountid)
    return f"plan changed {old['code'] if old else '?'} -> {plan['code']} ({fleet} vehicles)"


def _upcoming_account(conn: Connection, obj: dict) -> str | None:
    """The account an upcoming invoice (which has no id of its own) or a subscription belongs to."""
    sid = obj.get("subscription") or ((obj.get("parent") or {}).get("subscription_details") or {}).get("subscription")
    if obj.get("object") == "subscription":
        sid = obj.get("id")
    if sid:
        s = row(conn, "SELECT accountid FROM subscriptions WHERE stripesubscriptionid = :s", s=sid)
        if s:
            return s["accountid"]
    a = _account_for(conn, obj.get("customer"), obj.get("metadata"))
    return a["recordid"] if a else None


def sync_invoice(conn: Connection, inv: dict, event_type: str | None = None) -> str | None:
    """Store an invoice (from billing.invoice) and record a payment or failure on its subscription."""
    sub = row(conn, "SELECT recordid, accountid FROM subscriptions WHERE stripesubscriptionid = :s",
              s=inv["subscription"]) if inv.get("subscription") else None
    accountid = sub["accountid"] if sub else ((_account_for(conn, inv.get("customer")) or {}).get("recordid"))
    if not accountid:
        return None
    now = utcnow()
    fields = dict(accountid=accountid, subscriptionid=sub["recordid"] if sub else None, number=inv.get("number"),
                  status=(inv.get("status") or "draft")[:16], amountdue=inv["amount_due"], amountpaid=inv["amount_paid"],
                  currency=(inv.get("currency") or "usd")[:3], periodstart=ts(inv.get("period_start")),
                  periodend=ts(inv.get("period_end")), paidon=ts(inv.get("paid_at")), attemptcount=inv.get("attempt_count") or 0,
                  nextattempt=ts(inv.get("next_payment_attempt")), failuremessage=inv.get("failure"),
                  hostedurl=inv.get("hosted_invoice_url"), pdfurl=inv.get("invoice_pdf"), invoicedon=ts(inv.get("created")))
    run(conn, f"""
        INSERT INTO invoices (recordid, stripeinvoiceid, {", ".join(fields)})
        VALUES (:id, :sid, {", ".join(":" + k for k in fields)})
        ON DUPLICATE KEY UPDATE {", ".join(f"{k} = VALUES({k})" for k in fields)}, updated = :now
    """, id=newid(), sid=inv["id"], now=now, **fields)
    if sub and inv.get("status") == "paid" and inv["amount_paid"] > 0:
        run(conn, """UPDATE subscriptions SET lastpaidon = :paid, lastpaidamount = :amt, lastpaymenterror = NULL,
                            nextattempt = NULL, updated = :now WHERE recordid = :id""",
            paid=ts(inv.get("paid_at")) or now, amt=inv["amount_paid"], now=now, id=sub["recordid"])
    elif sub and event_type == "invoice.payment_failed":
        run(conn, """UPDATE subscriptions SET lastpaymenterror = :err, nextattempt = :next,
                            pastduesince = COALESCE(pastduesince, :now), updated = :now WHERE recordid = :id""",
            err=inv.get("failure") or "The payment was declined.", next=ts(inv.get("next_payment_attempt")), now=now,
            id=sub["recordid"])
        log(conn, None, "billing-payment-failed", "invoice", inv["id"],
            {"amount": inv["amount_due"], "attempt": inv.get("attempt_count"), "reason": inv.get("failure")}, accountid=accountid)
    return accountid


def handle_event(conn: Connection, event: dict) -> str:
    """Apply one webhook event. Stripe delivers at least once, so each event id is handled once.
    Raising rolls the whole thing back (event record included) and Stripe retries later."""
    run(conn, """INSERT IGNORE INTO stripeevents (eventid, type, livemode, stripecreated) VALUES (:id, :t, :live, :at)""",
        id=event["id"], t=event["type"][:64], live=1 if event.get("livemode") else 0, at=ts(event.get("created")))
    if row(conn, "SELECT outcome FROM stripeevents WHERE eventid = :id", id=event["id"])["outcome"]:
        return "duplicate"
    kind, obj = event["type"], (event.get("data") or {}).get("object") or {}
    accountid, outcome = None, "ignored"
    if kind in ("invoice.upcoming", "customer.subscription.trial_will_end"):
        # A renewal is coming: bill it on the fleet as it is now.
        accountid = _upcoming_account(conn, obj)
        outcome = reprice(conn, accountid) if accountid else "not ours"
        if kind == "customer.subscription.trial_will_end" and accountid and obj.get("id"):
            sync_subscription(conn, billing.subscription(obj["id"]))
    elif kind.startswith("customer.subscription."):
        accountid = sync_subscription(conn, billing.subscription(obj["id"]))
        outcome = "subscription synced" if accountid else "not ours"
    elif kind.startswith("invoice.") and obj.get("id"):
        try:
            inv = billing.invoice(obj["id"])
        except billing.BillingError:
            inv = None                          # e.g. a draft that has since been deleted
        if inv:
            accountid = sync_invoice(conn, inv, kind)
            outcome = "invoice synced" if accountid else "not ours"
    run(conn, "UPDATE stripeevents SET accountid = :a, outcome = :o WHERE eventid = :id", a=accountid, o=outcome, id=event["id"])
    return outcome


# The events the endpoint should be subscribed to in the Stripe dashboard.
EVENTS = ("customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted",
          "customer.subscription.paused", "customer.subscription.resumed", "customer.subscription.trial_will_end",
          "invoice.upcoming", "invoice.created", "invoice.finalized", "invoice.paid", "invoice.payment_failed", "invoice.payment_action_required",
          "invoice.voided", "invoice.marked_uncollectible")
