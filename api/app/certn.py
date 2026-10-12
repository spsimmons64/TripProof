###################################################################################################
# Certn: background screening, ordered over their API rather than on somebody's website.
#
# The PSP report and the CDLIS check are fetched by a person signing in to a government site and
# bringing the answer back. This one is different in a way that matters: TripProof places the order,
# so TripProof owns the waiting. An order goes out, nothing comes back for hours or days, and the
# answer arrives on a webhook addressed to a request made long after whoever made it went home.
#
# Three consequences shape this module.
#
#   THE VENDOR'S ID IS THE ONLY THREAD. A webhook carries their application id and nothing of ours,
#   so the id is stored the moment the order is accepted. An order whose id was never recorded is
#   an order whose result can never be filed.
#
#   NOTHING HERE DECIDES ANYTHING. Certn returns what it found; whether that disqualifies a driver
#   is a judgement the company makes, recorded as a reading like every other outside document. This
#   module moves paper and never forms an opinion about it.
#
#   IT HAS TO WORK WHEN CERTN DOES NOT. An outage must not lose an order or charge twice, so every
#   call fails loudly with a sentence somebody can act on, and the caller writes nothing until a
#   reference comes back.
#
# WHAT IS NOT CONFIRMED: the exact request and response field names are written from Certn's public
# documentation and have NOT been exercised against their sandbox - there are no credentials on this
# machine. `ORDER_FIELDS` and `_read_status` are where their shape lives, deliberately in one place,
# so confirming them against a real sandbox response is an edit to two functions and nothing else.
###################################################################################################
import hashlib
import hmac
import logging

import httpx

from app.config import settings

log = logging.getLogger("tripproof.certn")

# What we sell, and what we ask Certn for. The depth is ours to name; the flags are theirs.
TIERS = {
    "core": {
        "name": "Core Background Check",
        "price": 2399,
        "covers": "National criminal database and sex offender registry searches.",
        # Certn turns individual checks on with request flags.
        "flags": {"request_enhanced_identity_verification": True,
                  "request_softcheck": True},
    },
    "complete": {
        "name": "Complete Background Check",
        "price": 5999,
        "covers": "Everything in Core, plus county and federal criminal searches and identity "
                  "verification.",
        "flags": {"request_enhanced_identity_verification": True,
                  "request_softcheck": True,
                  "request_us_criminal_record_check": True,
                  "request_employment_verification": False},
    },
}

# Their words for where an application has got to, mapped to the three states this application
# understands. Anything unrecognised is treated as still running rather than as finished, because
# finishing an order on a word nobody has seen before is how a driver gets cleared by a typo.
RUNNING = ("PENDING", "IN_PROGRESS", "PARTIAL", "ANALYZING", "WAITING_ON_CANDIDATE")
FINISHED = ("COMPLETE", "COMPLETED", "RETURNED")
FAILED = ("CANCELLED", "EXPIRED", "FAILED", "ERROR")


class CertnError(RuntimeError):
    """Something went wrong at Certn, in words somebody in an office can act on."""


def configured() -> bool:
    return bool(getattr(settings, "certn_api_key", None))


def _client() -> httpx.Client:
    if not configured():
        raise CertnError("Background screening is not switched on for this installation yet.")
    return httpx.Client(
        base_url=getattr(settings, "certn_base_url", "https://api.certn.co"),
        headers={"Authorization": f"Bearer {settings.certn_api_key}",
                 "Content-Type": "application/json"},
        timeout=30.0,
    )


def order(tier: str, driver: dict, email: str | None) -> dict:
    """Place one screening. Returns their reference and their first word on it.

    Nothing is written by the caller until this returns a reference: an order we cannot name is an
    order whose result can never be matched to a driver."""
    if tier not in TIERS:
        raise CertnError("Choose a Core or a Complete background check.")
    body = {
        "email": email or None,
        "information": {
            "first_name": (driver.get("firstname") or "").strip(),
            "last_name": (driver.get("lastname") or "").strip(),
            "date_of_birth": str(driver["dob"]) if driver.get("dob") else None,
        },
        **TIERS[tier]["flags"],
    }
    try:
        with _client() as http:
            r = http.post("/api/v1/applications/", json=body)
    except httpx.HTTPError as e:
        log.warning("certn order failed: %s", e)
        raise CertnError("Certn could not be reached. Nothing was ordered and nothing was "
                         "charged - try again in a moment.") from e
    if r.status_code >= 400:
        log.warning("certn order rejected %s: %s", r.status_code, r.text[:400])
        raise CertnError(_rejection(r))
    got = r.json()
    ref = got.get("id") or got.get("applicant_id") or got.get("application_id")
    if not ref:
        raise CertnError("Certn accepted the order but did not say which one it is, so it cannot "
                         "be tracked. Nothing was charged.")
    return {"ref": str(ref), "status": _read_status(got)}


def fetch(ref: str) -> dict:
    """Where one order has got to, asked directly rather than waited for.

    The webhook is how a result normally arrives; this is for an office that wants to know now, and
    for the case where a webhook was missed."""
    try:
        with _client() as http:
            r = http.get(f"/api/v1/applications/{ref}/")
    except httpx.HTTPError as e:
        raise CertnError("Certn could not be reached.") from e
    if r.status_code >= 400:
        raise CertnError(_rejection(r))
    return {"status": _read_status(r.json()), "raw": r.json()}


def report_pdf(ref: str) -> bytes:
    """The finished report, as the file that goes on the driver's file."""
    try:
        with _client() as http:
            r = http.get(f"/api/v1/reports/{ref}/", headers={"Accept": "application/pdf"})
    except httpx.HTTPError as e:
        raise CertnError("Certn could not be reached.") from e
    if r.status_code >= 400:
        raise CertnError(_rejection(r))
    return r.content


def signature_ok(body: bytes, signature: str | None) -> bool:
    """Whether this really came from Certn.

    A webhook endpoint has to be reachable by anybody, so it proves the caller rather than trusting
    them. Compared in constant time, because a comparison that returns early tells an attacker how
    much of a guess was right. With no secret configured nothing is accepted - an open endpoint
    that files background screenings on a driver's record is not a thing to leave ajar."""
    secret = getattr(settings, "certn_webhook_secret", "")
    if not secret or not signature:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip().lower())


def read_status(got: dict) -> str:
    """Their word for where an order has got to - the public name for the reader below."""
    return _read_status(got)


def _read_status(got: dict) -> str:
    """Their word for where it has got to, reduced to running, finished or failed."""
    said = str(got.get("status") or got.get("result") or "").upper()
    if said in FINISHED:
        return "finished"
    if said in FAILED:
        return "failed"
    # Deliberately the default. A word nobody has seen before means we do not know it is done.
    return "running"


def _rejection(r: httpx.Response) -> str:
    """What Certn refused, in a sentence rather than a status code."""
    try:
        said = r.json()
    except ValueError:
        said = {}
    detail = said.get("detail") or said.get("message")
    if r.status_code in (401, 403):
        return "Certn refused the request. The API key is missing or no longer valid."
    if r.status_code == 402:
        return "Certn declined the order on billing grounds."
    if r.status_code == 422 or r.status_code == 400:
        return f"Certn could not use the details sent: {detail or 'check the name and date of birth on the driver record.'}"
    return f"Certn returned an error ({r.status_code}). {detail or 'Nothing was charged.'}"
