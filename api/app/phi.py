###################################################################################################
# PHI rows - the only way anything reads or writes the `phi` table. Every read that returns PHI to
# a caller is expected to be logged by that caller with phi=True.
###################################################################################################
from sqlalchemy.engine import Connection

from app import crypto
from app.db import newid, row, rows, run


def _aad(ownertype: str, ownerid: str) -> str:
    return f"{ownertype}:{ownerid}"


def put(conn: Connection, accountid: str, ownertype: str, ownerid: str, payload: dict):
    version, sealed = crypto.seal_json(payload, _aad(ownertype, ownerid))
    run(conn, """
        INSERT INTO phi (recordid, accountid, ownertype, ownerid, keyversion, payload)
        VALUES (:id, :acct, :otype, :oid, :v, :p)
        ON DUPLICATE KEY UPDATE keyversion = VALUES(keyversion), payload = VALUES(payload)
    """, id=newid(), acct=accountid, otype=ownertype, oid=ownerid, v=version, p=sealed)


def get(conn: Connection, accountid: str, ownertype: str, ownerid: str) -> dict | None:
    r = row(conn, """
        SELECT keyversion, payload FROM phi
        WHERE accountid = :acct AND ownertype = :otype AND ownerid = :oid
    """, acct=accountid, otype=ownertype, oid=ownerid)
    return crypto.open_json(r["keyversion"], r["payload"], _aad(ownertype, ownerid)) if r else None


def get_many(conn: Connection, accountid: str, ownertype: str, ownerids: list[str]) -> dict[str, dict]:
    if not ownerids:
        return {}
    out = {}
    # Chunked so a 10,000-trip packet does not build one enormous IN list.
    for i in range(0, len(ownerids), 500):
        chunk = ownerids[i:i + 500]
        params = {f"o{n}": oid for n, oid in enumerate(chunk)}
        placeholders = ", ".join(f":o{n}" for n in range(len(chunk)))
        for r in rows(conn, f"""
            SELECT ownerid, keyversion, payload FROM phi
            WHERE accountid = :acct AND ownertype = :otype AND ownerid IN ({placeholders})
        """, acct=accountid, otype=ownertype, **params):
            out[r["ownerid"]] = crypto.open_json(r["keyversion"], r["payload"], _aad(ownertype, r["ownerid"]))
    return out


def delete(conn: Connection, accountid: str, ownertype: str, ownerid: str):
    run(conn, "DELETE FROM phi WHERE accountid = :acct AND ownertype = :otype AND ownerid = :oid",
        acct=accountid, otype=ownertype, oid=ownerid)
