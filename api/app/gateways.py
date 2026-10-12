"""Payment gateways - the processor a company charges a private-pay passenger through.

Not TripProof's own Stripe account, which charges companies their subscription. This is the
company's own merchant account, and the keys below are theirs.

Three rules hold this together:

  * A SECRET IS WRITE-ONLY. Nothing here ever returns a secret to a caller, including the
    company that typed it. What comes back is whether a field is set and the last four
    characters, which is enough to tell "the key I pasted" from "the key from two years ago"
    and no help at all to anybody who should not have it.
  * A BLANK SECRET MEANS "LEAVE IT". Editing the mode must not silently wipe a key, so a
    field sent empty keeps whatever is already sealed.
  * THE ADAPTERS LIVE IN CODE. What a processor needs is a property of its API, not a row
    somebody has to migrate when Square adds a field.

Nothing here charges a card. It is the configuration, and it is deliberately the whole of
this change: taking a payment means an adapter per processor, a charge record that cites the
schedule it was priced from, and a refund path - and none of that is worth writing on top of
credentials nobody has stored yet.
"""

from sqlalchemy.engine import Connection

from app import crypto
from app.db import newid, row, rows, run, utcnow

MODES = {"test": "Test / sandbox", "live": "Live"}


def _f(name, label, secret=False, hint=None, optional=False):
    return {"name": name, "label": label, "secret": secret, "hint": hint, "optional": optional}


# What each processor needs to be talked to. Ordered as its own dashboard presents them, so
# somebody copying from one screen to the other is not hunting.
#
# `secret` is the whole security model of this module: those fields are sealed, never
# returned, and kept when sent blank. Everything else is a public identifier - a publishable
# key, a merchant number - and is held and shown in the clear, because it already is.
ADAPTERS = {
    "stripe": {
        "name": "Stripe",
        "note": "Cards, Apple Pay and Google Pay. Keys are under Developers > API keys.",
        "fields": [
            _f("publishable_key", "Publishable key", hint="pk_live_… or pk_test_…"),
            _f("secret_key", "Secret key", secret=True, hint="sk_live_… or sk_test_…"),
            _f("webhook_secret", "Webhook signing secret", secret=True, optional=True,
               hint="whsec_… - needed before Stripe can tell us a payment settled"),
        ],
    },
    "authorizenet": {
        "name": "Authorize.Net",
        "note": "Account > Settings > API Credentials & Keys.",
        "fields": [
            _f("login_id", "API login ID"),
            _f("transaction_key", "Transaction key", secret=True),
            _f("signature_key", "Signature key", secret=True, optional=True,
               hint="Used to check that a webhook really came from Authorize.Net"),
        ],
    },
    "square": {
        "name": "Square",
        "note": "Developer dashboard > your application > Credentials.",
        "fields": [
            _f("application_id", "Application ID"),
            _f("location_id", "Location ID", hint="Which of your locations the trip is sold at"),
            _f("access_token", "Access token", secret=True),
        ],
    },
    "nmi": {
        "name": "NMI",
        "note": "Also sold white-labelled - a gateway that asks for a 'security key' is "
                "usually this one.",
        "fields": [
            _f("security_key", "Security key", secret=True),
            _f("tokenization_key", "Public tokenization key", optional=True,
               hint="Lets the card be collected in the browser without touching our server"),
        ],
    },
    "braintree": {
        "name": "Braintree",
        "note": "A PayPal company. Settings > API keys.",
        "fields": [
            _f("merchant_id", "Merchant ID"),
            _f("public_key", "Public key"),
            _f("private_key", "Private key", secret=True),
        ],
    },
    "paypal": {
        "name": "PayPal",
        "note": "Developer dashboard > Apps & Credentials.",
        "fields": [
            _f("client_id", "Client ID"),
            _f("client_secret", "Client secret", secret=True),
        ],
    },
    "elavon": {
        "name": "Elavon Converge",
        "fields": [
            _f("merchant_id", "Merchant ID"),
            _f("user_id", "Converge user ID"),
            _f("pin", "PIN", secret=True),
        ],
    },
    "cardconnect": {
        "name": "Fiserv CardConnect",
        "fields": [
            _f("merchant_id", "Merchant ID"),
            _f("username", "API username"),
            _f("password", "API password", secret=True),
        ],
    },
    "globalpayments": {
        "name": "Global Payments",
        "note": "Heartland merchants are on this one.",
        "fields": [
            _f("app_id", "App ID"),
            _f("app_key", "App key", secret=True),
        ],
    },
    "usaepay": {
        "name": "USAePay",
        "fields": [
            _f("source_key", "Source key"),
            _f("pin", "Source PIN", secret=True),
        ],
    },
    "cardknox": {
        "name": "Cardknox",
        "fields": [
            _f("transaction_key", "Transaction key", secret=True),
            _f("ifields_key", "iFields key", optional=True,
               hint="Lets the card be collected in the browser without touching our server"),
        ],
    },
    "helcim": {
        "name": "Helcim",
        "fields": [
            _f("account_id", "Account ID"),
            _f("api_token", "API token", secret=True),
        ],
    },
    "clover": {
        "name": "Clover",
        "fields": [
            _f("merchant_id", "Merchant ID"),
            _f("api_token", "API token", secret=True),
        ],
    },
    "adyen": {
        "name": "Adyen",
        "fields": [
            _f("merchant_account", "Merchant account"),
            _f("client_key", "Client key"),
            _f("api_key", "API key", secret=True),
        ],
    },
    "worldpay": {
        "name": "Worldpay",
        "fields": [
            _f("merchant_code", "Merchant code"),
            _f("service_key", "Service key", secret=True),
        ],
    },
    "stax": {
        "name": "Stax",
        "note": "Formerly Fattmerchant.",
        "fields": [
            _f("api_key", "API key", secret=True),
            _f("web_payments_token", "Web payments token", optional=True),
        ],
    },
    "payjunction": {
        "name": "PayJunction",
        "fields": [
            _f("app_key", "Application key"),
            _f("api_login", "API login"),
            _f("api_password", "API password", secret=True),
        ],
    },
}

# The order they are offered in. Roughly how likely a small NEMT operator is to already be on
# one, which is the only ordering that saves anybody a scroll.
ORDER = ["stripe", "square", "authorizenet", "nmi", "braintree", "paypal", "helcim", "clover",
         "elavon", "globalpayments", "cardconnect", "usaepay", "cardknox", "stax",
         "payjunction", "adyen", "worldpay"]


def _aad(accountid: str, code: str) -> str:
    """Binds a sealed blob to one account and one adapter.

    Without it a ciphertext copied from another row would open perfectly well in this one.
    """
    return f"gateway:{accountid}:{code}"


def _hint(value: str) -> str:
    """The tail of a secret, which is how a human tells one key from another."""
    v = (value or "").strip()
    return f"••••{v[-4:]}" if len(v) >= 4 else "••••"


def catalog(conn: Connection) -> list[dict]:
    """Every adapter TripProof knows, with the platform's switch on each."""
    held = {r["code"]: r for r in rows(conn, "SELECT * FROM paymentgateways")}
    out = []
    for n, code in enumerate(ORDER):
        a = ADAPTERS[code]
        r = held.get(code) or {}
        out.append({
            "code": code, "name": a["name"], "note": a.get("note"),
            # Unknown to the table means offered. A new adapter should not need a row written
            # before anybody can use it.
            "active": bool(r.get("active", 1)),
            "sortorder": r.get("sortorder", n),
            "platformnote": r.get("note"),
            "fields": a["fields"],
            "secrets": sum(1 for f in a["fields"] if f["secret"]),
        })
    out.sort(key=lambda x: (x["sortorder"], ORDER.index(x["code"])))
    return out


def offered(conn: Connection) -> list[dict]:
    """The adapters a company may actually choose, in order."""
    return [g for g in catalog(conn) if g["active"]]


def set_offered(conn: Connection, code: str, active: bool, note: str | None = None) -> None:
    if code not in ADAPTERS:
        raise KeyError(code)
    run(conn, """
        INSERT INTO paymentgateways (code, active, sortorder, note, updated)
        VALUES (:c, :a, :o, :n, :now)
        ON DUPLICATE KEY UPDATE active = VALUES(active), note = VALUES(note),
                                updated = VALUES(updated)
    """, c=code, a=1 if active else 0, o=ORDER.index(code),
        n=(note or "").strip()[:255] or None, now=utcnow())


# -------------------------------------------------------------------------------------------
# A company's own configuration.
# -------------------------------------------------------------------------------------------

def _unseal(r: dict, accountid: str) -> dict:
    if not r.get("credentials"):
        return {}
    return crypto.open_json(r["keyversion"], r["credentials"],
                            _aad(accountid, r["gatewaycode"])) or {}


def _public(r: dict, accountid: str) -> dict:
    """One configured gateway, with every secret replaced by the fact that it is set.

    This is the only shape that leaves this module. There is deliberately no function that
    returns a company's secrets to a caller outside it - when a charge is finally built, it
    will ask this module to make the call, not for the key to make it with.
    """
    a = ADAPTERS[r["gatewaycode"]]
    creds = _unseal(r, accountid)
    values, state = {}, {}
    for f in a["fields"]:
        v = creds.get(f["name"]) or ""
        if f["secret"]:
            state[f["name"]] = {"set": bool(v), "hint": _hint(v) if v else None}
        else:
            values[f["name"]] = v
    return {
        "recordid": r["recordid"], "code": r["gatewaycode"], "name": a["name"],
        "mode": r["mode"], "active": bool(r["active"]),
        "values": values, "secrets": state,
        "added": r["added"], "updated": r["updated"],
        # What it cannot do yet, said by the thing that knows: every required field answered.
        "ready": all(
            (creds.get(f["name"]) or "").strip()
            for f in a["fields"] if not f["optional"]),
    }


def configured(conn: Connection, accountid: str) -> list[dict]:
    return [_public(r, accountid) for r in rows(conn, """
        SELECT * FROM accountgateways WHERE accountid = :a ORDER BY active DESC, added
    """, a=accountid) if r["gatewaycode"] in ADAPTERS]


def chosen(conn: Connection, accountid: str) -> dict | None:
    """The gateway this company takes private payments through, if it has said."""
    r = row(conn, """
        SELECT * FROM accountgateways WHERE accountid = :a AND active = 1 LIMIT 1
    """, a=accountid)
    return _public(r, accountid) if r and r["gatewaycode"] in ADAPTERS else None


def save(conn: Connection, accountid: str, userid: str, code: str, body: dict) -> str:
    """Write a company's configuration for one adapter.

    A secret sent blank keeps what is already sealed - the alternative is that opening this
    screen to change the mode and pressing Save silently empties the keys.
    """
    if code not in ADAPTERS:
        raise KeyError(code)
    a = ADAPTERS[code]
    held = row(conn, """
        SELECT * FROM accountgateways WHERE accountid = :a AND gatewaycode = :c
    """, a=accountid, c=code)
    creds = _unseal(held, accountid) if held else {}

    sent = body.get("values") or {}
    for f in a["fields"]:
        v = (sent.get(f["name"]) or "").strip()
        if f["secret"] and not v:
            continue                      # blank means "leave it"
        if v:
            creds[f["name"]] = v
        else:
            creds.pop(f["name"], None)    # a public field really can be cleared

    version, sealed = crypto.seal_json(creds, _aad(accountid, code))
    mode = body.get("mode") if body.get("mode") in MODES else "test"
    recordid = held["recordid"] if held else newid()
    if held:
        run(conn, """
            UPDATE accountgateways SET mode = :m, keyversion = :v, credentials = :c,
                   updated = :now
            WHERE recordid = :i
        """, i=recordid, m=mode, v=version, c=sealed, now=utcnow())
    else:
        run(conn, """
            INSERT INTO accountgateways (recordid, accountid, gatewaycode, mode, keyversion,
                                         credentials, active, addedby)
            VALUES (:i, :a, :g, :m, :v, :c, 0, :by)
        """, i=recordid, a=accountid, g=code, m=mode, v=version, c=sealed, by=userid)
    return recordid


def use(conn: Connection, accountid: str, code: str) -> None:
    """Make this the one private payments go through. There can only be one."""
    run(conn, "UPDATE accountgateways SET active = 0, updated = :now WHERE accountid = :a",
        a=accountid, now=utcnow())
    run(conn, """
        UPDATE accountgateways SET active = 1, updated = :now
        WHERE accountid = :a AND gatewaycode = :c
    """, a=accountid, c=code, now=utcnow())


def forget(conn: Connection, accountid: str, code: str) -> bool:
    """Delete a configuration, keys and all.

    Deleted rather than deactivated, unlike almost everything else here. A row kept "for the
    record" is a merchant key still sitting in the database after somebody asked for it to be
    taken out, and no audit question is worth that.
    """
    return bool(run(conn, """
        DELETE FROM accountgateways WHERE accountid = :a AND gatewaycode = :c
    """, a=accountid, c=code).rowcount)


def summary(conn: Connection, accountid: str) -> dict:
    """What the screen needs: the choices, the configurations, and the one in use."""
    return {
        "modes": MODES,
        "available": offered(conn),
        "configured": configured(conn, accountid),
        "chosen": (chosen(conn, accountid) or {}).get("code"),
    }


def describe(code: str) -> str:
    return ADAPTERS[code]["name"] if code in ADAPTERS else code


__all__ = ["ADAPTERS", "MODES", "ORDER", "catalog", "chosen", "configured", "describe",
           "forget", "offered", "save", "set_offered", "summary", "use"]
