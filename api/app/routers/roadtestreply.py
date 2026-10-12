###################################################################################################
# The road test, answered by the examiner - 49 CFR 391.31.
#
# The examiner is usually not in this office: a contracted safety manager, a trainer, somebody at
# another company. So the test reaches them the way a safety performance inquiry reaches a previous
# employer - a link, answered by somebody with no login and nothing to prove themselves against.
#
# What that means for the signature: they type their name and it is drawn in a hand, and it is NOT
# kept as a signature of record. There is nothing to prove it against - an outside examiner has no
# account here, no date of birth we hold and no Social Security number we could ever ask for. It
# signs this one certificate and goes no further, which is exactly what a signature on a faxed
# certificate does.
###################################################################################################
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.engine import Connection

from app import applicationview as view
from app import events, roadtest, roadtestview
from app.db import get_conn, row, run, saved, utcnow
from app.security import client_ip

router = APIRouter(prefix="/api/road-test", tags=["road test"])


def _open(conn: Connection, token: str) -> dict:
    held = row(conn, """
        SELECT r.*, d.firstname, d.lastname, a.name AS accountname,
               l.number AS licensenumber, l.state AS licensestate, l.classification AS licenseclass
        FROM roadtests r
        JOIN drivers d ON d.recordid = r.driverid
        JOIN accounts a ON a.recordid = r.accountid
        LEFT JOIN driverlicenses l ON l.driverid = d.recordid AND l.active = 1
        WHERE r.token = :t
    """, t=token)
    if not held:
        raise HTTPException(404, "This link is not valid")
    if held["completedon"]:
        raise HTTPException(409, "This road test has already been completed")
    if held["expireson"] and held["expireson"] < utcnow():
        raise HTTPException(410, "This link has expired. Ask the company to send a new one.")
    return held


@router.get("/{token}")
def what_is_being_asked(token: str, conn: Connection = Depends(get_conn)):
    """Who is being tested, by whom, and the form to fill in."""
    held = _open(conn, token)
    return {
        "accountname": held["accountname"],
        "driver": {"name": f'{held["firstname"]} {held["lastname"]}'.strip().title(),
                   "licensenumber": held["licensenumber"], "licensestate": held["licensestate"],
                   "licenseclass": held["licenseclass"]},
        "examiner": {"name": held["examinername"], "email": held["examineremail"]},
        "items": [{"key": k, "label": l} for k, l in roadtest.ITEMS],
        "extras": [{"key": k, "label": l} for k, l in roadtest.EXTRAS],
        "ratings": roadtest.RATINGS, "results": roadtest.RESULTS,
        "vehicletypes": roadtest.VEHICLE_TYPES,
        "fonts": list(view.SIGNATURE_FACES),
    }


class ResultIn(BaseModel):
    testedon: str
    startedat: str | None = None
    endedat: str | None = None
    miles: int | None = None
    examinername: str
    examinertitle: str | None = None
    examinerorg: str | None = None
    vehicledescr: str | None = None
    vin: str | None = None
    vehicletype: str | None = None
    gvwr: int | None = None
    seats: int | None = None
    airbrakes: bool | None = None
    manual: bool | None = None
    trailer: bool | None = None
    representative: bool | None = None
    ratings: dict = {}
    extras: dict = {}
    comments: str | None = None
    result: str
    signature: str
    fontkey: str | None = None


@router.post("/{token}")
def file_the_result(token: str, body: ResultIn, request: Request,
                    conn: Connection = Depends(get_conn)):
    """What the examiner saw, and what they decided."""
    held = _open(conn, token)
    if body.result not in roadtest.RESULTS:
        raise HTTPException(400, "Say whether the driver passed")
    if not body.signature.strip():
        raise HTTPException(400, "Sign the certificate")
    # 391.31(b): the test is only a road test if it was in a vehicle representative of what the
    # driver will operate. Saying it was not is allowed - lying about having been asked is not.
    if body.representative is None:
        raise HTTPException(400, "Say whether the vehicle was representative")
    known = {k for k, _ in roadtest.ITEMS}
    extras = {k for k, _ in roadtest.EXTRAS}
    for key, value in list(body.ratings.items()) + list(body.extras.items()):
        if key not in known | extras or value not in roadtest.RATINGS:
            raise HTTPException(400, f"Unrecognised rating for {key}")
    run(conn, """
        UPDATE roadtests
           SET testedon = :on, startedat = :from_, endedat = :to_, miles = :miles,
               examinername = :who, examinertitle = :title, examinerorg = :org,
               vehicledescr = :veh, vin = :vin, vehicletype = :vtype, gvwr = :gvwr, seats = :seats,
               airbrakes = :air, manual = :manual, trailer = :trailer,
               representative = :rep, ratings = :ratings, extras = :extras, comments = :note,
               result = :result, certsignature = :sig, certfontkey = :font,
               completedon = :now, completedip = :ip
         WHERE recordid = :i
    """, on=body.testedon, from_=(body.startedat or None), to_=(body.endedat or None),
        miles=body.miles, who=body.examinername.strip().upper()[:128],
        title=((body.examinertitle or "").strip().upper()[:128] or None),
        org=((body.examinerorg or "").strip().upper()[:160] or None),
        veh=((body.vehicledescr or "").strip().upper()[:160] or None),
        vin=((body.vin or "").strip().upper()[:32] or None), vtype=(body.vehicletype or None),
        gvwr=body.gvwr, seats=body.seats, air=body.airbrakes, manual=body.manual,
        trailer=body.trailer, rep=body.representative,
        ratings=json.dumps(body.ratings), extras=json.dumps(body.extras),
        note=((body.comments or "").strip()[:2000] or None), result=body.result,
        sig=body.signature.strip().upper()[:160],
        font=(body.fontkey if body.fontkey in view.SIGNATURE_FACES else "modern"),
        now=utcnow(), ip=client_ip(request), i=held["recordid"])
    # The evaluation and, on a pass, the certificate - rendered now, from what they just signed.
    roadtestview.keep(conn, held["recordid"])
    events.record(conn, held["accountid"], "driver", held["driverid"], "uploaded", "ROAD_TEST",
                  label=f'Road test {roadtest.RESULTS[body.result].lower()} for '
                        f'{held["firstname"].title()} {held["lastname"].title()}')
    saved(conn)
    return {"ok": True, "accountname": held["accountname"],
            "result": roadtest.RESULTS[body.result]}
