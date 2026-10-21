###################################################################################################
# backgroundchecks.com: criminal history and identity searches, ordered over their API.
#
# This replaces Certn. The shape of the problem is the same one app/certn.py describes - TripProof
# places the order, so TripProof owns the waiting - but two things about this vendor differ, and
# both change how the code has to be written.
#
#   THEY DO NOT CALL US BACK. Certn posted a webhook when a report finished. Nothing in this
#   vendor's published documentation offers one, and an integration must not assume a callback that
#   may never come. A report is therefore ASKED FOR: GET /status/{report_key}, by the office when
#   it wants to know, and by the sweep that walks open orders. If they do offer webhooks, adding
#   one is additive and changes nothing here.
#
#   THE TOKEN TRAVELS IN THE URL. Their documentation is explicit: "The api_token token must be
#   passed as a query parameter for all authenticated requests." A credential in a query string is
#   a credential in every access log, proxy log and error report between here and them, so it is
#   put there at the last possible moment, by httpx's params, and this module never logs a URL. The
#   logging below records status codes and bodies, never the request line.
#
# WHAT IS CONFIRMED, by read-only calls against a real account on 2026-10-14:
#
#   base url    https://app.backgroundchecks.com/api            (production)
#               https://sandbox.backgroundchecks.com/api        (sandbox, a DIFFERENT token)
#   auth        Authorization: Bearer <token>. Their page says the token may go in the query
#               string, and it may - but a credential in a URL is a credential in every access
#               log, proxy log and error report between here and them, and the header works.
#   reports     GET /reports              the account's reports, paginated Laravel-style
#               GET /reports/{key}/status {"status":"C","flagged_for_end_user_review":false,
#                                          "reports":{"background_report":"C"}}
#               (GET /status/{key} is a redirect to the above, so the real path is used)
#   add-ons     a report row carries mvr_addon, blj_addon, federal_criminal_addon, drug_addon,
#               employment_addon, education_addon - which is how depth is bought. The base report
#               is national criminal, county and the identity trace; everything beyond it is an
#               add-on. A tier is therefore a SET OF ADD-ONS, and a tier with none is the base
#               report, which is a real thing to sell and not a misconfiguration.
#   statuses    single letters. "C" is complete. The others have not been seen, so anything that
#               is not a known finished or failed letter is read as still running.
#
# STILL NOT CONFIRMED, and the only thing left to change when it is: `ORDER_PATH` and the body
# `order()` builds. Placing an order is the one call that cannot be tried without buying a real
# report on a real person, so it is written from the shape of everything around it - the resource
# is `reports`, so a new one is a POST to it - and left in one place.
#
# What a tier contains is NOT written here. It is a fee schedule row - see migration 287 - because
# it is a thing TripProof sells and prices, and a price that lives in Python is a price that needs
# a deploy to change.
###################################################################################################
import hashlib
import hmac
import logging

import httpx

from app.config import settings

log = logging.getLogger("tripproof.backgroundchecks")

# Confirmed from their Swagger reference (basePath /api), 2026-10-15.
#
# An order carries NO personal details - only an email address per applicant. They answer with a
# report_key and an `applicant_invite_url`, and the applicant follows it and enters their own
# name, date of birth, Social Security number and address history. That is the right shape for
# this: under the FCRA the disclosure and authorisation are the applicant's to give, and a system
# that posts a driver's SSN to a vendor before the driver has agreed to anything is doing the one
# thing the Act is about. So TripProof sends an email address and keeps the key.
ORDER_PATH = "/orders/new"

# Their words for where a report has got to, reduced to the three this application understands.
# Anything unrecognised is treated as STILL RUNNING rather than as finished, because finishing an
# order on a word nobody has seen before is how a driver gets cleared by a typo.
# Theirs are single letters - "C" for complete, seen on a real report. The spelled-out words are
# kept beside them because a status endpoint that answers in letters today may answer in words
# tomorrow, and reading both costs nothing.
FINISHED = ("C", "COMPLETE", "COMPLETED", "FINISHED", "CLOSED")
FAILED = ("X", "CANCELLED", "CANCELED", "EXPIRED", "FAILED", "ERROR", "REJECTED")
# "A" - awaiting the applicant. Running, but running on the DRIVER rather than on the vendor, and
# an office chasing a slow report needs to know which: one is waiting on a court, the other is
# waiting on somebody who has not opened their email, and only the second can be hurried along.
WAITING = ("A", "AWAITING", "AWAITING APPLICANT")


class ScreeningError(RuntimeError):
    """Something went wrong at the vendor, in words somebody in an office can act on."""


def configured() -> bool:
    return bool(getattr(settings, "backgroundchecks_api_token", None))


def base_url() -> str:
    return getattr(settings, "backgroundchecks_base_url",
                   "https://sandbox.backgroundchecks.com/api")


def registration_widget_script() -> str | None:
    """The Create Account widget's script - the one that signs a company up for its own account."""
    if not getattr(settings, "backgroundchecks_source_token", ""):
        return None
    return f"{_host()}/js/widgets/registration-widget.js"


def source_token() -> str:
    """What identifies this product to their registration widget. Not a secret the way the private
    key is - it travels to the browser by design - but absent it, no company can sign up."""
    return getattr(settings, "backgroundchecks_source_token", "")


def _host() -> str:
    host = base_url().rstrip("/")
    return host[:-4] if host.endswith("/api") else host


# ------------------------------------------------------------------------------------------------
# What a company can see about its own account with them.
#
# Read-only, and every call takes that company's own token - never this installation's. A company
# looking at "my account" must be looking at theirs.
# ------------------------------------------------------------------------------------------------

def _get(path: str, token: str):
    try:
        with _client(token) as http:
            r = http.get(path)
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    return r.json()


def account(token: str) -> dict:
    return _get("/accounts", token)


def teams(token: str) -> list:
    got = _get("/accounts/teams", token)
    return got if isinstance(got, list) else got.get("data", [])


def billing_info(token: str) -> dict:
    return _get("/billing/info", token)


def invoices(token: str) -> list:
    got = _get("/invoices", token)
    return got if isinstance(got, list) else got.get("data", [])


def invoice_pdf(reference: str, token: str) -> bytes:
    """One invoice as a file. Keyed by their PUBLIC invoice id - "MLYPGDAR-0010" - and not by the
    numeric `id` on the same row, which answers 404 here."""
    try:
        with _client(token) as http:
            r = http.get(f"/invoices/{reference}/pdf", headers={"Accept": "application/pdf"},
                         follow_redirects=True)
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    return r.content


def skus(token: str) -> dict:
    """What this company may order, at the prices THEY pay. Read from the vendor every time rather
    than copied here: a price list kept in two places is a price list that lies in one of them.

    Their add-on list is 573 long, and 554 of those are SURCHARGES - a line for every county and
    state whose court charges to be searched. They are real and they are billed, but they are not
    things anybody chooses: the surcharge follows from where the applicant has lived. Shipping all
    of them to a browser makes a price list nobody can read, so they are counted and summarised,
    and the nineteen things a company actually picks are listed."""
    got = _get("/skus", token)
    addons, surcharges = [], []
    for s in got.get("addons", []):
        (surcharges if "surcharge" in (s.get("title") or "").lower() else addons).append(s)
    prices = sorted(s.get("price") or 0 for s in surcharges)
    return {
        "reports": got.get("reports", []),
        "addons": addons,
        "surcharges": {"count": len(surcharges),
                       "low": prices[0] if prices else 0,
                       "high": prices[-1] if prices else 0},
    }


def applicant_widget_script() -> str | None:
    """The Applicant Form widget's script, for whichever of their worlds we are pointed at.

    The widget lets a driver fill in their own details inside TripProof instead of leaving for an
    emailed link - which is the difference between a driver finishing it while somebody is stood
    next to them and a driver finishing it next week."""
    if not configured():
        return None
    host = base_url().rstrip("/")
    if host.endswith("/api"):
        host = host[:-4]
    return f"{host}/js/widgets/applicant-form-widget.js"


def _client(token: str | None = None) -> httpx.Client:
    """A client for one account's credentials, falling back to this installation's own.

    Two models of this vendor exist side by side and both are legitimate.

    THE PLATFORM ACCOUNT. One account, ours, every company's screenings through it. We front the
    cost and recover it on the monthly invoice. Simple, and the company never has to sign up for
    anything - but under the FCRA WE are then the end user of a consumer report about somebody
    else's job applicant, which is a position nobody should hold by accident.

    THE COMPANY'S OWN ACCOUNT, created through the Connect widget. They are billed directly, they
    sign their own certifications, and the permissible purpose is theirs - which is the truth of
    it, because they are the ones deciding whether to hire the driver.

    So: a company's own token if it has one, ours if it does not."""
    token = token or getattr(settings, "backgroundchecks_api_token", "")
    if not token:
        raise ScreeningError("Background screening is not switched on for this installation yet.")
    return httpx.Client(
        base_url=base_url(),
        headers={"Authorization": f"Bearer {token}",
                 "Content-Type": "application/json", "Accept": "application/json"},
        timeout=30.0,
    )


def widget_token(ref: str, token: str | None = None) -> str:
    """A single-use JWT that lets the View Report widget show one report, and only that one.

    Fetched here and never in the browser: the thing that would have to go to the browser to ask
    for it is the account's API token, and that opens every report on the account."""
    try:
        with _client(token) as http:
            r = http.get(f"/report/{ref}/widget-token")
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    got = r.json().get("token")
    if not got:
        raise ScreeningError("backgroundchecks.com did not return a token for that report.")
    return got


def adopt_account(sealed_token: str) -> str:
    """Turn what the Create Account widget hands back into that company's own API token.

    The widget's onSuccess gives an ENCRYPTED token. It is decrypted with the platform's private
    key, which is why this runs on the server: the private key is the one secret that would let
    anybody holding it adopt accounts in our name."""
    private = getattr(settings, "backgroundchecks_private_key", "")
    if not private:
        raise ScreeningError(
            "This installation has no backgroundchecks.com platform private key, so an account "
            "created in the widget cannot be claimed. Ask their account manager for the platform "
            "source token and private key.")
    try:
        with httpx.Client(base_url=base_url(), timeout=30.0,
                          headers={"Content-Type": "application/json",
                                   "Accept": "application/json"}) as http:
            r = http.post("/token/decrypt",
                          json={"token": sealed_token, "private_key": private})
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    key = r.json().get("api_key")
    if not key:
        raise ScreeningError("backgroundchecks.com did not return an API key for that account.")
    return key


# The add-ons an order can switch on, as their ReportOrder body names them. Each is Y or N.
# `drug_test` is the odd one: switching it on also needs a `drug_sku`, because they sell six
# different panels and there is no default.
ORDER_FLAGS = ("mvr", "employment", "education", "blj", "federal_criminal", "drug_test")


def addons_of(tier: dict) -> list[str]:
    """The add-ons this tier buys on top of its base report, as its fee schedule row states them.

    Empty is a real answer: the base report on its own is the cheapest thing we sell."""
    return [p.strip().lower() for p in str(tier.get("products") or "").split(",") if p.strip()]


def order(tier: dict, driver: dict, email: str | None, token: str | None = None) -> dict:
    """Place one screening. Returns their report key, the applicant's invite link, and a status.

    Nothing is written by the caller until this returns a key: an order we cannot name is an order
    whose result can never be matched to a driver.

    One applicant per call, deliberately. Their API takes a list and bills per applicant, and a
    batch that half-succeeds leaves the office with reports it cannot tell apart from the ones it
    did not get. One driver, one key, one row."""
    sku = (tier.get("reportsku") or "").strip()
    if not sku:
        raise ScreeningError(
            f"{tier.get('name') or 'That tier'} has no report SKU against it, so there is nothing "
            "to order. Set it on the fee schedule. Nothing was ordered and nothing was charged.")
    if not email:
        raise ScreeningError(
            "That driver has no email address, and backgroundchecks.com sends the applicant a link "
            "to enter their own details. Add one first - nothing was ordered or charged.")
    wanted = addons_of(tier)
    body = {
        "report_sku": sku,
        "order_quantity": 1,
        "applicant_emails": [email],
        # Every flag stated, including the ones that are off. A body that mentions only what it
        # wants leaves the rest to whatever the vendor defaults to, and the vendor's default is
        # not a thing this company has agreed to pay for.
        **{flag: ("Y" if flag in wanted else "N") for flag in ORDER_FLAGS},
        # Placing the order IS the agreement - the office pressed the button that spends the money.
        "terms_agree": "Y",
    }
    if body["drug_test"] == "Y":
        drug = (tier.get("drugsku") or "").strip()
        if not drug:
            raise ScreeningError(
                f"{tier.get('name')} includes a drug test but does not say which panel. Set the "
                "drug SKU on the fee schedule. Nothing was ordered and nothing was charged.")
        body["drug_sku"] = drug
    try:
        with _client(token) as http:
            r = http.post(ORDER_PATH, json=body)
    except httpx.HTTPError as e:
        log.warning("screening order failed: %s", e)
        raise ScreeningError("backgroundchecks.com could not be reached. Nothing was ordered and "
                             "nothing was charged - try again in a moment.") from e
    if r.status_code >= 400:
        log.warning("screening order rejected %s: %s", r.status_code, r.text[:400])
        raise ScreeningError(_rejection(r))
    got = r.json()
    # Their 201 answers with a list, one entry per applicant email sent. We send one.
    first = (got.get("applicants") or [{}])[0]
    ref = first.get("report_key") or got.get("report_key")
    if not ref:
        raise ScreeningError("backgroundchecks.com accepted the order but did not say which report "
                             "it is, so it cannot be tracked. Nothing was charged.")
    return {"ref": str(ref), "status": "waiting",
            # The link the driver has to follow to give their details and their authorisation.
            # Without it the order sits unfilled and nobody in the office knows why.
            "invite": first.get("applicant_invite_url"),
            "email": first.get("applicant_email") or email}


def fetch(ref: str, token: str | None = None) -> dict:
    """Where one order has got to. With no webhook from this vendor, this is the only way to know."""
    try:
        with _client(token) as http:
            r = http.get(f"/reports/{ref}/status")
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    got = r.json()
    return {"status": read_status(got), "raw": got}


def report_pdf(ref: str, token: str | None = None) -> bytes:
    """The finished report, as the file that goes on the driver's file.

    Their /pdf route answers 302 to a signed, expiring URL rather than sending the file itself,
    and httpx does not follow redirects unless told to. Without `follow_redirects` what comes back
    is 958 bytes of redirect HTML - which, stored under the name of a PDF, is a document on a
    driver's record that nothing can open and nobody can read."""
    try:
        with _client(token) as http:
            # Singular "report" - the plural path is the account's list, not one file.
            r = http.get(f"/report/{ref}/pdf", headers={"Accept": "application/pdf"},
                         follow_redirects=True)
    except httpx.HTTPError as e:
        raise ScreeningError("backgroundchecks.com could not be reached.") from e
    if r.status_code >= 400:
        raise ScreeningError(_rejection(r))
    # Checked, not assumed. What is kept here is filed as the evidence that a driver was screened,
    # and an error page saved under that name is worse than no file at all: the requirement reads
    # as met and the proof behind it is a redirect.
    if not r.content.startswith(b"%PDF-"):
        log.warning("report %s came back as %s, not a PDF", ref,
                    r.headers.get("content-type", "something else"))
        raise ScreeningError("backgroundchecks.com did not return the report as a file. The "
                             "screening is finished - try fetching it again in a moment.")
    return r.content


# The pieces a report is made of, in their words and ours. Their /status answers with a `reports`
# object whose keys are these, each holding one letter.
PARTS = {
    "background_report": "National criminal",
    "county_status": "County criminal",
    "mvd_status": "Driving record",
    "federal_criminal_status": "Federal criminal",
    "employment_status": "Employment",
    "education_status": "Education",
    "blj_status": "Bankruptcies, liens and judgments",
    "drug_status": "Drug test",
}
SAID_PART = {"C": "Complete", "P": "Still running", "A": "Waiting for the driver"}


def progress(raw: dict) -> list[dict]:
    """What is done and what is not, inside one report.

    A report sits at "pending" until its slowest part finishes, and a county court can take days.
    Without this an office watching a screening that has not moved for two days has no way to tell
    a search still running from one that has gone wrong - and the answer is usually that one
    county is being slow, which is nobody's problem to solve."""
    parts = (raw or {}).get("reports") or {}
    return [{"what": PARTS.get(k, k.replace("_", " ").title()),
             "state": SAID_PART.get(str(v).upper(), str(v)),
             "done": str(v).upper() == "C"}
            for k, v in parts.items() if v]


def read_status(got: dict) -> str:
    """Their word for where it has got to, reduced to running, finished or failed."""
    said = str(got.get("status") or got.get("state") or got.get("result") or "").strip().upper()
    if said in FINISHED:
        return "finished"
    if said in FAILED:
        return "failed"
    if said in WAITING:
        return "waiting"
    # Deliberately the default. A word nobody has seen before means we do not know it is done.
    return "running"


def _rejection(r: httpx.Response) -> str:
    """What they refused, in a sentence rather than a status code."""
    try:
        said = r.json()
    except ValueError:
        said = {}
    detail = said.get("message") or said.get("detail") or said.get("error")
    if r.status_code in (401, 403):
        return ("backgroundchecks.com refused the request. The API token is missing or no longer "
                "valid.")
    if r.status_code == 402:
        return "backgroundchecks.com declined the order on billing grounds."
    if r.status_code == 404:
        return "backgroundchecks.com has no record of that report."
    if r.status_code == 429:
        return "backgroundchecks.com is rate limiting us. Nothing was charged - try again shortly."
    if r.status_code in (400, 422):
        return (f"backgroundchecks.com could not use the details sent: "
                f"{detail or 'check the name and date of birth on the driver record.'}")
    return (f"backgroundchecks.com returned an error ({r.status_code}). "
            f"{detail or 'Nothing was charged.'}")


# What a webhook from them must present before it is believed ------------------------------------
#
# Confirmed by them: every webhook carries a `Signature` header holding the HMAC-SHA256 of the
# UNMODIFIED request body, under the webhook key they issued.
#
# Unmodified is the whole of it. The bytes that arrive are what is hashed - not the result of
# parsing them and serialising them again, which reorders keys, changes spacing and breaks the
# comparison for reasons that look like a vendor fault. The caller hands this function the raw
# body, before anything has read it.
def webhook_ok(body: bytes, headers: dict) -> bool:
    key = getattr(settings, "backgroundchecks_webhook_key", "")
    said = str(headers.get("signature") or "").strip().strip('"')
    if not key or not said:
        # No key configured means nothing is believed. An open endpoint that files background
        # screenings onto a driver's record is not a thing to leave ajar.
        return False
    # A `sha256=` prefix is not in their description; stripped anyway, because if they ever add one
    # the alternative is every webhook silently failing.
    if said.lower().startswith("sha256="):
        said = said.split("=", 1)[1]
    expected = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    # Constant time: a comparison that returns early tells an attacker how much of a guess was
    # right, one character at a time.
    return hmac.compare_digest(said.lower(), expected)
