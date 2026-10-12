###################################################################################################
# Subscription plans - fleet-size tiers. A customer's plan follows from their vehicle count: the
# active tier whose range contains it. Tiers without a price are "contact us" (shown, not sold online).
###################################################################################################
import json

from fastapi import HTTPException
from sqlalchemy.engine import Connection

from app.db import row, rows


def _shape(p: dict) -> dict:
    p = dict(p)
    p["features"] = json.loads(p["features"]) if p.get("features") else []
    p["contact"] = p["monthlyprice"] is None
    return p


def active_plans(conn: Connection) -> list[dict]:
    return [_shape(p) for p in rows(conn, """
        SELECT recordid, code, name, description, minvehicles, maxvehicles, monthlyprice, trialdays, features, sortorder
        FROM plans WHERE active = 1 ORDER BY sortorder, minvehicles
    """)]


def plan_for_fleet(conn: Connection, fleetsize: int) -> dict | None:
    p = row(conn, """
        SELECT * FROM plans
        WHERE active = 1 AND minvehicles <= :n AND (maxvehicles IS NULL OR maxvehicles >= :n)
        ORDER BY minvehicles DESC LIMIT 1
    """, n=fleetsize)
    return _shape(p) if p else None


def check_no_overlap(conn: Connection, minv: int, maxv: int | None, active: bool, planid: str | None = None):
    """Active tiers may not share a vehicle count, or a fleet would match two plans."""
    if not active:
        return
    clash = row(conn, """
        SELECT name FROM plans
        WHERE active = 1 AND (:id IS NULL OR recordid <> :id)
          AND minvehicles <= COALESCE(:maxv, 2147483647) AND COALESCE(maxvehicles, 2147483647) >= :minv
        LIMIT 1
    """, id=planid, minv=minv, maxv=maxv)
    if clash:
        raise HTTPException(409, f"That vehicle range overlaps the active “{clash['name']}” plan")
