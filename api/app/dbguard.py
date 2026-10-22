"""Which databases the test suite may wipe.

The suite's fixture drops every table in its database before rebuilding it from the migrations. It
runs only against a database named for tests, and never the live one - checked against the name in
the settings before anything connects, and against the database the server says it is connected to
before anything is dropped."""


def refuse_unsafe(name: str | None, live: str | None) -> str | None:
    """Why this database must not be wiped by the tests, or None."""
    if not name or not name.endswith("_test"):
        return f"the database is {name!r}: the tests wipe their database, so its name must end in _test"
    if live and name == live:
        return f"{name!r} is the live database"
    return None


# Databases every MariaDB login can see and none of which hold TripProof data.
SYSTEM = {"information_schema", "performance_schema", "mysql", "sys"}


def reaches_beyond(visible: list[str]) -> list[str]:
    """The databases a test login can see that are not test databases - each one something a
    misconfigured run could reach. A login made for the tests should see none."""
    return sorted(d for d in visible if d not in SYSTEM and not d.endswith("_test"))
