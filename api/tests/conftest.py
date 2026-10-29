###################################################################################################
# Integration tests run against a real MariaDB. Point TEST_DB_* at a disposable database - the
# fixture drops every table in it. Without TEST_DB_NAME set, integration tests are skipped and only
# the pure unit tests run.
###################################################################################################
import base64
import os
import tempfile

import pytest

from app.dbguard import reaches_beyond, refuse_unsafe

INTEGRATION = bool(os.environ.get("TEST_DB_NAME"))


if INTEGRATION:
    unsafe = refuse_unsafe(os.environ["TEST_DB_NAME"], os.environ.get("DB_NAME"))
    if unsafe:
        raise pytest.UsageError("Refusing to run: " + unsafe)
    os.environ["DB_HOST"] = os.environ.get("TEST_DB_HOST", "127.0.0.1")
    os.environ["DB_PORT"] = os.environ.get("TEST_DB_PORT", "3306")
    os.environ["DB_USER"] = os.environ.get("TEST_DB_USER", "tripproof")
    os.environ["DB_PASSWORD"] = os.environ.get("TEST_DB_PASSWORD", "")
    os.environ["DB_NAME"] = os.environ["TEST_DB_NAME"]
os.environ.setdefault("JWT_SECRET", "test-secret-" + "x" * 32)
os.environ.setdefault("PHI_KEYS", "1:" + base64.b64encode(os.urandom(32)).decode())
os.environ["STORAGE_PATH"] = tempfile.mkdtemp(prefix="tripproof-test-")
# Tests never call Stripe: the Stripe path is covered with billing mocked.
os.environ["STRIPE_SECRET_KEY"] = os.environ["STRIPE_PUBLISHABLE_KEY"] = ""
# Nor send real mail: with no SMTP host, invitations come back as links (tests that need mail mock it).
os.environ["SMTP_HOST"] = ""
# Never text a real phone from a test run: texts are kept, as "off", and not sent.
os.environ["TWILIO_ACCOUNT_SID"] = ""


@pytest.fixture(scope="session")
def db():
    if not INTEGRATION:
        pytest.skip("TEST_DB_NAME not set")
    from app.cli import migrate
    from app.db import engine
    with engine.begin() as conn:
        # Asked of the server, not the settings: the database actually connected to is the one wiped.
        connected = conn.exec_driver_sql("SELECT DATABASE()").scalar()
        if refuse_unsafe(connected, None):
            pytest.exit(f"Refusing to wipe {connected!r}: " + refuse_unsafe(connected, None), returncode=2)
        # And the login itself: one made for the tests sees only test databases, so no setting it
        # is given can point it at live data. Required where the deploy has such a login.
        beyond = reaches_beyond([r[0] for r in conn.exec_driver_sql("SHOW DATABASES").fetchall()])
        if beyond and os.environ.get("TEST_DB_STRICT") == "1":
            pytest.exit(f"Refusing to run: the test login can reach {', '.join(beyond)}", returncode=2)
        if beyond:
            print(f"\nWARNING: the test login can reach {', '.join(beyond)} - give the tests a login "
                  f"of their own (TEST_DB_USER in .env)")
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 0")
        for (name, kind) in conn.exec_driver_sql("SHOW FULL TABLES").fetchall():
            conn.exec_driver_sql(f"DROP {'VIEW' if kind == 'VIEW' else 'TABLE'} `{name}`")
        conn.exec_driver_sql("SET FOREIGN_KEY_CHECKS = 1")
    migrate()
    # Production starts with no rules; tests load the original Florida set to exercise the engine.
    from pathlib import Path
    from app.cli import split_sql
    with engine.begin() as conn:
        for stmt in split_sql((Path(__file__).parent / "fixtures" / "test_rules.sql").read_text()):
            conn.exec_driver_sql(stmt)
    return engine


@pytest.fixture(scope="session")
def client(db):
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)
