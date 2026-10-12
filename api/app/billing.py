###################################################################################################
# Billing - the only module that talks to Stripe.
#
# The application verifies a card before the account is finished: a SetupIntent with no customer
# (step 2), confirmed in the browser by Stripe.js, so card details never reach TripProof. When the
# applicant accepts the Terms (step 3) a Stripe customer is created and the verified payment method
# attached and made the default for invoices.
#
# After that Stripe bills on its own - at the end of the free trial, then monthly - and reports
# back through webhooks (routers/billing.py, app/billingsync.py).
#
# With no STRIPE_SECRET_KEY configured (development) configured() is False and the application
# lets the card step be skipped; nothing here is called.
###################################################################################################
import logging

import stripe

from app.config import settings

log = logging.getLogger("tripproof.billing")


class BillingError(Exception):
    """A Stripe failure worded for the applicant."""


def configured() -> bool:
    return bool(settings.stripe_secret_key and settings.stripe_publishable_key)


def _client():
    stripe.api_key = settings.stripe_secret_key
    return stripe


def _friendly(e: Exception) -> BillingError:
    msg = getattr(e, "user_message", None) or "The card couldn't be verified. Check the details or try another card."
    return BillingError(msg)


def create_setup_intent(accountid: str, email: str) -> dict:
    s = _client()
    try:
        si = s.SetupIntent.create(payment_method_types=["card"], usage="off_session",
                                  metadata={"tripproof_account": accountid, "email": email})
    except Exception as e:  # stripe.StripeError and network failures alike
        raise _friendly(e)
    return {"id": si.id, "client_secret": si.client_secret}


def verified_card(setupintentid: str) -> dict:
    """The card behind a SetupIntent, if Stripe says it was verified; raises otherwise."""
    s = _client()
    try:
        si = s.SetupIntent.retrieve(setupintentid, expand=["payment_method"])
    except Exception as e:
        raise _friendly(e)
    if si.status != "succeeded" or not si.payment_method:
        raise BillingError("The card hasn't been verified yet.")
    pm = si.payment_method
    card = pm.card
    return {"paymentmethod": pm.id, "brand": card.brand, "last4": card.last4,
            "exp": f"{card.exp_month:02d}/{card.exp_year}"}


def create_customer(account: dict, email: str, adminname: str, paymentmethod: str) -> str:
    """The Stripe customer for a finished application, with the verified card as its default."""
    s = _client()
    try:
        customer = s.Customer.create(
            name=account["name"], email=email, phone=account.get("phone") or None,
            address={"line1": account.get("address1") or None, "line2": account.get("address2") or None,
                     "city": account.get("city") or None, "state": account.get("state") or None,
                     "postal_code": account.get("zip") or None, "country": "US"},
            metadata={"tripproof_account": account["recordid"], "account_number": str(account["accountnumber"]),
                      "admin": adminname})
        s.PaymentMethod.attach(paymentmethod, customer=customer.id)
        s.Customer.modify(customer.id, invoice_settings={"default_payment_method": paymentmethod})
    except Exception as e:
        raise _friendly(e)
    return customer.id


def ensure_price(plan: dict) -> dict:
    """The Stripe product and current monthly price for a plan, created on first use and re-created
    when the plan's price has changed (Stripe prices can't be edited). The superseded price is
    archived so it can't be picked again; existing subscriptions on it carry on unchanged.
    Returns the ids to store back on the plan."""
    s = _client()
    amount = plan["monthlyprice"]
    try:
        product = plan.get("stripeproductid")
        if not product:
            product = s.Product.create(name=f"TripProof {plan['name']}", metadata={"tripproof_plan": plan["code"]}).id
        price = plan.get("stripepriceid")
        if not price or plan.get("stripepriceamount") is None or plan["stripepriceamount"] != amount:
            new = s.Price.create(product=product, currency="usd", unit_amount=int(round(float(amount) * 100)),
                                 recurring={"interval": "month"}, metadata={"tripproof_plan": plan["code"]})
            if price:
                s.Price.modify(price, active=False)
            price = new.id
    except Exception as e:
        raise _friendly(e)
    return {"stripeproductid": product, "stripepriceid": price, "stripepriceamount": amount}


def create_subscription(customer: str, price: str, trialdays: int, accountid: str, fleetsize: int) -> dict:
    """Start the subscription on the customer's default card. If the first charge fails, Stripe
    refuses (error_if_incomplete) rather than leaving a half-made subscription."""
    s = _client()
    params = {"customer": customer, "items": [{"price": price}], "payment_behavior": "error_if_incomplete",
              "metadata": {"tripproof_account": accountid, "fleet_size": str(fleetsize)}}
    if trialdays:
        params["trial_period_days"] = trialdays
    try:
        sub = s.Subscription.create(**params)
    except Exception as e:
        raise _friendly(e)
    return _subscription(sub.to_dict())


# ------------------------------------------------------------------------------------------------
# After signup: webhooks, reading back what Stripe did, and customers changing their card
# ------------------------------------------------------------------------------------------------

def construct_event(payload: bytes, signature: str | None) -> dict:
    """A webhook event, only if Stripe signed it with our endpoint's secret. Raises ValueError."""
    try:
        event = stripe.Webhook.construct_event(payload, signature, settings.stripe_webhook_secret)
    except (stripe.SignatureVerificationError, ValueError) as e:
        raise ValueError(str(e) or "Invalid signature")
    return event.to_dict()


def _subscription(s: dict) -> dict:
    # current_period_end lives on the subscription item in current Stripe API versions.
    items = (s.get("items") or {}).get("data") or []
    period_end = (items[0].get("current_period_end") if items else None) or s.get("current_period_end")
    price = (items[0].get("price") or {}) if items else {}
    return {"id": s["id"], "status": s["status"], "customer": s.get("customer"), "trial_end": s.get("trial_end"),
            "current_period_end": period_end, "cancel_at_period_end": bool(s.get("cancel_at_period_end")),
            "canceled_at": s.get("canceled_at"), "ended_at": s.get("ended_at"), "metadata": s.get("metadata") or {},
            "price": price.get("id"), "unit_amount": price.get("unit_amount")}


def subscription(subscriptionid: str) -> dict:
    """The subscription as Stripe has it now. Webhooks can arrive out of order, so the webhook
    handler reads the current state rather than trusting the event's snapshot."""
    try:
        return _subscription(_client().Subscription.retrieve(subscriptionid).to_dict())
    except Exception as e:
        raise _friendly(e)


def _failure_message(inv: dict) -> str | None:
    """Why the last attempt to pay an invoice failed, from its payment intent (current API versions
    keep payments in invoice.payments)."""
    for p in ((inv.get("payments") or {}).get("data") or [])[::-1]:
        pi = (p.get("payment") or {}).get("payment_intent")
        err = pi.get("last_payment_error") if isinstance(pi, dict) else None
        if err:
            return (err.get("message") or err.get("code") or "")[:255] or None
    return None


def invoice(invoiceid: str) -> dict:
    """An invoice as Stripe has it now, with the reason its last payment failed if it did."""
    s = _client()
    try:
        try:
            inv = s.Invoice.retrieve(invoiceid, expand=["payments.data.payment.payment_intent"]).to_dict()
        except stripe.InvalidRequestError:
            inv = s.Invoice.retrieve(invoiceid).to_dict()
    except Exception as e:
        raise _friendly(e)
    lines = (inv.get("lines") or {}).get("data") or []
    period = (lines[0].get("period") if lines else None) or {}
    parent = ((inv.get("parent") or {}).get("subscription_details") or {})
    return {"id": inv["id"], "customer": inv.get("customer"), "number": inv.get("number"), "status": inv.get("status"),
            "subscription": inv.get("subscription") or parent.get("subscription"),
            "amount_due": (inv.get("amount_due") or 0) / 100, "amount_paid": (inv.get("amount_paid") or 0) / 100,
            "currency": inv.get("currency") or "usd", "created": inv.get("created"),
            "period_start": period.get("start") or inv.get("period_start"), "period_end": period.get("end") or inv.get("period_end"),
            "paid_at": (inv.get("status_transitions") or {}).get("paid_at"), "attempt_count": inv.get("attempt_count") or 0,
            "next_payment_attempt": inv.get("next_payment_attempt"), "hosted_invoice_url": inv.get("hosted_invoice_url"),
            "invoice_pdf": inv.get("invoice_pdf"), "failure": _failure_message(inv)}


def customer_setup_intent(customer: str, accountid: str) -> dict:
    """A SetupIntent for an existing customer changing their card; confirming it attaches the card."""
    try:
        si = _client().SetupIntent.create(customer=customer, payment_method_types=["card"], usage="off_session",
                                          metadata={"tripproof_account": accountid})
    except Exception as e:
        raise _friendly(e)
    return {"id": si.id, "client_secret": si.client_secret}


def set_default_card(customer: str, setupintentid: str) -> dict:
    """Make the card behind a confirmed SetupIntent the customer's default for invoices."""
    card = verified_card(setupintentid)
    s = _client()
    try:
        pm = s.PaymentMethod.retrieve(card["paymentmethod"])
        if pm.customer != customer:
            s.PaymentMethod.attach(card["paymentmethod"], customer=customer)
        s.Customer.modify(customer, invoice_settings={"default_payment_method": card["paymentmethod"]})
    except Exception as e:
        raise _friendly(e)
    return card


def pay_open_invoices(customer: str) -> int:
    """Try the default card on every open invoice now instead of waiting for Stripe's next retry.
    Returns how many were paid; raises (worded for the customer) if the card is declined."""
    s = _client()
    paid = 0
    try:
        for inv in s.Invoice.list(customer=customer, status="open", limit=20).auto_paging_iter():
            s.Invoice.pay(inv.id)
            paid += 1
    except Exception as e:
        raise _friendly(e)
    return paid


def dashboard_url(customer: str) -> str:
    """The customer in the Stripe dashboard (test-mode keys open the sandbox)."""
    test = settings.stripe_secret_key.startswith(("sk_test_", "rk_test_"))
    return f"https://dashboard.stripe.com/{'test/' if test else ''}customers/{customer}"


def change_price(subscriptionid: str, price: str, fleetsize: int) -> dict:
    """Move a subscription to another plan's price from the next invoice on. No proration: the
    current period was billed at the old plan, and the fleet size is re-checked before each renewal."""
    s = _client()
    try:
        sub = s.Subscription.retrieve(subscriptionid)
        item = sub["items"]["data"][0]
        sub = s.Subscription.modify(subscriptionid, items=[{"id": item.id, "price": price}], proration_behavior="none",
                                    metadata={"fleet_size": str(fleetsize)})
    except Exception as e:
        raise _friendly(e)
    return _subscription(sub.to_dict())


def charge_next_invoice(customer: str, cents: int, description: str, accountid: str) -> str | None:
    """Put one charge on this customer's NEXT monthly invoice.

    TripProof pays the vendor at the moment of ordering and recovers it from the account later, so
    nothing is taken from a card here: this adds a line that Stripe picks up when the subscription
    invoice is next drawn. A company ordering four screenings in a month sees four lines and one
    payment.

    Returns the invoice item's id, or None where billing is not configured - an installation
    without Stripe still orders screenings, it simply does not bill for them."""
    if not configured() or not customer:
        return None
    _client()
    try:
        item = stripe.InvoiceItem.create(
            customer=customer, amount=int(cents), currency="usd",
            description=description[:500],
            metadata={"accountid": accountid, "kind": "background-screening"},
        )
        return item["id"]
    except Exception as e:
        raise _friendly(e) from e


def cancel_invoice_item(itemid: str | None) -> None:
    """Take a charge back off the next invoice.

    Used where an order was placed, charged and then could not be run. A credit note on an invoice
    nobody has been shown yet is just a line that should never have been there."""
    if not itemid or not configured():
        return
    _client()
    try:
        stripe.InvoiceItem.delete(itemid)
    except Exception as e:  # already invoiced, already gone - not worth failing the caller over
        log.warning("could not remove invoice item %s: %s", itemid, e)
