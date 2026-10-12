###################################################################################################
# Billing - the Stripe webhook, and the customer's Billing page (plan, status, card, invoices).
#
# The webhook is public; Stripe's signature (STRIPE_WEBHOOK_SECRET) is what authenticates it.
# Everything else is for the customer's owner/admin users. Changing the card is the customer's own
# act - TripProof staff in a launched session can look but not change it.
###################################################################################################
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.engine import Connection
from sqlalchemy.exc import OperationalError

from app import billing, billingsync, plans
from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, rows, run, tx, utcnow
from app.security import client_ip, current_user

router = APIRouter(prefix="/api/billing", tags=["billing"])


@router.post("/webhook")
async def webhook(request: Request):
    """Async only to read the raw body (the signature covers the exact bytes). The work - database
    and Stripe calls, which block - runs on a worker thread, so events arriving together for the
    same customer don't stall the event loop while one waits on the other's row locks."""
    if not settings.stripe_webhook_secret:
        raise HTTPException(503, "Webhooks aren't set up on this server")
    payload = await request.body()
    try:
        event = billing.construct_event(payload, request.headers.get("stripe-signature"))
    except ValueError:
        raise HTTPException(400, "Invalid signature")
    return {"received": True, "outcome": await run_in_threadpool(_handle, event)}


def _handle(event: dict) -> str:
    # Two events about one customer can deadlock on its rows; MariaDB rolls one back - try it again.
    for attempt in range(3):
        try:
            with tx() as conn:
                return billingsync.handle_event(conn, event)
        except OperationalError as e:
            if attempt == 2 or getattr(e.orig, "args", [None])[0] not in (1213, 1205):   # deadlock, lock wait timeout
                raise
            time.sleep(0.2 * (attempt + 1))


# ------------------------------------------------------------------------------------------------
# The customer's Billing page
# ------------------------------------------------------------------------------------------------

def billing_user(user: dict = Depends(current_user)) -> dict:
    """The customer's owners and admins (and staff launched into their portal)."""
    if user.get("platformrole") and not user.get("launched"):
        raise HTTPException(403, "Billing belongs to a customer account")
    if user["role"] not in ("owner", "admin"):
        raise HTTPException(403, "Only account owners and admins can see billing")
    return user


def card_changer(user: dict = Depends(billing_user)) -> dict:
    if user.get("launched"):
        raise HTTPException(403, "Only the customer can change their payment card")
    if not billing.configured():
        raise HTTPException(503, "Card payments aren't set up on this server")
    return user


def billing_state(conn: Connection, accountid: str) -> dict:
    a = row(conn, """
        SELECT a.status, a.holdreason, a.fleetsize, a.stripecustomerid, a.cardbrand, a.cardlast4, a.cardexp,
               p.name AS planname, p.monthlyprice AS planprice
        FROM accounts a LEFT JOIN plans p ON p.recordid = a.planid WHERE a.recordid = :a
    """, a=accountid)
    sub = billingsync.current_subscription(conn, accountid)
    if sub:
        sub = {k: sub[k] for k in ("status", "fleetsize", "monthlyprice", "trialend", "currentperiodend", "cancelatperiodend",
                                   "pastduesince", "lastpaidon", "lastpaidamount", "lastpaymenterror", "nextattempt",
                                   "startedon", "canceledon")}
    invoices = rows(conn, """
        SELECT number, status, amountdue, amountpaid, periodstart, periodend, paidon, invoicedon, hostedurl, pdfurl,
               failuremessage
        FROM invoices WHERE accountid = :a AND status <> 'draft' ORDER BY invoicedon DESC, added DESC LIMIT 24
    """, a=accountid)
    # What the next renewal will be billed on, from the vehicles on file today.
    fleet = billingsync.billable_fleet(conn, accountid)
    upcoming = plans.plan_for_fleet(conn, fleet)
    return {"plan": {"name": a["planname"], "monthlyprice": a["planprice"], "fleetsize": a["fleetsize"]} if a["planname"] else None,
            "billablefleet": fleet,
            "nextplan": {"name": upcoming["name"], "monthlyprice": upcoming["monthlyprice"], "contact": upcoming["contact"]} if upcoming else None,
            "subscription": sub, "hold": a["holdreason"] == "billing" and a["status"] == "inactive",
            "card": {"brand": a["cardbrand"], "last4": a["cardlast4"], "exp": a["cardexp"]} if a["cardlast4"] else None,
            "stripe": settings.stripe_publishable_key if billing.configured() and a["stripecustomerid"] else None,
            "invoices": invoices}


@router.get("")
def get_billing(user: dict = Depends(billing_user), conn: Connection = Depends(get_conn)):
    return billing_state(conn, user["accountid"])


@router.post("/card/intent")
def card_intent(user: dict = Depends(card_changer), conn: Connection = Depends(get_conn)):
    a = row(conn, "SELECT stripecustomerid FROM accounts WHERE recordid = :a", a=user["accountid"])
    if not a["stripecustomerid"]:
        raise HTTPException(409, "This account has no billing profile yet. Please contact support.")
    try:
        si = billing.customer_setup_intent(a["stripecustomerid"], user["accountid"])
    except billing.BillingError as e:
        raise HTTPException(402, str(e))
    run(conn, "UPDATE accounts SET stripesetupintentid = :s WHERE recordid = :a", s=si["id"], a=user["accountid"])
    return {"clientsecret": si["client_secret"]}


@router.post("/card")
def change_card(request: Request, user: dict = Depends(card_changer), conn: Connection = Depends(get_conn)):
    """After the browser confirmed the SetupIntent: make that card the default, then settle up -
    pay whatever is open, or start a new subscription (no trial) if the old one was canceled."""
    a = row(conn, """SELECT recordid, stripecustomerid, stripesetupintentid, planid, fleetsize FROM accounts
                     WHERE recordid = :a FOR UPDATE""", a=user["accountid"])
    if not a["stripesetupintentid"] or not a["stripecustomerid"]:
        raise HTTPException(400, "Start the card change first")
    ip, now = client_ip(request), utcnow()
    try:
        card = billing.set_default_card(a["stripecustomerid"], a["stripesetupintentid"])
    except billing.BillingError as e:
        raise HTTPException(402, str(e))
    run(conn, """UPDATE accounts SET stripepaymentmethodid = :pm, cardbrand = :b, cardlast4 = :l, cardexp = :x,
                    cardverifiedon = :now, stripesetupintentid = NULL WHERE recordid = :a""",
        pm=card["paymentmethod"], b=card["brand"], l=card["last4"], x=card["exp"], now=now, a=a["recordid"])
    log(conn, user, "billing-card-changed", "account", a["recordid"], {"brand": card["brand"], "last4": card["last4"]}, ip=ip)

    sub = billingsync.current_subscription(conn, a["recordid"])
    message = "Your card was updated."
    try:
        if sub and sub["status"] in ("past_due", "unpaid", "incomplete"):
            if billing.pay_open_invoices(a["stripecustomerid"]):
                message = "Your card was updated and the balance due was paid."
            billingsync.sync_subscription(conn, billing.subscription(sub["stripesubscriptionid"]))
        elif not sub or sub["status"] in billingsync.LAPSED:
            # Back on the plan today's fleet calls for (the current one if the fleet is past the priced tiers).
            fleet = billingsync.billable_fleet(conn, a["recordid"])
            fits = plans.plan_for_fleet(conn, fleet)
            planid = fits["recordid"] if fits and not fits["contact"] else a["planid"]
            plan = row(conn, "SELECT * FROM plans WHERE recordid = :p AND monthlyprice IS NOT NULL", p=planid)
            if not plan:
                return {**billing_state(conn, a["recordid"]), "paymentfailed": True,
                        "message": "Your card was updated, but your plan is no longer offered online. Please contact support."}
            price = billing.ensure_price(plan)
            run(conn, """UPDATE plans SET stripeproductid = :prod, stripepriceid = :price, stripepriceamount = :amt
                         WHERE recordid = :p""", prod=price["stripeproductid"], price=price["stripepriceid"],
                amt=price["stripepriceamount"], p=plan["recordid"])
            s = billing.create_subscription(a["stripecustomerid"], price["stripepriceid"], 0, a["recordid"], fleet)
            run(conn, """INSERT INTO subscriptions (recordid, accountid, planid, status, fleetsize, monthlyprice,
                                                    stripesubscriptionid, startedon)
                         VALUES (:id, :a, :p, :st, :n, :price, :sid, :now)""",
                id=newid(), a=a["recordid"], p=plan["recordid"], st=s["status"], n=fleet,
                price=plan["monthlyprice"], sid=s["id"], now=now)
            run(conn, "UPDATE accounts SET planid = :p, fleetsize = :n WHERE recordid = :a", p=plan["recordid"], n=fleet, a=a["recordid"])
            billingsync.sync_subscription(conn, s)
            log(conn, user, "billing-resubscribed", "account", a["recordid"], {"plan": plan["code"], "subscription": s["id"]}, ip=ip)
            message = f"Your card was charged and your {plan['name']} subscription is active again."
    except billing.BillingError as e:
        # The card is saved either way; the charge is what failed.
        return {**billing_state(conn, a["recordid"]), "message": f"Your card was saved, but the payment didn't go through: {e}",
                "paymentfailed": True}
    return {**billing_state(conn, a["recordid"]), "message": message}
