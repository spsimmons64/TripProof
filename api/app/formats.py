###################################################################################################
# US identifier formats - one normal form for every phone, fax, EIN and SSN the API stores, whatever
# was typed. Each returns None for blank input and raises ValueError with a readable message when
# the digits don't fit.
###################################################################################################
import re


def _digits(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


def phone(v: str | None, label: str = "Phone") -> str | None:
    """(813) 555-0142. US area codes never start with 0 or 1, so leading 1s (country code) and 0s are
    dropped first - the same rule the web form's mask uses."""
    d = _digits(v)
    if not d:
        return None
    d = d.lstrip("01")
    if len(d) != 10:
        raise ValueError(f"{label} must be a 10-digit US number")
    return f"({d[:3]}) {d[3:6]}-{d[6:]}"


def ein(v: str | None) -> str | None:
    """12-3456789"""
    d = _digits(v)
    if not d:
        return None
    if len(d) != 9:
        raise ValueError("EIN must be 9 digits (12-3456789)")
    return f"{d[:2]}-{d[2:]}"


def ssn(v: str | None) -> str | None:
    """123-45-6789"""
    d = _digits(v)
    if not d:
        return None
    if len(d) != 9:
        raise ValueError("SSN must be 9 digits (123-45-6789)")
    return f"{d[:3]}-{d[3:5]}-{d[5:]}"
