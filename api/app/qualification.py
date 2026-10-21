###################################################################################################
# Four separate questions about one driver, never collapsed into one "compliant".
#
#   Hired?                      the hiring decision - the driver's status
#   Onboarding complete?        the HR obligations - I-9, W-4 - which never stop dispatch
#   Qualified for a program?    every rule reaching the driver for that program, satisfied
#   May they take this trip?    the dispatch check - see app/eligibility_check.py
#
# A program is qualified only when every requirement that reaches the driver for it is met. Unknown
# applicability never reads as qualified: a rule nobody can yet say applies leaves the program under
# review, and the reasons say which.
###################################################################################################
from datetime import date

PROGRAMS = {
    "privatepay": "Private Pay",
    "medicaid": "Medicaid NEMT",
    "medicareadvantage": "Medicare Advantage",
    "commercialinsurance": "Commercial Insurance",
    "workerscomp": "Workers' Compensation",
    "facility": "Facility Contracts",
    "dhscoordinated": "DHS Coordinated Transportation",
}
FAILING = ("failed", "expired", "overdue")
WAITING = ("review", "ordered")
EMPLOYMENT = {"application": "Applicant", "appcor": "Applicant", "new": "Applicant",
              "pending": "Pending Hiring Decision", "hired": "Hired", "inactive": "Not Employed",
              "declined": "Not Hired"}


def _onboarding(items: list[dict]) -> dict:
    hr = [i for i in items if i.get("enforcement") == "hr"]
    owed = [i for i in hr if i["applies"] is True]
    if any(i["status"] in FAILING for i in owed):
        state = "Overdue"
    elif any(i["applies"] is None for i in hr):
        state = "Needs Review"
    elif any(i["status"] not in ("satisfied", "expiring") for i in owed):
        state = "In Progress"
    elif owed:
        state = "Complete"
    else:
        state = "Not Applicable"
    return {"status": state,
            "outstanding": [i["name"] for i in owed if i["status"] not in ("satisfied", "expiring")]
            + [i["name"] for i in hr if i["applies"] is None]}


def _program(key: str, items: list[dict]) -> dict:
    """Whether the driver is qualified for one program - each row judged on its own sources for
    that program, never on another program's."""
    from app.rules import for_program
    counts = [x for x in (for_program(i, key) for i in items if i.get("enforcement") != "hr") if x]
    reaching = [i for i in counts if i["applies"] is True and i.get("blocking")]
    # Missing counts against the driver once it is owed. A training a program allows 90 days for
    # is not a shortfall on day ten.
    today = date.today()
    owed = lambda i: not i.get("dueon") or i["dueon"] <= today  # noqa: E731
    failing = [i for i in reaching if i["status"] in FAILING or (i["status"] == "pending" and owed(i))]
    waiting = [i for i in reaching if i["status"] in WAITING]
    undecided = [i for i in counts if i["applies"] is None]
    if failing:
        status = "Not Qualified"
    elif waiting or undecided:
        status = "Review Required"
    else:
        status = "Qualified"
    return {"program": key, "label": PROGRAMS.get(key, key), "status": status,
            "reasons": [i["name"] for i in failing][:4]
            + [f'{i["name"]} - waiting to be read' for i in waiting][:4]
            + [f'{i["name"]} - applicability undecided' for i in undecided][:4]}


def overview(driver: dict, items: list[dict], facts: dict) -> dict:
    """The driver's four answers, each kept to its own scope."""
    programs = list(facts.get("company.programs") or [])
    if not programs:
        # No programs recorded on the operating profile: what the company has said about itself
        # still decides which programs there are.
        programs = ["privatepay"] + (["medicaid"] if facts.get("company.medicaid") else [])
    return {"employment": EMPLOYMENT.get(driver.get("status"), driver.get("status") or "-"),
            "onboarding": _onboarding(items),
            "programs": [_program(p, items) for p in programs]}
