"""What became of a text: Bandwidth saying delivered or failed, after it accepted the message.

Accepted only means Bandwidth has it, so the text log says Sent until this arrives. Bandwidth signs
nothing here; the long secret in the address is what says the call is theirs. A message nobody here
sent is ignored, and always answered with success, or Bandwidth would keep trying.
"""

import hmac

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.engine import Connection

from app.config import settings
from app.db import get_conn, run, saved

router = APIRouter(prefix="/api/sms", tags=["sms"])


@router.post("/bandwidth/{secret}")
async def bandwidth(secret: str, request: Request, conn: Connection = Depends(get_conn)):
    wanted = settings.bandwidth_callback_secret
    if not wanted or not hmac.compare_digest(secret, wanted):
        raise HTTPException(404, "Not found")
    try:
        events = await request.json()
    except ValueError:
        raise HTTPException(400, "Not JSON") from None
    for e in events if isinstance(events, list) else [events]:
        if not isinstance(e, dict):
            continue
        kind, sid = e.get("type"), (e.get("message") or {}).get("id")
        if not sid or kind not in ("message-delivered", "message-failed"):
            continue
        if kind == "message-delivered":
            run(conn, "UPDATE drivertexts SET status = 'delivered', error = NULL WHERE twiliosid = :s", s=sid)
        else:
            said = " - ".join(str(x) for x in (e.get("errorCode"), e.get("description")) if x)
            run(conn, "UPDATE drivertexts SET status = 'failed', error = :e WHERE twiliosid = :s", e=said[:400] or "Failed", s=sid)
    saved(conn)
    return {"ok": True}
