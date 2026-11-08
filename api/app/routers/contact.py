"""The Contact page on the public site: a message, kept, and emailed to TripProof so somebody
answers it. Built the same way as the tester list (testers.py)."""
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import emails, mailer
from app.config import settings
from app.db import get_conn, newid, run, saved, utcnow
from app.security import client_ip

router = APIRouter(prefix="/api", tags=["contact"])

# A form anybody can post to: this many from one address in an hour, and no more.
TRIES, WINDOW = 5, 3600
_tried: dict[str, list[float]] = {}
TOPICS = {"sales": "Sales", "support": "Support", "broker": "Broker", "other": "Other"}


class ContactIn(BaseModel):
    topic: str = "other"
    name: str
    company: str | None = None
    email: str
    phone: str | None = None
    message: str
    website: str | None = None        # left empty by people; filled in by bots that fill in everything


def _clean(v: str | None, n: int) -> str | None:
    return " ".join((v or "").split())[:n] or None


def _tell(to: str, m: dict) -> None:
    topic = TOPICS[m["topic"]]
    rows_ = "".join(emails.p(f"<strong>{k}:</strong> {emails.escape(v)}") for k, v in (
        ("Topic", topic), ("Name", m["name"]), ("Company", m["company"]), ("Email", m["email"]),
        ("Phone", m["phone"]), ("Message", m["message"])) if v)
    mailer.send(to, f"Contact ({topic}): {m['name']}", emails.layout(
        preheader=f"{m['name']} sent a message from tripproofonline.com.", heading="New Contact Message", body=rows_,
        footer_note="From the Contact page on tripproofonline.com."),
        "\n".join(f"{k}: {v}" for k, v in m.items() if v))


@router.post("/contact")
def contact(body: ContactIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    who, now = client_ip(request) or "?", time.time()
    recent = [t for t in _tried.get(who, []) if now - t < WINDOW]
    if len(recent) >= TRIES:
        raise HTTPException(429, "That is a lot of messages from one place. Email support@tripproofonline.com instead.")
    _tried[who] = recent + [now]
    if body.website:
        return {"ok": True}                   # a bot: thanked, and not kept
    m = {"topic": body.topic if body.topic in TOPICS else "other", "name": _clean(body.name, 120),
         "company": _clean(body.company, 160), "email": (body.email or "").strip().lower()[:255],
         "phone": _clean(body.phone, 40), "message": (body.message or "").strip()[:4000]}
    if not m["name"]:
        raise HTTPException(400, "Give your name.")
    if "@" not in m["email"] or " " in m["email"] or "." not in m["email"].rsplit("@", 1)[-1]:
        raise HTTPException(400, "Give an email address we can reach you at.")
    if not m["message"]:
        raise HTTPException(400, "Write a message.")
    run(conn, """INSERT INTO contactmessages (recordid, topic, name, company, email, phone, message, ip, added)
                 VALUES (:i, :topic, :name, :company, :email, :phone, :message, :ip, :now)""",
        i=newid(), ip=who, now=utcnow(), **m)
    saved(conn)
    tasks.add_task(_tell, settings.tester_notify, m)
    return {"ok": True}
