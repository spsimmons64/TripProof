###################################################################################################
# Audit packets - the auditor asks for trips 1-100; this produces one zip:
#
#   summary.pdf      cover page, then one section per trip: member, legs, driver/vehicle, and every
#                    requirement with the credential that covered it (number, issued, expires,
#                    coverage window) or the reason nothing did
#   trips.csv        one row per trip, the same facts in machine-readable form
#   checks.json      every saved check behind the PDF, verbatim from legchecks
#   rules.json       the version of every rule in force for the run (evaluationruns.rulesnapshot)
#   documents/       the source file of every credential cited
#   SHA256SUMS       a digest of every file above
#
# The packet is tied to the evaluation run current for the requested trips (all trips must share
# it; the caller re-evaluates them together first), and the zip's own digest is recorded, so the
# copy in the auditor's hands can be proven unchanged.
###################################################################################################
import csv
import hashlib
import io
import json
import zipfile
from collections import defaultdict
from datetime import time, timedelta

from fpdf import FPDF
from sqlalchemy.engine import Connection

from app import phi, storage
from app.db import newid, row, rows, run, run_many
from app.evaluator import evaluate


def _latin1(s) -> str:
    # The PDF core fonts are Latin-1; replace anything outside it rather than fail the packet.
    return ("" if s is None else str(s)).encode("latin-1", "replace").decode("latin-1")


def _through(end) -> str:
    # Windows are half-open; an end at midnight reads as "through the previous day".
    if end is None:
        return "onward (no end)"
    if end.time() == time.min:
        return f"through {end - timedelta(days=1):%Y-%m-%d}"
    return f"until {end:%Y-%m-%d %H:%M}"


def _in(prefix: str, ids: list[str]) -> tuple[str, dict]:
    return ", ".join(f":{prefix}{i}" for i in range(len(ids))), {f"{prefix}{i}": v for i, v in enumerate(ids)}


class _Pdf(FPDF):
    def __init__(self, title: str):
        super().__init__(orientation="P", unit="mm", format="Letter")
        self.title_text = title
        self.set_auto_page_break(True, margin=15)

    def header(self):
        self.set_font("Helvetica", "B", 9)
        self.set_text_color(90, 90, 90)
        self.cell(0, 6, _latin1(self.title_text), new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 6, f"Page {self.page_no()} / {{nb}}  -  Contains PHI. Handle under HIPAA.", align="C")


def build(conn: Connection, user: dict, externalids: list[str], auditrequestid: str | None = None) -> dict:
    acct = user["accountid"]
    account = row(conn, "SELECT name, npi, medicaidid, timezone FROM accounts WHERE recordid = :a", a=acct)
    request = row(conn, "SELECT * FROM auditrequests WHERE recordid = :r AND accountid = :a",
                  r=auditrequestid, a=acct) if auditrequestid else None

    ph, p = _in("e", externalids)
    trips = rows(conn, f"""
        SELECT t.recordid, t.externalid, t.tripdate, t.servicelevel, t.billedamount, t.billingstatus,
               b.name AS brokername
        FROM trips t LEFT JOIN payers b ON b.recordid = t.brokerid
        WHERE t.accountid = :a AND t.deleted IS NULL AND t.externalid IN ({ph})
        ORDER BY t.tripdate, t.externalid
    """, a=acct, **p)
    found = {t["externalid"] for t in trips}
    notfound = [e for e in externalids if e not in found]
    if not trips:
        return {"error": "None of the requested trips are in the ledger", "notfound": notfound}

    # One fresh run over exactly these trips, so the packet reflects today's vault and a single run.
    tripids = [t["recordid"] for t in trips]
    ev = evaluate(conn, acct, tripids, user["recordid"], "audit-packet")
    runid = ev["runid"]
    runrow = row(conn, "SELECT * FROM evaluationruns WHERE recordid = :r", r=runid)

    tph, tp = _in("t", tripids)
    legs = rows(conn, f"""
        SELECT l.*, d.firstname, d.lastname, d.licensenumber, d.licensestate,
               v.externalid AS unit, v.vin, v.plate, v.make, v.model, v.modelyear
        FROM triplegs l
        LEFT JOIN drivers d ON d.recordid = l.driverid
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        WHERE l.accountid = :a AND l.tripid IN ({tph})
        ORDER BY l.tripid, l.legnumber
    """, a=acct, **tp)
    checks = rows(conn, f"""
        SELECT c.*, c.rulecode AS requirementcode, c.rulename AS requirement,
               CONCAT('v', COALESCE(c.ruleversion, '-')) AS family, c.ruleversion AS version,
               COALESCE(c.approved, 1) AS verified,
               cr.number, cr.issuer, cr.issuedon, cr.expireson, cr.revokedon, cr.documentid,
               doc.filename, doc.storagekey, doc.sha256 AS docsha256
        FROM legchecks c
        LEFT JOIN credentials cr ON cr.recordid = c.credentialid
        LEFT JOIN documents doc ON doc.recordid = cr.documentid
        WHERE c.runid = :run AND c.tripid IN ({tph})
        ORDER BY c.tripid, c.legid, c.rulecode
    """, run=runid, **tp)
    members = phi.get_many(conn, acct, "trip", tripids)
    legphi = phi.get_many(conn, acct, "leg", [l["recordid"] for l in legs])

    legs_by_trip, checks_by_leg = defaultdict(list), defaultdict(list)
    for l in legs:
        legs_by_trip[l["tripid"]].append(l)
    for c in checks:
        checks_by_leg[c["legid"]].append(c)

    title = f"TripProof audit packet - {account['name']}"
    pdf = _Pdf(title)
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 12, "Trip Credential Evidence Packet", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    cover = [
        ("Provider", account["name"]), ("NPI", account["npi"] or "-"), ("Medicaid ID", account["medicaidid"] or "-"),
        ("Requested by", request["requester"] if request else "-"), ("Reference", request["reference"] if request else "-"),
        ("Trips requested", len(externalids)), ("Trips included", len(trips)),
        ("Trips not found", ", ".join(notfound) if notfound else "none"),
        ("Evaluation run", runid), ("Evaluated (UTC)", runrow["finished"]), ("Engine version", runrow["engineversion"]),
        ("Time basis", f"Pickup times and credential dates are local wall-clock time ({account['timezone']})"),
    ]
    for k, v in cover:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(45, 6, _latin1(k))
        pdf.set_font("Helvetica", "", 10)
        pdf.multi_cell(0, 6, _latin1(v), new_x="LMARGIN", new_y="NEXT")
    failed_trips = {c["tripid"] for c in checks if c["outcome"] != "pass"}
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 11)
    pdf.cell(0, 7, f"Result: {len(trips) - len(failed_trips)} of {len(trips)} trips fully credentialed at pickup",
             new_x="LMARGIN", new_y="NEXT")
    unverified = sorted({f"{c['requirementcode']} {c['family']}" for c in checks if not c["verified"]})
    if unverified:
        pdf.set_font("Helvetica", "I", 9)
        pdf.multi_cell(0, 5, _latin1("Rules not yet approved by a reviewer: " + ", ".join(unverified)),
                       new_x="LMARGIN", new_y="NEXT")

    for t in trips:
        pdf.add_page()
        m = members.get(t["recordid"], {})
        pdf.set_font("Helvetica", "B", 13)
        status = "NOT FULLY CREDENTIALED" if t["recordid"] in failed_trips else "Credentialed"
        pdf.cell(0, 8, _latin1(f"Trip {t['externalid']}  -  {status}"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _latin1(
            f"Date of service {t['tripdate']}   Broker {t['brokername'] or 'unknown'}   Level {t['servicelevel'] or '-'}   "
            f"Billed ${t['billedamount']}   Member {m.get('membername') or '-'} (ID {m.get('memberid') or '-'})"),
            new_x="LMARGIN", new_y="NEXT")
        for l in legs_by_trip[t["recordid"]]:
            lp = legphi.get(l["recordid"], {})
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 10)
            driver = f"{l['firstname']} {l['lastname']}" if l["firstname"] else (l["driverexternal"] or "no driver")
            vehicle = (f"{l['unit'] or ''} {l['modelyear'] or ''} {l['make'] or ''} {l['model'] or ''} VIN {l['vin'] or '-'}"
                       if l["vehicleid"] else (l["vehicleexternal"] or "no vehicle"))
            pdf.multi_cell(0, 5, _latin1(f"Leg {l['legnumber']}: pickup {l['pickupat']}  drop-off {l['dropoffat'] or '-'}"),
                           new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 9)
            pdf.multi_cell(0, 5, _latin1(
                f"Driver {driver}   Vehicle {vehicle.strip()}   Signature {'yes' if l['signature'] else 'no'}   "
                f"GPS {'yes' if l['gps'] else 'no'}\nFrom {lp.get('pickupaddress') or '-'}  To {lp.get('dropoffaddress') or '-'}"),
                new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "B", 8)
            widths = (46, 14, 70, 66)
            for w, h in zip(widths, ("Requirement", "Result", "Evidence", "Coverage window")):
                pdf.cell(w, 5, h, border="B")
            pdf.ln()
            pdf.set_font("Helvetica", "", 8)
            for c in checks_by_leg[l["recordid"]]:
                if c["outcome"] == "pass" and c["credentialid"]:
                    evidence = f"#{c['number'] or '-'} issued {c['issuedon']} exp {c['expireson'] or 'none'}"
                    if c["filename"]:
                        evidence += f" [{c['filename']}]"
                elif c["outcome"] == "pass":
                    evidence = "Vehicle meets rule"
                else:
                    evidence = c["reason"] or ""
                window = f"{c['windowstart']:%Y-%m-%d} {_through(c['windowend'])}" if c["windowstart"] else "-"
                y = pdf.get_y()
                cells = (f"{c['requirementcode']} ({c['family']})", c["outcome"].upper(), evidence, window)
                heights = []
                x = pdf.l_margin
                for w, txt in zip(widths, cells):
                    pdf.set_xy(x, y)
                    pdf.multi_cell(w, 4, _latin1(txt))
                    heights.append(pdf.get_y() - y)
                    x += w
                pdf.set_xy(pdf.l_margin, y + max(heights))

    # trips.csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["trip", "date", "broker", "servicelevel", "billed", "memberid", "membername", "legs", "result", "failures"])
    for t in trips:
        m = members.get(t["recordid"], {})
        fails = [c["reason"] for l in legs_by_trip[t["recordid"]] for c in checks_by_leg[l["recordid"]] if c["outcome"] != "pass"]
        w.writerow([t["externalid"], t["tripdate"], t["brokername"] or "", t["servicelevel"] or "", t["billedamount"],
                    m.get("memberid") or "", m.get("membername") or "", len(legs_by_trip[t["recordid"]]),
                    "fail" if fails else "pass", "; ".join(fails)])

    files: dict[str, bytes] = {
        "summary.pdf": bytes(pdf.output()),
        "trips.csv": buf.getvalue().encode(),
        "checks.json": json.dumps([{k: v for k, v in c.items() if k not in ("storagekey",)} for c in checks],
                                  default=str, indent=1).encode(),
        "rules.json": runrow["rulesnapshot"].encode(),
    }
    seen = set()
    for c in checks:
        if c["documentid"] and c["documentid"] not in seen:
            seen.add(c["documentid"])
            files[f"documents/{c['credentialid']}_{c['filename']}"] = storage.get(c["storagekey"])
    files["SHA256SUMS"] = "".join(f"{hashlib.sha256(b).hexdigest()}  {name}\n" for name, b in files.items()).encode()

    zbuf = io.BytesIO()
    with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, b in files.items():
            z.writestr(name, b)
    data = zbuf.getvalue()

    packetid = newid()
    key = storage.put(acct, "packets", packetid, data)
    run(conn, """
        INSERT INTO auditpackets (recordid, accountid, auditrequestid, runid, tripcount, sha256, storagekey, bytes, generatedby)
        VALUES (:id, :a, :r, :run, :tc, :h, :k, :b, :u)
    """, id=packetid, a=acct, r=auditrequestid, run=runid, tc=len(trips), h=storage.sha256(data), k=key, b=len(data),
        u=user["recordid"])
    run_many(conn, "INSERT INTO auditpackettrips (packetid, tripid) VALUES (:p, :t)",
             [{"p": packetid, "t": t} for t in tripids])
    return {"recordid": packetid, "tripcount": len(trips), "notfound": notfound, "sha256": storage.sha256(data),
            "bytes": len(data), "runid": runid, "failedtrips": len(failed_trips)}
