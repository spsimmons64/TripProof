###################################################################################################
# Command line - run from the api directory (or the api container):
#
#   python -m app.cli migrate                  apply db/migrations/*.sql not yet applied
#   python -m app.cli create-account --name "Bay Area Medical Transport" --email owner@example.com
#   python -m app.cli reprice [--days 3]       move subscriptions renewing within N days to the plan
#                                              their current fleet size calls for (daily cron; the
#                                              invoice.upcoming webhook does the same per renewal)
#
# Migrations are plain .sql files applied in name order and recorded in `schemamigrations`. They
# may use `DELIMITER $$ ... DELIMITER ;` for triggers, exactly as the mariadb client accepts.
###################################################################################################
import argparse
import getpass
import os
import re
from pathlib import Path

from sqlalchemy import text

from app.db import engine, newid, row, run, tx
from app.security import hash_password

MIGRATIONS = Path(os.environ.get("MIGRATIONS_PATH", Path(__file__).resolve().parents[2] / "db" / "migrations"))


def _without_comment(line: str) -> str:
    """The line up to its first "--" outside single or double quotes."""
    quote = None
    for n, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif line.startswith("--", n) and (n == 0 or line[n - 1].isspace()):
            return line[:n]
    return line


def split_sql(sql: str) -> list[str]:
    """Split a script into statements, honouring DELIMITER lines and skipping comments."""
    statements, buf, delim = [], [], ";"
    for line in sql.splitlines():
        m = re.match(r"^\s*DELIMITER\s+(\S+)\s*$", line, re.I)
        if m:
            delim = m.group(1)
            continue
        if not buf and (not line.strip() or line.strip().startswith("--")):
            continue
        buf.append(line)
        # A trailing "-- comment" after the delimiter still ends the statement. It is cut at the
        # first "--" that stands outside a quoted string, so a "--" inside a literal is left alone,
        # an apostrophe IN the comment cannot glue this statement to the next one, and a line with a
        # string on it - 'FCRA_FORMS');  -- a note - still ends where the code does. (Cutting only
        # lines with no quote at all left 024 unrunnable on an empty database.)
        code = _without_comment(line)
        code = code.rstrip()
        if code.endswith(delim):
            buf[-1] = code
            stmt = "\n".join(buf).rstrip()[: -len(delim)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    if "\n".join(buf).strip():
        statements.append("\n".join(buf).strip())
    return statements


def migrate():
    with tx() as conn:
        run(conn, """CREATE TABLE IF NOT EXISTS schemamigrations (
                        filename VARCHAR(255) NOT NULL PRIMARY KEY,
                        applied  DATETIME NOT NULL DEFAULT UTC_TIMESTAMP())""")
        done = {r[0] for r in conn.exec_driver_sql("SELECT filename FROM schemamigrations")}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        if path.name in done:
            continue
        print(f"applying {path.name}")
        # DDL commits implicitly in MariaDB, so each file runs on a raw connection statement by
        # statement; a failure stops the run with the file unrecorded, to be fixed and re-run.
        raw = engine.raw_connection()
        try:
            cur = raw.cursor()
            for stmt in split_sql(path.read_text()):
                cur.execute(stmt)
            cur.execute("INSERT INTO schemamigrations (filename) VALUES (%s)", (path.name,))
            raw.commit()
        finally:
            raw.close()
    # Whatever the migrations changed in the rules is kept as a new version of each.
    # Never a reason for the service not to start: a failure here is reported and the next run
    # catches up, because a version is only ever the difference from the last one.
    from app import ruleversions
    try:
        with tx() as conn:
            n = ruleversions.capture(conn, reason="migration")
        if n:
            print(f"recorded {n} rule version{'' if n == 1 else 's'}")
    except Exception as e:                  # noqa: BLE001 - see above
        print(f"rule versions not recorded: {e}")
    print("migrations up to date")


def create_account(name: str, email: str, username: str, state: str, timezone: str, password: str | None):
    password = password or getpass.getpass("Password for the owner: ")
    if len(password) < 12:
        raise SystemExit("Use a password of at least 12 characters")
    with tx() as conn:
        if row(conn, "SELECT 1 AS x FROM users WHERE email = :e", e=email.lower()):
            raise SystemExit(f"{email} already has an account")
        acct, uid = newid(), newid()
        number = row(conn, "SELECT NEXT VALUE FOR accountnumbers AS n")["n"]
        run(conn, "INSERT INTO accounts (recordid, accountnumber, name, state, timezone) VALUES (:id, :num, :n, :s, :tz)",
            id=acct, num=number, n=name, s=state.upper(), tz=timezone)
        run(conn, """INSERT INTO users (recordid, accountid, email, name, passwordhash, role)
                     VALUES (:id, :a, :e, :n, :p, 'owner')""",
            id=uid, a=acct, e=email.lower(), n=username or email, p=hash_password(password))
        run(conn, "UPDATE accounts SET primaryuserid = :u WHERE recordid = :a", u=uid, a=acct)
    print(f"account #{number} ({acct})\nowner   {uid} <{email.lower()}>")


def create_admin(email: str, name: str, password: str | None, role: str = "superadmin"):
    """A TripProof staff login for the admin portal. Staff live in one internal account (platform = 1),
    created on first use; it holds no customer data and never appears in customer lists."""
    password = password or getpass.getpass("Password for the admin: ")
    if len(password) < 12:
        raise SystemExit("Use a password of at least 12 characters")
    with tx() as conn:
        if row(conn, "SELECT 1 AS x FROM users WHERE email = :e", e=email.lower()):
            raise SystemExit(f"{email} already has a login")
        platform = row(conn, "SELECT recordid FROM accounts WHERE platform = 1 LIMIT 1")
        if platform:
            acct = platform["recordid"]
        else:
            acct = newid()
            run(conn, "INSERT INTO accounts (recordid, name, state, platform) VALUES (:id, 'TripProof (staff)', 'FL', 1)", id=acct)
        uid = newid()
        run(conn, """INSERT INTO users (recordid, accountid, email, name, passwordhash, role, platformrole)
                     VALUES (:id, :a, :e, :n, :p, 'admin', :pr)""",
            id=uid, a=acct, e=email.lower(), n=name or email, p=hash_password(password), pr=role)
    print(f"admin {uid} <{email.lower()}> ({role})")


def reprice(days: int):
    from datetime import timedelta
    from app import billing, billingsync
    from app.db import rows, utcnow
    if not billing.configured():
        raise SystemExit("Stripe isn't configured")
    with tx() as conn:
        due = rows(conn, """SELECT DISTINCT accountid FROM subscriptions
                             WHERE status IN ('trialing', 'active', 'past_due') AND stripesubscriptionid IS NOT NULL
                               AND COALESCE(currentperiodend, trialend) <= :until""", until=utcnow() + timedelta(days=days))
    for r in due:
        with tx() as conn:          # one transaction per account: a Stripe error stops only that one
            try:
                print(r["accountid"], billingsync.reprice(conn, r["accountid"]))
            except billing.BillingError as e:
                print(r["accountid"], "failed:", e)


def collect_screenings():
    """Collect background screenings that have finished. Run often - they come back all day."""
    from app import screeningsweep
    with tx() as conn:
        out = screeningsweep.collect(conn)
    print(f"asked about {out['looked']} open screening(s)")
    print(f"  came back    {out['landed']}")
    print(f"  still going  {out['waiting']}")
    if out["failed"]:
        print(f"  could not be run {out['failed']}")
    if out["unreachable"]:
        print(f"  could not ask    {out['unreachable']}")


def screen_exclusions():
    """Screen every driver against the OIG exclusion list. Run monthly, after the 10th."""
    from app import screening
    with tx() as conn:
        out = screening.monthly(conn)
    if out.get("failed"):
        print(f"OIG screening FAILED, recorded as failed: {out['why']}")
        raise SystemExit(1)
    if out.get("skipped"):
        print(f"already screened against the list OIG published {out['stamp']} - nothing to do")
        return
    print(f"screened against the list OIG published {out['stamp']} ({out['listed']:,} people)")
    print(f"  clear     {out['clear']:,}")
    print(f"  potential {out['potential']:,}" + ("  <- these need a person" if out["potential"] else ""))


def screen_sam():
    """Screen every pending and active driver against the SAM.gov exclusions list. Run daily."""
    from app import screening
    with tx() as conn:
        out = screening.daily_sam(conn)
    if out.get("failed"):
        print(f"SAM.gov screening FAILED, recorded as failed: {out['why']}")
        raise SystemExit(1)
    if out.get("skipped"):
        print(f"already screened against the SAM.gov list of {out['stamp']} - nothing to do")
        return
    print(f"screened against the SAM.gov list of {out['stamp']} ({out['listed']:,} individuals)")
    print(f"  clear     {out['clear']:,}")
    print(f"  potential {out['potential']:,}" + ("  <- these need a person" if out["potential"] else ""))


def daily_compliance():
    """Keep today's program standings and re-check the week's assigned trips. Run daily."""
    from app import dailycompliance
    with tx() as conn:
        out = dailycompliance.daily(conn)
    print(f"snapshots {out['snapshots']:,} - trips checked {out['checked']:,}, "
          f"no longer qualified {out['notqualified']:,}")


def main():
    p = argparse.ArgumentParser(prog="app.cli")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("migrate")
    sub.add_parser("screen-exclusions")
    sub.add_parser("screen-sam")
    sub.add_parser("daily-compliance")
    sub.add_parser("collect-screenings")
    cadm = sub.add_parser("create-admin")
    cadm.add_argument("--email", required=True)
    cadm.add_argument("--name", default="")
    cadm.add_argument("--role", default="superadmin", choices=["superadmin", "support"])
    cadm.add_argument("--password", help="omit to be prompted")
    ca = sub.add_parser("create-account")
    ca.add_argument("--name", required=True)
    ca.add_argument("--email", required=True)
    ca.add_argument("--username", default="")
    ca.add_argument("--state", default="FL")
    ca.add_argument("--timezone", default="America/New_York")
    ca.add_argument("--password", help="omit to be prompted")
    rp = sub.add_parser("reprice")
    rp.add_argument("--days", type=int, default=3)
    args = p.parse_args()
    if args.cmd == "migrate":
        migrate()
    elif args.cmd == "screen-exclusions":
        screen_exclusions()
    elif args.cmd == "screen-sam":
        screen_sam()
    elif args.cmd == "daily-compliance":
        daily_compliance()
    elif args.cmd == "collect-screenings":
        collect_screenings()
    elif args.cmd == "reprice":
        reprice(args.days)
    elif args.cmd == "create-admin":
        create_admin(args.email, args.name, args.password, args.role)
    else:
        create_account(args.name, args.email, args.username, args.state, args.timezone, args.password)


if __name__ == "__main__":
    main()
