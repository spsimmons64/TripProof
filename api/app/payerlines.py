"""Whether a payer line counts: a line for private pay always does, and a line for a payer only while
that payer is active for the company - its own say about a shared payer first, then the payer's flag.

Kept as SQL so every query that reads the lines - programs, the trip check's contract, contract
rules, driver approvals - filters them the same way."""


def live(alias: str) -> str:
    """A condition on the companycontracts row named `alias`."""
    return f"""({alias}.payerid IS NULL OR COALESCE(
        (SELECT ap.active FROM accountpayers ap
          WHERE ap.accountid = {alias}.accountid AND ap.payerid = {alias}.payerid),
        (SELECT p.active FROM payers p WHERE p.recordid = {alias}.payerid), 0) = 1)"""
