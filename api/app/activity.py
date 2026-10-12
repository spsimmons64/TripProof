###################################################################################################
# Activity log - who did what to which record, and whether PHI was exposed. The table is
# append-only (triggers refuse UPDATE/DELETE), which is what makes it usable as a HIPAA access log.
###################################################################################################
import json

from sqlalchemy.engine import Connection

from app.db import newid, run


def log(conn: Connection, user: dict | None, action: str, entitytype: str | None = None,
        entityid: str | None = None, detail: dict | None = None, phi: bool = False,
        ip: str | None = None, accountid: str | None = None):
    run(conn, """
        INSERT INTO activitylog (recordid, accountid, userid, action, entitytype, entityid, phi, detail, ip)
        VALUES (:id, :acct, :uid, :action, :etype, :eid, :phi, :detail, :ip)
    """, id=newid(), acct=accountid or (user or {}).get("accountid"), uid=(user or {}).get("recordid"),
        action=action, etype=entitytype, eid=entityid, phi=1 if phi else 0,
        detail=json.dumps(detail, default=str) if detail else None, ip=ip)
