"""The payment portal: a passenger pays an invoice, with no login.

Each company has its own page. A link or QR code carries a long private code straight to one invoice;
someone typing from paper gives the invoice number and billing ZIP. It shows that invoice and nothing
else. Paying goes to the company's own merchant account on the processor's hosted page, and only the
processor's word marks an invoice paid: never the browser's. Full balance only.
"""

import time
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import emails, gateways, mailer
from app.activity import log
from app.config import settings
from app.db import get_conn, newid, row, rows, run, saved, utcnow
from app.routers.tripbilling import ORDER_LINES, balance, invoice_pdf, pay_link

router = APIRouter(prefix="/api/pay", tags=["pay"])

# Guessing invoice numbers and ZIPs is slowed down: this many tries, per address, per ten minutes.
TRIES, WINDOW = 10, 600
_tried: dict[str, list[float]] = {}


def _company(conn: Connection, where: str, **kw) -> dict:
    got = row(conn, f"SELECT recordid, accountnumber, name, phone, billingemail FROM accounts WHERE {where}", **kw)
    if not got:
        raise HTTPException(404, "No such company")
    return got


@router.get("/account/{accountnumber}")
def account(accountnumber: str, conn: Connection = Depends(get_conn)):
    c = _company(conn, "accountnumber = :n AND status IN ('active', 'setup')", n=accountnumber)
    return {"name": c["name"], "phone": c["phone"]}


class FindIn(BaseModel):
    invoice: int
    zip: str


@router.post("/account/{accountnumber}/find")
def find(accountnumber: str, body: FindIn, request: Request, conn: Connection = Depends(get_conn)):
    """The invoice number and ZIP from paper, to the invoice. The same answer whichever was wrong."""
    who = request.client.host if request.client else "?"
    now = time.time()
    recent = [t for t in _tried.get(who, []) if now - t < WINDOW]
    if len(recent) >= TRIES:
        raise HTTPException(429, "Too many tries. Wait a few minutes, or call the company.")
    _tried[who] = recent + [now]
    c = _company(conn, "accountnumber = :n", n=accountnumber)
    inv = row(conn, "SELECT paytoken, billtoaddress FROM tripinvoices WHERE accountid = :a AND number = :n", a=c["recordid"], n=body.invoice)
    zipcode = "".join(ch for ch in body.zip if ch.isdigit())[:5]
    if not inv or len(zipcode) != 5 or zipcode not in (inv["billtoaddress"] or ""):
        raise HTTPException(404, "We could not find that invoice. Check the number and the ZIP on it.")
    return {"token": inv["paytoken"]}


def _invoice(conn: Connection, token: str) -> dict:
    inv = row(conn, """
        SELECT i.*, t.billingstatus, t.billinvoiceid, t.externalid, t.tripdate FROM tripinvoices i JOIN trips t ON t.recordid = i.tripid
        WHERE i.paytoken = :t
    """, t=token)
    if not inv:
        raise HTTPException(404, "We could not find that invoice.")
    return inv


@router.get("/invoice/{token}")
def invoice(token: str, conn: Connection = Depends(get_conn)):
    inv = _invoice(conn, token)
    c = _company(conn, "recordid = :a", a=inv["accountid"])
    owed = balance(conn, inv)
    replaced = inv["billinvoiceid"] != inv["recordid"]
    return {"company": c["name"], "phone": c["phone"], "accountnumber": c["accountnumber"], "number": inv["number"], "issuedon": inv["issuedon"],
            "billto": inv["billtoname"], "needsemail": not inv["billtoemail"], "amount": float(inv["amount"]), "balance": float(owed), "replaced": replaced,
            "lines": [{"label": x["label"], "amount": float(x["amount"])} for x in rows(
                conn, "SELECT label, amount FROM tripcharges WHERE invoiceid = :i ORDER BY " + ORDER_LINES, i=inv["recordid"])],
            "canpay": not replaced and owed > 0 and inv["billingstatus"] == "billed" and gateways.can_take_payment(conn, inv["accountid"])}


@router.get("/invoice/{token}/pdf")
def invoice_file(token: str, conn: Connection = Depends(get_conn)):
    inv = _invoice(conn, token)
    return Response(invoice_pdf(conn, inv["accountid"], [inv["recordid"]]), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="invoice-{inv["number"]}.pdf"'})


class CheckoutIn(BaseModel):
    email: str | None = None


@router.post("/invoice/{token}/checkout")
def checkout(token: str, body: CheckoutIn | None = None, conn: Connection = Depends(get_conn)):
    """To the processor's page for the whole balance. No part payments. With no email on file, one
    is required here and kept: for the receipt, and for the passenger's next invoice."""
    inv = _invoice(conn, token)
    owed = balance(conn, inv)
    if not inv["billtoemail"] and owed > 0:
        email = ((body.email if body else None) or "").strip().lower()[:255]
        if "@" not in email or " " in email or "." not in email.rsplit("@", 1)[-1]:
            raise HTTPException(400, "Give your email address, for the receipt.")
        run(conn, "UPDATE tripinvoices SET billtoemail = :e WHERE recordid = :i", e=email, i=inv["recordid"])
        # On the passenger too, unless the office has filled one in meanwhile; a billing contact's
        # address goes on the contact.
        t = row(conn, "SELECT passenger FROM trips WHERE recordid = :t", t=inv["tripid"])
        run(conn, """UPDATE passengers SET billingemail = IF(billingname IS NOT NULL, :e, billingemail), email = IF(billingname IS NULL, :e, email)
                     WHERE accountid = :a AND name = :n AND deleted IS NULL AND email IS NULL AND billingemail IS NULL""",
            e=email, a=inv["accountid"], n=t["passenger"])
        saved(conn)
        inv["billtoemail"] = email
    if inv["billinvoiceid"] != inv["recordid"] or inv["billingstatus"] != "billed" or owed <= 0:
        raise HTTPException(409, "This invoice has nothing to pay.")
    if not gateways.can_take_payment(conn, inv["accountid"]):
        raise HTTPException(409, "This company does not take payments online yet.")
    c = _company(conn, "recordid = :a", a=inv["accountid"])
    back = pay_link(c["accountnumber"], token)
    if settings.pay_simulator and not gateways.has_stripe(conn, inv["accountid"]):
        return {"url": back + "/simulate"}
    try:
        url = gateways.stripe_checkout(conn, inv["accountid"], cents=int(owed * 100), label=f"{c['name']} invoice {inv['number']}",
                                       success=back + "?session={CHECKOUT_SESSION_ID}", cancel=back, email=inv["billtoemail"], reference=token)
    except Exception as e:                                                    # noqa: BLE001
        raise HTTPException(502, "The payment page could not be opened. Try again, or call the company.") from e
    return {"url": url}


def _receipt(to: str, company: str, number: int, amount: Decimal) -> None:
    body = emails.p(f"{emails.escape(company)} received your payment of <strong>${amount:,.2f}</strong> for invoice {number}. Thank you.")
    html = emails.layout(preheader=f"Payment received for invoice {number}.", heading="Payment Received", body=body,
                         footer_note=f"Sent for {emails.escape(company)}.")
    mailer.send(to, f"Payment received - invoice {number}", html, f"{company} received your payment of ${amount:,.2f} for invoice {number}. Thank you.")


def _settle(conn: Connection, inv: dict, ref: str, cents: int, tasks: BackgroundTasks | None, note: str = "PAID ONLINE") -> bool:
    """A paid session, on the processor's word. Told twice, it counts once."""
    if row(conn, "SELECT 1 AS x FROM billpayments WHERE accountid = :a AND processorref = :r", a=inv["accountid"], r=ref):
        return False
    amount = (Decimal(cents) / 100).quantize(Decimal("0.01"))
    run(conn, """INSERT INTO billpayments (recordid, accountid, tripid, amount, denied, note, processorref, recordedon, recordedby)
                 VALUES (:i, :a, :t, :m, 0, :note, :r, :now, 'online')""",
        i=newid(), a=inv["accountid"], t=inv["tripid"], m=amount, note=note, r=ref, now=utcnow())
    run(conn, "UPDATE trips SET billingstatus = 'paid', updated = :now WHERE recordid = :t AND billingstatus = 'billed'", now=utcnow(), t=inv["tripid"])
    log(conn, None, "invoice-paid-online", "trip", inv["tripid"], {"invoice": inv["number"], "amount": str(amount)})
    saved(conn)
    if tasks and inv["billtoemail"]:
        c = _company(conn, "recordid = :a", a=inv["accountid"])
        tasks.add_task(_receipt, inv["billtoemail"], c["name"], inv["number"], amount)
    return True


@router.post("/invoice/{token}/confirm/{session}")
def confirm(token: str, session: str, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    """Back from the payment page: ask the processor, so a paid invoice shows at once even where the
    webhook is not set up or is late."""
    inv = _invoice(conn, token)
    try:
        got = gateways.stripe_session(conn, inv["accountid"], session)
    except Exception as e:                                                    # noqa: BLE001
        raise HTTPException(502, "We could not confirm the payment yet.") from e
    if got["reference"] != token or not got["paid"]:
        return {"paid": False}
    _settle(conn, inv, got["id"], got["cents"], tasks)
    return {"paid": True}


@router.post("/invoice/{token}/simulate")
def simulate(token: str, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    """The pretend processor saying the payment went through. Does not exist unless switched on."""
    if not settings.pay_simulator:
        raise HTTPException(404, "Not found")
    inv = _invoice(conn, token)
    owed = balance(conn, inv)
    if inv["billinvoiceid"] != inv["recordid"] or inv["billingstatus"] != "billed" or owed <= 0:
        raise HTTPException(409, "This invoice has nothing to pay.")
    _settle(conn, inv, "sim_" + newid(), int(owed * 100), tasks, note="SIMULATED PAYMENT - NO MONEY MOVED")
    return {"paid": True}


@router.post("/webhook/{accountnumber}")
async def webhook(accountnumber: str, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    """The company's own Stripe account saying a payment went through. Its signature is the proof."""
    c = _company(conn, "accountnumber = :n", n=accountnumber)
    payload = await request.body()
    try:
        event = gateways.stripe_event(conn, c["recordid"], payload, request.headers.get("stripe-signature"))
    except Exception as e:                                                    # noqa: BLE001
        raise HTTPException(400, "Bad signature") from e
    if event.get("type") == "checkout.session.completed":
        s = event["data"]["object"]
        inv = row(conn, "SELECT * FROM tripinvoices WHERE paytoken = :t AND accountid = :a", t=s.get("client_reference_id"), a=c["recordid"])
        if inv and s.get("payment_status") == "paid":
            _settle(conn, inv, s["id"], s["amount_total"], tasks)
    return {"ok": True}
