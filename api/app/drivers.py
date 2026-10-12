###################################################################################################
# The driver's own number, which is what the portal calls a Driver ID.
#
# It is not drivers.externalid - that is the driver's key in the customer's dispatch system, which
# the trip importer matches on and which is empty for anyone who applied online. The number here is
# assigned when the record is created, by whatever created it, and counts from 1001 within the one
# account.
###################################################################################################
from sqlalchemy.engine import Connection

from app.db import row

FIRST = 1001


def next_number(conn: Connection, accountid: str) -> int:
    """The next free number for this account. A unique index on (accountid, drivernumber) is what
    actually holds the line if two records are created at the same moment."""
    taken = row(conn, """
        SELECT MAX(drivernumber) AS n FROM drivers WHERE accountid = :a
    """, a=accountid)
    return max(FIRST, (taken["n"] or 0) + 1)
