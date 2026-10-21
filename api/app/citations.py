###################################################################################################
# A citation, as a link to where it can be read.
#
# Rules cite in four forms, and each has one official or standard place to read it:
#   49 CFR 391.11(b)(5)        eCFR, the current Code of Federal Regulations
#   42 U.S.C. 1396a(a)(87)(B)  Cornell LII's United States Code
#   F.S. 409.907(8)(a)4        the Florida Senate's statutes
#   F.A.C. 14-90.004(3)(d)     flrules.org, the Florida Administrative Code
# A citation in none of these forms is returned as text with no link, never with a guessed one.
###################################################################################################
import re

FORMS = [
    (re.compile(r"(\d+)\s*CFR\s*(\d+)\.(\d+)", re.I),
     lambda m: f"https://www.ecfr.gov/current/title-{m[1]}/section-{m[2]}.{m[3]}"),
    (re.compile(r"(\d+)\s*U\.?S\.?C\.?\s*(\d+[a-z]*(?:-\d+)?)", re.I),
     lambda m: f"https://www.law.cornell.edu/uscode/text/{m[1]}/{m[2]}"),
    (re.compile(r"F\.?\s*S\.?\s*(\d+)\.(\d+)", re.I),
     lambda m: f"https://www.flsenate.gov/Laws/Statutes/2026/{m[1]}.{m[2]}"),
    (re.compile(r"F\.?\s*A\.?\s*C\.?\s*(\d+[A-Z]?-\d+\.\d+)", re.I),
     lambda m: f"https://www.flrules.org/gateway/RuleNo.asp?id={m[1]}"),
]


def links(citation: str | None, sourceurl: str | None = None) -> list[dict]:
    """Each part of a citation - they are joined with semicolons - with the page to read it on."""
    out = []
    for part in [p.strip() for p in (citation or "").split(";") if p.strip()]:
        url = None
        for pattern, build in FORMS:
            m = pattern.search(part)
            if m:
                url = build(m)
                break
        out.append({"text": part, "url": url})
    # A link the rule carries itself is the one its author chose, so it wins for the first part.
    if sourceurl:
        if out:
            out[0]["url"] = sourceurl
        else:
            out.append({"text": "Source", "url": sourceurl})
    return out
