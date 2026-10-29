###################################################################################################
# Database - one engine, plain SQL through SQLAlchemy Core text(). Every tenant query passes
# accountid explicitly; there is no query path that reads tenant rows without it.
###################################################################################################
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

from app.config import settings

engine = create_engine(
    f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/{settings.db_name}?charset=utf8mb4",
    pool_pre_ping=True,
    pool_recycle=280,
)


def newid() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    # Naive UTC, which is what the DATETIME housekeeping columns hold.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def localnow(tz: str) -> datetime:
    # Naive wall-clock time in the operator's zone, the basis of every business time.
    return datetime.now(ZoneInfo(tz)).replace(tzinfo=None)


@contextmanager
def tx():
    """A connection inside a transaction; commits on success, rolls back on error."""
    with engine.begin() as conn:
        yield conn


def get_conn():
    """FastAPI dependency: one transaction per request.

    The transaction is committed by `saved()` inside the endpoint, not here. Since FastAPI 0.106 the
    exit code of a dependency with yield runs *after* the response has been sent, so a client that
    reads straight after a write - the application wizard does exactly that - could be served the
    old row. Anything left uncommitted still commits on the way out, and any error still rolls the
    whole request back."""
    with engine.begin() as conn:
        # What waits on a commit belongs to this request only: a connection goes back to the pool,
        # and a text queued by a request that then failed must not go out with the next one.
        conn.info.pop("after_commit", None)
        try:
            yield conn
        finally:
            conn.info.pop("after_commit", None)


def saved(conn: Connection) -> None:
    """Commit what this request has written, before the response goes out - then anything that was
    waiting for it to be written (a text to a driver must not go out about a change that was then
    rolled back)."""
    conn.commit()
    for then in conn.info.pop("after_commit", []):
        then()


def rows(conn: Connection, sql: str, **params) -> list[dict]:
    return [dict(r._mapping) for r in conn.execute(text(sql), params)]


def row(conn: Connection, sql: str, **params) -> dict | None:
    r = conn.execute(text(sql), params).first()
    return dict(r._mapping) if r else None


def run(conn: Connection, sql: str, **params):
    return conn.execute(text(sql), params)


def run_many(conn: Connection, sql: str, paramlist: list[dict]):
    """executemany - one statement, many parameter sets."""
    if paramlist:
        conn.execute(text(sql), paramlist)
