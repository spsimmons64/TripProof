###################################################################################################
# A company's own account with backgroundchecks.com.
#
# WHY A COMPANY HAS ONE AT ALL. Under the FCRA the party that obtains a consumer report for
# employment purposes has to be the party evaluating the consumer for employment - §603(h) - and
# that is the transport company deciding whether to hire the driver. Not the software it decides
# with. If TripProof's account placed the order, TripProof would be certifying under §604(b)(1)
# that it had made a disclosure and would run adverse action, neither of which it can do, and
# passing the finished report on would make it a reseller under §603(u) with everything §607 and
# §611 then ask of one.
#
# So each company signs up for itself, through their Create Account widget. Their name goes on the
# disclosure the driver signs, their certification is the one on file, and they are billed by
# backgroundchecks.com directly. TripProof holds the key and gets out of the way.
#
# HOW THE KEY IS KEPT. Sealed, in `accountgateways`, with the same envelope the payment gateways
# use: AES through app.crypto, versioned, bound by AAD to this account and this code so a
# ciphertext lifted from another row cannot be opened in this one. The table is reused rather than
# copied because it already is "one company's sealed credentials for an outside service", and the
# Merchant Connect screen filters to its own adapter list, so this row cannot appear on it.
###################################################################################################
from sqlalchemy.engine import Connection

from app import backgroundchecks, crypto
from app.db import newid, row, run, utcnow

CODE = "backgroundchecks"


def _aad(accountid: str) -> str:
    return f"{accountid}:{CODE}"


def _held(conn: Connection, accountid: str) -> dict | None:
    return row(conn, """
        SELECT recordid, keyversion, credentials, added, updated FROM accountgateways
        WHERE accountid = :a AND gatewaycode = :c
    """, a=accountid, c=CODE)


def token_for(conn: Connection, accountid: str) -> str | None:
    """This company's own API token, or None if they have not signed up.

    None is a real answer and callers must handle it: a company with no account of its own cannot
    order, and must not quietly fall through to somebody else's."""
    held = _held(conn, accountid)
    if not held or not held["credentials"]:
        return None
    creds = crypto.open_json(held["keyversion"], held["credentials"], _aad(accountid)) or {}
    return creds.get("api_token") or None


def connected(conn: Connection, accountid: str) -> bool:
    return bool(token_for(conn, accountid))


def adopt(conn: Connection, accountid: str, userid: str, sealed_token: str) -> None:
    """Claim the account the Create Account widget has just made, and keep its key.

    The widget hands back an ENCRYPTED token. Turning it into an API key needs the platform's
    private key, which is why that happens on the server - anybody holding it could adopt accounts
    in this product's name."""
    api_token = backgroundchecks.adopt_account(sealed_token)
    keep(conn, accountid, userid, api_token)


def keep(conn: Connection, accountid: str, userid: str, api_token: str) -> None:
    version, sealed = crypto.seal_json({"api_token": api_token}, _aad(accountid))
    held = _held(conn, accountid)
    if held:
        run(conn, """
            UPDATE accountgateways SET keyversion = :v, credentials = :c, updated = :now
            WHERE recordid = :i
        """, i=held["recordid"], v=version, c=sealed, now=utcnow())
    else:
        run(conn, """
            INSERT INTO accountgateways (recordid, accountid, gatewaycode, mode, keyversion,
                                         credentials, active, addedby)
            VALUES (:i, :a, :g, 'live', :v, :c, 0, :by)
        """, i=newid(), a=accountid, g=CODE, v=version, c=sealed, by=userid)


def forget(conn: Connection, accountid: str) -> bool:
    """Disconnect. The account at the vendor is untouched - it is theirs, not ours - and this only
    stops TripProof holding the key to it."""
    return bool(run(conn, "DELETE FROM accountgateways WHERE accountid = :a AND gatewaycode = :c",
                    a=accountid, c=CODE))
