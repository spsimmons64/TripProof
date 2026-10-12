###################################################################################################
# What has changed since you last looked.
#
# One endpoint, deliberately: a client asks for everything after its cursor and is told where the
# cursor is now. The answer carries ids, not content - so this can be served to a polling client
# today, streamed as server-sent events when the office wants it instant, and pushed down a socket
# if a dispatch console is ever built, without the client's question changing.
###################################################################################################
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from app import certn, events
from app.db import get_conn, row, saved
from app.security import current_user, editor

router = APIRouter(prefix="/api", tags=["live"])


@router.get("/events")
def what_changed(since: int | None = None, subject: str | None = None, subjectid: str | None = None,
                 user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Events for this account only - the account is taken from the session, never from the query,
    so one company cannot ask what another company's drivers have been doing."""
    return events.since(conn, user["accountid"], since, subject, subjectid)


@router.get("/arrivals")
def waiting_to_be_read(user: dict = Depends(current_user), conn: Connection = Depends(get_conn)):
    """Documents that came in on their own and nobody has read yet."""
    return {"items": events.waiting_to_be_read(conn, user["accountid"])}


@router.post("/arrivals/{recordid}/reviewed")
def mark_reviewed(recordid: str, user: dict = Depends(editor), conn: Connection = Depends(get_conn)):
    """Somebody has read it - and it matters who.

    Reviewing is an act of the company: it is the carrier that has to have looked at what arrived,
    and the carrier that answers for it. TripProof staff read the same documents while helping, and
    their reading is not the company's. So a staff session opens the document and changes nothing:
    the arrival stays in the queue until somebody who works there has seen it."""
    if user.get("platformrole"):
        return {"ok": True, "reviewed": False, "why": "staff"}
    if not events.mark_read(conn, user["accountid"], recordid, user["recordid"]):
        raise HTTPException(404, "No such arrival, or it has already been reviewed")
    saved(conn)
    return {"ok": True, "reviewed": True}


@router.post("/webhooks/certn")
async def certn_said(request: Request, conn: Connection = Depends(get_conn)):
    """Certn telling us an order has moved. Public by necessity, so it proves who it is.

    Matched on THEIR reference, which is the only thread between an order placed this morning and a
    result arriving tonight. An unknown reference is answered 200 and ignored: a webhook retried
    for ever because we said 404 to something that is not ours helps nobody.

    The result is filed and left needing to be read. Certn says what it found; whether that
    disqualifies a driver is the company's judgement, not ours and not theirs."""
    body = await request.body()
    if not certn.signature_ok(body, request.headers.get("Certn-Signature")):
        raise HTTPException(401, "Not from Certn")
    try:
        said = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(400, "Unreadable") from None
    ref = str(said.get("id") or said.get("applicant_id") or said.get("application_id") or "")
    if not ref:
        return {"ok": True}
    held = row(conn, """
        SELECT recordid, accountid, driverid FROM driverreports
        WHERE vendor = 'certn' AND vendorref = :ref
    """, ref=ref)
    if not held:
        return {"ok": True}
    from app.routers.vault import _land_screening
    _land_screening(conn, held["accountid"], held["driverid"], held["recordid"], ref,
                    certn.read_status(said))
    saved(conn)
    return {"ok": True}
