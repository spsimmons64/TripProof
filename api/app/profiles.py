###################################################################################################
# Customer profile rules, shared by the admin portal and the online application: which fields make
# up a profile, how each is normalised, and the account statuses.
###################################################################################################
import re

from fastapi import HTTPException

from app import formats

STATUSES = ("active", "inactive", "setup")
PROFILE_FIELDS = ("name", "dba", "address1", "address2", "city", "county", "state", "zip", "phone",
                  "fax", "email", "supportemail", "billingemail", "ein", "usdot", "mcnumber",
                  "medicaidid", "npi")
# The company's own mailboxes, and what each is for.
EMAIL_FIELDS = (("email", "General email"), ("supportemail", "Support email"), ("billingemail", "Billing email"))


def clean_profile(fields: dict) -> dict:
    """Trim, normalise and validate profile fields; blank strings clear a field."""
    out = {}
    for k, v in fields.items():
        v = v.strip() if isinstance(v, str) else v
        out[k] = v or None
    if out.get("name") is None and "name" in out:
        raise HTTPException(400, "Company name is required")
    if out.get("state"):
        out["state"] = out["state"].upper()
        if not re.fullmatch(r"[A-Z]{2}", out["state"]):
            raise HTTPException(400, "State must be a two-letter code")
    if out.get("zip") and not re.fullmatch(r"\d{5}(-\d{4})?", out["zip"]):
        raise HTTPException(400, "ZIP must be 5 digits or ZIP+4 (12345-6789)")
    try:
        for f, label in (("phone", "Telephone"), ("fax", "Fax")):
            if f in out:
                out[f] = formats.phone(out[f], label)
        if "ein" in out:
            out["ein"] = formats.ein(out["ein"])
    except ValueError as e:
        raise HTTPException(400, str(e))
    if out.get("npi"):
        if not re.fullmatch(r"\d{10}", out["npi"]):
            raise HTTPException(400, "NPI must be 10 digits")
    for field, label in EMAIL_FIELDS:
        if out.get(field):
            out[field] = out[field].lower()
            if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", out[field]):
                raise HTTPException(400, f"{label} doesn't look like an email address")
    return out


def clean_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(400, "Enter a valid email address")
    return email
