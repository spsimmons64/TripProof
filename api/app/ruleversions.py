###################################################################################################
# Every rule as it stood, each time it changed.
#
# A rule is a row edited in place - by a migration, or by a reviewer approving it - so on its own
# the table cannot say what a rule said last month. This keeps a version per change: the whole row,
# its hash, when, by whom and why. Run after every migration and every review decision; a rule
# whose content has not moved writes nothing.
###################################################################################################
import hashlib
import json

from sqlalchemy.engine import Connection

from app.db import newid, row, rows, run, utcnow

# Not part of what a rule says: housekeeping that changes without the rule changing.
IGNORED = {"added", "addedby"}


def _snapshot(rule: dict) -> tuple[str, str]:
    body = json.dumps({k: v for k, v in rule.items() if k not in IGNORED},
                      sort_keys=True, default=str)
    return body, hashlib.sha256(body.encode()).hexdigest()


def capture(conn: Connection, userid: str | None = None, reason: str | None = None) -> int:
    """Write a new version of every rule that differs from its last. Returns how many."""
    latest = {(r["rulecode"], r["accountid"]): r for r in rows(conn, """
        SELECT v.rulecode, v.accountid, v.version, v.snapshotsha FROM compliancerulesversions v
        JOIN (SELECT rulecode, accountid, MAX(version) AS version FROM compliancerulesversions
              GROUP BY rulecode, accountid) m
          ON m.rulecode = v.rulecode AND m.version = v.version
         AND (m.accountid <=> v.accountid)
    """)}
    written = 0
    for rule in rows(conn, "SELECT * FROM compliancerules"):
        body, sha = _snapshot(rule)
        held = latest.get((rule["code"], rule["accountid"]))
        if held and held["snapshotsha"] == sha:
            continue
        run(conn, """
            INSERT INTO compliancerulesversions (recordid, rulecode, accountid, version, snapshot,
                                                 snapshotsha, capturedon, capturedby, reason)
            VALUES (:id, :c, :a, :v, :s, :h, :now, :u, :r)
        """, id=newid(), c=rule["code"], a=rule["accountid"], v=(held["version"] + 1) if held else 1,
            s=body, h=sha, now=utcnow(), u=userid, r=(reason or None) and reason[:128])
        written += 1
    return written


def current(conn: Connection) -> dict[str, int]:
    """The version each platform rule is at now, by code."""
    return {r["rulecode"]: r["version"] for r in rows(conn, """
        SELECT rulecode, MAX(version) AS version FROM compliancerulesversions
        WHERE accountid IS NULL GROUP BY rulecode
    """)}
