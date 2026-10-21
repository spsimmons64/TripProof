###################################################################################################
# What has changed since you last looked.
#
# One endpoint, deliberately: a client asks for everything after its cursor and is told where the
# cursor is now. The answer carries ids, not content - so this can be served to a polling client
# today, streamed as server-sent events when the office wants it instant, and pushed down a socket
# if a dispatch console is ever built, without the client's question changing.
###################################################################################################
import json
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from app import backgroundchecks, certn, events, screeningaccount
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

    Certn is no longer the vendor new orders go to - backgroundchecks.com is, and it has no webhook
    of its own. This stays because an order placed at Certn before the change can still finish, and
    a result that arrives with nowhere to land is a driver whose file never completes.

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
                    certn.read_status(said), "certn")
    saved(conn)
    return {"ok": True}


@router.post("/webhooks/backgroundchecks")
async def backgroundchecks_said(request: Request, conn: Connection = Depends(get_conn)):
    """backgroundchecks.com telling us a report has moved.

    This endpoint believes ONE thing in what it is sent: the report key. Everything else - whether
    the report is finished, what it found - is then asked of their API directly, over an
    authenticated connection, by the same code the Check For The Result button uses.

    That is deliberate, and it is what makes the endpoint safe to leave open. Their documentation
    describes no signing scheme, so there is nothing to verify a caller with; an endpoint that
    believed its body could be told a driver was cleared by anybody who found the URL. Believing
    only the key reduces a forged call to a wasted lookup against a key we either have or do not.

    An unknown key is answered 200 and ignored. A webhook retried for ever because we said 404 to
    something that is not ours helps nobody."""
    body = await request.body()
    if not backgroundchecks.webhook_ok(body, request.headers):
        # Said without detail. Which part failed is exactly what somebody guessing wants told.
        logging.getLogger("tripproof.live").warning(
            "backgroundchecks webhook refused: signature did not match the body")
        raise HTTPException(401, "Not from backgroundchecks.com")
    try:
        said = json.loads(body or b"{}")
    except ValueError:
        raise HTTPException(400, "Unreadable") from None
    ref = str(said.get("report_key") or said.get("key") or said.get("id") or "").strip()
    if not ref:
        return {"ok": True}
    held = row(conn, """
        SELECT recordid, accountid, driverid FROM driverreports
        WHERE vendor = 'backgroundchecks' AND vendorref = :ref
    """, ref=ref)
    if not held:
        return {"ok": True}
    # Asked with the key of the account the report belongs to. Theirs, not ours: a report lives
    # on one company's account and this installation's credential is not valid for it.
    try:
        got = backgroundchecks.fetch(
            ref, screeningaccount.token_for(conn, held["accountid"]))
    except backgroundchecks.ScreeningError:
        # They told us something moved and we could not go and look. Answered 200 so they stop
        # retrying; the order stays open and the sweep - or the office - will pick it up.
        return {"ok": True}
    from app.routers.vault import _land_screening
    _land_screening(conn, held["accountid"], held["driverid"], held["recordid"], ref,
                    got["status"], "backgroundchecks")
    saved(conn)
    return {"ok": True}
