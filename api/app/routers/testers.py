"""The tester list: transport companies asking, from the public site, to run TripProof before it
opens. Kept, and each one emailed to TripProof so somebody answers it."""
import time

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import emails, mailer
from app.config import settings
from app.db import get_conn, newid, rows, run, saved, utcnow
from app.security import client_ip, platform_viewer

router = APIRouter(prefix="/api", tags=["testers"])

# A form anybody can post to: this many from one address in an hour, and no more.
TRIES, WINDOW = 5, 3600
_tried: dict[str, list[float]] = {}
FLEETS = ("1-5", "6-15", "16-40", "41+")


class SignupIn(BaseModel):
    company: str
    name: str
    email: str
    phone: str | None = None
    state: str | None = None
    fleet: str | None = None
    brokers: str | None = None
    note: str | None = None
    website: str | None = None        # left empty by people; filled in by bots that fill in everything


def _clean(v: str | None, n: int) -> str | None:
    return " ".join((v or "").split())[:n] or None


def _tell(to: str, s: dict) -> None:
    rows_ = "".join(emails.p(f"<strong>{k}:</strong> {emails.escape(v)}") for k, v in (
        ("Company", s["company"]), ("Name", s["name"]), ("Email", s["email"]), ("Phone", s["phone"]), ("State", s["state"]),
        ("Vehicles", s["fleet"]), ("Brokers", s["brokers"]), ("Note", s["note"])) if v)
    mailer.send(to, f"Tester sign-up: {s['company']}", emails.layout(
        preheader=f"{s['company']} wants to test TripProof.", heading="New Tester Sign-Up", body=rows_,
        footer_note="From the sign-up form on tripproofonline.com."),
        "\n".join(f"{k}: {v}" for k, v in s.items() if v))


@router.post("/testers")
def sign_up(body: SignupIn, request: Request, tasks: BackgroundTasks, conn: Connection = Depends(get_conn)):
    who, now = client_ip(request) or "?", time.time()
    recent = [t for t in _tried.get(who, []) if now - t < WINDOW]
    if len(recent) >= TRIES:
        raise HTTPException(429, "That is a lot of sign-ups from one place. Email support@tripproofonline.com instead.")
    _tried[who] = recent + [now]
    if body.website:
        return {"ok": True}                   # a bot: thanked, and not kept
    s = {"company": _clean(body.company, 160), "name": _clean(body.name, 120), "email": (body.email or "").strip().lower()[:255],
         "phone": _clean(body.phone, 40), "state": _clean(body.state, 8), "fleet": body.fleet if body.fleet in FLEETS else None,
         "brokers": _clean(body.brokers, 400), "note": (body.note or "").strip()[:2000] or None}
    if not s["company"] or not s["name"]:
        raise HTTPException(400, "Give your company name and your own.")
    if "@" not in s["email"] or " " in s["email"] or "." not in s["email"].rsplit("@", 1)[-1]:
        raise HTTPException(400, "Give an email address we can reach you at.")
    run(conn, """INSERT INTO testersignups (recordid, company, name, email, phone, state, fleet, brokers, note, ip, added)
                 VALUES (:i, :company, :name, :email, :phone, :state, :fleet, :brokers, :note, :ip, :now)""",
        i=newid(), ip=who, now=utcnow(), **s)
    saved(conn)
    tasks.add_task(_tell, settings.tester_notify, s)
    return {"ok": True}


@router.get("/admin/testers")
def tester_list(user: dict = Depends(platform_viewer), conn: Connection = Depends(get_conn)):
    return {"items": rows(conn, "SELECT recordid, company, name, email, phone, state, fleet, brokers, note, added FROM testersignups ORDER BY added DESC")}
