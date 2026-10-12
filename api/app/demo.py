###################################################################################################
# Demo data - a fictional 4-driver, 4-van Tampa operator with a realistic mix of gaps, for sales
# demos and for trying the UI. Every name and number is made up.
#
#   python -m app.demo --email demo@tripproof.test --password "some long password"
#
# Creates the account, vault, and ~400 trips (Jun-Sep 2026) and imports them through the same
# stage/commit path as a real upload.
###################################################################################################
import argparse
import csv
import io
import random
from datetime import date, datetime, timedelta

from app import importer
from app.cli import create_account
from app.db import newid, row, rows, run, tx

DRIVERS = [
    # dispatch id, first, last, credential gaps
    ("D-101", "Luis", "Ortega", {}),
    ("D-102", "Tanya", "Brooks", {"CPR": ("2024-07-15", "2026-07-15")}),            # CPR lapses mid-July
    ("D-103", "Marcus", "Hale", {"BACKGROUND_CHECK": ("2025-08-01", None)}),       # 365-day limit hits Aug 1
    ("D-104", "Priya", "Nair", {"PASSENGER_ASSIST": None}),                         # no securement training
]
VEHICLES = [("V-01", 2021, "Ford", "Transit"), ("V-02", 2019, "Dodge", "Grand Caravan"),
            ("V-03", 2015, "Chevrolet", "Express"),                                  # too old under broker rules
            ("V-04", 2022, "Toyota", "Sienna")]
MEMBERS = [("Alex Rivera", "FL100200301"), ("Beth Carter", "FL100200302"), ("Chen Wu", "FL100200303"),
           ("Dana Ellis", "FL100200304"), ("Evan Moss", "FL100200305"), ("Faye Grant", "FL100200306")]
STREETS = ["Bayshore Blvd", "Dale Mabry Hwy", "Fowler Ave", "Hillsborough Ave", "Kennedy Blvd", "Busch Blvd"]


def build_csv(seed: int = 7) -> bytes:
    rnd = random.Random(seed)
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Trip ID", "Leg", "Service Date", "Actual Pickup", "Actual Dropoff", "Driver ID", "Driver Name", "Unit",
                "Funding Source", "Space Type", "Billed Amount", "Client Name", "Medicaid ID", "Pickup Address",
                "Dropoff Address", "Signature", "GPS Verified"])
    n = 50000
    d = date(2026, 6, 1)
    while d <= date(2026, 9, 18):
        if d.weekday() < 6:
            for _ in range(rnd.randint(3, 5)):
                n += 1
                drv = rnd.choice(DRIVERS)
                unit = rnd.choice(VEHICLES)
                member = rnd.choice(MEMBERS)
                broker = rnd.choice(["MTM", "ModivCare", "ModivCare"])
                level = rnd.choice(["AMB", "AMB", "AMB", "WC"])
                start = datetime.combine(d, datetime.min.time()) + timedelta(hours=rnd.randint(6, 15), minutes=rnd.choice([0, 15, 30, 45]))
                home = f"{rnd.randint(100, 9999)} {rnd.choice(STREETS)}, Tampa FL"
                clinic = f"{rnd.randint(100, 9999)} {rnd.choice(STREETS)}, Tampa FL"
                amount = round((38 if level == "AMB" else 62) + rnd.random() * 20, 2)
                legs = [(start, home, clinic), (start + timedelta(hours=rnd.randint(2, 4)), clinic, home)]
                for i, (t, a, b) in enumerate(legs, start=1):
                    w.writerow([f"TP{n}", i, d.strftime("%m/%d/%Y"), t.strftime("%m/%d/%Y %I:%M %p"),
                                (t + timedelta(minutes=35)).strftime("%m/%d/%Y %I:%M %p"), drv[0], f"{drv[1]} {drv[2]}",
                                unit[0], broker, level, f"{amount / 2:.2f}", member[0], member[1], a, b,
                                "Y" if rnd.random() > 0.05 else "N", "Y" if rnd.random() > 0.1 else "N"])
        d += timedelta(days=1)
    return out.getvalue().encode()


def add(conn, acct, code, subject, subjectid, issued, expires=None, number=None):
    t = row(conn, "SELECT recordid FROM credentialtypes WHERE code = :c", c=code)
    run(conn, """INSERT INTO credentials (recordid, accountid, credentialtypeid, subject, subjectid, number, issuedon, expireson)
                 VALUES (:id, :a, :t, :s, :sid, :n, :i, :e)""",
        id=newid(), a=acct, t=t["recordid"], s=subject, sid=subjectid, n=number, i=issued, e=expires)


def main():
    p = argparse.ArgumentParser(prog="app.demo")
    p.add_argument("--email", default="demo@tripproof.test")
    p.add_argument("--password", required=True)
    p.add_argument("--name", default="Gulf Coast Care Rides (demo)")
    args = p.parse_args()
    create_account(args.name, args.email, "Demo Owner", "FL", "America/New_York", args.password)

    with tx() as conn:
        user = row(conn, "SELECT recordid, accountid FROM users WHERE email = :e", e=args.email.lower())
        acct = user["accountid"]
        for ext, first, last, gaps in DRIVERS:
            did = newid()
            run(conn, """INSERT INTO drivers (recordid, accountid, externalid, firstname, lastname, licensenumber, licensestate, hiredon)
                         VALUES (:id, :a, :ext, :f, :l, :lic, 'FL', '2023-03-01')""",
                id=did, a=acct, ext=ext, f=first, l=last, lic=f"{last[0]}{random.randint(100000000000, 999999999999)}")
            base = {
                "DRIVER_LICENSE": ("2022-05-01", "2030-05-01"), "CPR": ("2025-01-10", "2027-01-10"),
                "FIRST_AID": ("2025-01-10", "2027-01-10"), "BACKGROUND_CHECK": ("2026-01-15", None),
                "DRUG_SCREEN": ("2026-01-15", None), "PASSENGER_ASSIST": ("2024-02-01", "2027-02-01"),
            }
            base.update(gaps)
            for code, dates in base.items():
                if dates:
                    add(conn, acct, code, "driver", did, *dates)
            # Monthly exclusion checks, run on the 1st. The September run was missed for one driver.
            for m in range(5, 10):
                if not (ext == "D-101" and m == 9):
                    add(conn, acct, "OIG_EXCLUSION", "driver", did, f"2026-{m:02d}-01")
        for ext, yr, make, model in VEHICLES:
            vid = newid()
            run(conn, """INSERT INTO vehicles (recordid, accountid, externalid, modelyear, make, model)
                         VALUES (:id, :a, :ext, :y, :mk, :md)""", id=vid, a=acct, ext=ext, y=yr, mk=make, md=model)
            add(conn, acct, "VEHICLE_REGISTRATION", "vehicle", vid, "2025-09-01", "2026-12-31")
            add(conn, acct, "VEHICLE_INSURANCE", "vehicle", vid, "2026-01-01", "2026-12-31")
            add(conn, acct, "VEHICLE_INSPECTION", "vehicle", vid, "2025-08-20" if ext == "V-02" else "2026-02-01")
        add(conn, acct, "AUTO_LIABILITY_COI", "company", acct, "2026-01-01", "2026-12-31", "CA-DEMO-0001")
        add(conn, acct, "GENERAL_LIABILITY_COI", "company", acct, "2026-01-01", "2026-12-31", "GL-DEMO-0001")

        full = {**rows(conn, "SELECT * FROM users WHERE recordid = :id", id=user["recordid"])[0]}
        staged = importer.stage(conn, full, "demo-dispatch-export.csv", build_csv())
        result = importer.commit(conn, full, staged["recordid"])
    print(f"demo ready: {result['trips']} trips, {result['evaluation']['failures']} failed checks")


if __name__ == "__main__":
    main()
