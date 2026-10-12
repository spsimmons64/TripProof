###################################################################################################
# Admin portal. Named to run after test_flow: it publishes rules, which changes results for the
# accounts test_flow creates, and uses that account's trips to prove publishing re-evaluates.
###################################################################################################
import pytest
from sqlalchemy import text


def login(client, email, password):
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def admin(client, db):
    from app.cli import create_admin
    create_admin("root@tripproof.test", "Root", "admin password 123", "superadmin")
    create_admin("help@tripproof.test", "Helper", "admin password 123", "support")
    return {"h": login(client, "root@tripproof.test", "admin password 123"),
            "support": login(client, "help@tripproof.test", "admin password 123")}


def test_access_control(client, admin):
    owner = login(client, "owner@a.test", "correct horse battery")
    assert client.get("/api/admin/overview", headers=owner).status_code == 403
    assert client.get("/api/admin/overview", headers=admin["support"]).status_code == 200
    # support can read but not change
    assert client.post("/api/admin/brokers", json={"code": "X", "name": "X"}, headers=admin["support"]).status_code == 403
    o = client.get("/api/admin/overview", headers=admin["h"]).json()
    assert o["counts"]["customers"] >= 2 and o["counts"]["credentialtypes"] >= 10
    # the staff account is not a customer
    listing = client.get("/api/admin/accounts", headers=admin["h"]).json()
    assert all(a["name"] != "TripProof (staff)" for a in listing["items"])
    # Paging: one row per page still reports the full total.
    one = client.get("/api/admin/accounts", params={"pagesize": 1, "page": 2}, headers=admin["h"]).json()
    assert one["total"] == listing["total"] >= 2 and len(one["items"]) == 1 and one["items"][0] == listing["items"][1]


def _token(link: str) -> str:
    from urllib.parse import parse_qs, urlparse
    return parse_qs(urlparse(link).query)["token"][0]


def test_customer_and_user_management(client, admin):
    h = admin["h"]
    body = {"name": "Suncoast Rides", "address1": "100 Bay St", "address2": "Suite 4", "city": "Tampa", "state": "fl",
            "zip": "33602", "phone": "813.555.0100", "fax": "8135550101", "ein": "123456789", "medicaidid": "FL-99",
            "npi": "1234567890", "adminname": "Boss Person", "adminemail": "Boss@Suncoast.test"}
    # Validation happens before anything is written.
    assert client.post("/api/admin/accounts", json={**body, "ein": "12-345"}, headers=h).status_code == 400
    assert client.post("/api/admin/accounts", json={**body, "zip": "3360"}, headers=h).status_code == 400
    r = client.post("/api/admin/accounts", json=body, headers=h).json()
    assert r["accountnumber"] > 100001                      # assigned from the sequence, never sent by the client
    inv = r["invitation"]
    assert inv["emailed"] is False and inv["email"] == "boss@suncoast.test"   # no SMTP in tests → link comes back

    prof = client.get(f"/api/admin/accounts/{r['recordid']}", headers=h).json()
    assert (prof["phone"], prof["fax"], prof["ein"], prof["state"]) == ("(813) 555-0100", "(813) 555-0101", "12-3456789", "FL")
    assert (prof["adminname"], prof["adminemail"]) == ("Boss Person", "boss@suncoast.test")

    # The admin can't sign in until the invitation is used.
    token = _token(inv["link"])
    assert client.get(f"/api/auth/reset/{token}").json()["purpose"] == "invite"
    assert client.post("/api/auth/reset", json={"token": token, "password": "short"}).status_code == 400
    ok = client.post("/api/auth/reset", json={"token": token, "password": "a brand new password"})
    assert ok.status_code == 200
    owner = {"Authorization": f"Bearer {ok.json()['token']}"}
    assert client.get("/api/auth/me", headers=owner).json()["accountname"] == "Suncoast Rides"
    # Links are single-use.
    assert client.post("/api/auth/reset", json={"token": token, "password": "another password!!"}).status_code == 410

    # Re-inviting someone who has signed in sends a reset; the old password works until it's used.
    again = client.post(f"/api/admin/users/{prof['primaryuserid']}/invite", headers=h).json()
    assert client.get(f"/api/auth/reset/{_token(again['link'])}").json()["purpose"] == "reset"
    login(client, "boss@suncoast.test", "a brand new password")
    client.post("/api/auth/reset", json={"token": _token(again["link"]), "password": "the reset password"})
    assert client.post("/api/auth/login", json={"email": "boss@suncoast.test", "password": "a brand new password"}).status_code == 401
    login(client, "boss@suncoast.test", "the reset password")

    # Editing the admin contact edits the login itself.
    assert client.patch(f"/api/admin/accounts/{r['recordid']}", json={"adminemail": "chief@suncoast.test", "city": "St. Petersburg"},
                        headers=h).status_code == 200
    login(client, "chief@suncoast.test", "the reset password")
    assert client.patch(f"/api/admin/accounts/{r['recordid']}", json={"adminemail": "owner@a.test"}, headers=h).status_code == 409

    # Suspending an account signs its users out, blocks login, and kills outstanding links.
    pending = client.post(f"/api/admin/users/{prof['primaryuserid']}/invite", headers=h).json()
    assert client.patch(f"/api/admin/accounts/{r['recordid']}", json={"status": "inactive"}, headers=h).status_code == 200
    assert client.get("/api/auth/me", headers=owner).status_code == 401
    assert client.post("/api/auth/login", json={"email": "chief@suncoast.test", "password": "the reset password"}).status_code == 401
    assert client.get(f"/api/auth/reset/{_token(pending['link'])}").status_code == 410

    # A platform role cannot be given to a customer's user.
    assert client.patch(f"/api/admin/users/{prof['primaryuserid']}", json={"platformrole": "superadmin"},
                        headers=h).status_code == 400

    log = client.get("/api/admin/activity", params={"action": "admin-create-account"}, headers=h).json()
    assert log["total"] >= 1


def test_notifications(client, admin):
    # Customer: unbilled at-risk trips from test_flow's account; marking read drops the count.
    owner = login(client, "owner@a.test", "correct horse battery")
    mine = client.get("/api/notifications", headers=owner).json()
    atrisk = next(n for n in mine["items"] if n["key"].startswith("atrisk:"))
    assert not atrisk["read"] and mine["unread"] >= 1
    client.post("/api/notifications/read", json={"keys": [atrisk["key"]]}, headers=owner)
    after = client.get("/api/notifications", headers=owner).json()
    assert after["unread"] == mine["unread"] - 1
    assert next(n for n in after["items"] if n["key"] == atrisk["key"])["read"]
    # Staff notifications never leak into a customer's list.
    assert not any(n["key"].startswith(("pastdue:", "quote:", "failedlogins:")) for n in after["items"])


def test_launch_into_customer_portal(client, admin, db):
    h = admin["h"]
    owner = login(client, "owner@a.test", "correct horse battery")
    acct = client.get("/api/auth/me", headers=owner).json()["accountid"]
    mine = client.get("/api/trips", headers=owner).json()["total"]

    t = client.post(f"/api/admin/accounts/{acct}/launch", headers=h).json()["token"]
    staff = {"Authorization": f"Bearer {t}"}
    me = client.get("/api/auth/me", headers=staff).json()
    assert me["launched"] and me["accountid"] == acct and me["role"] == "admin" and me["name"] == "Root"
    assert client.get("/api/trips", headers=staff).json()["total"] == mine          # sees the customer's data
    assert client.get("/api/admin/overview", headers=staff).status_code == 403      # but not the admin portal
    assert client.get("/api/notifications", headers=staff).json()["items"][0]["key"].startswith(("atrisk:", "expiring:", "import:", "stubs:", "audit:"))

    # What staff do in the portal is logged under the staff member, against the customer.
    client.get(f"/api/trips/{client.get('/api/trips', headers=staff).json()['items'][0]['recordid']}/phi", headers=staff)
    root = client.get("/api/auth/me", headers=h).json()["recordid"]
    with db.connect() as conn:
        n = conn.execute(text("SELECT COUNT(*) FROM activitylog WHERE userid = :u AND accountid = :a AND phi = 1"),
                         {"u": root, "a": acct}).scalar()
        assert n == 1

    # Support staff launch read-only.
    ts = client.post(f"/api/admin/accounts/{acct}/launch", headers=admin["support"]).json()["token"]
    ro = {"Authorization": f"Bearer {ts}"}
    assert client.get("/api/auth/me", headers=ro).json()["role"] == "auditor"
    assert client.post("/api/drivers", json={"firstname": "No", "lastname": "Way"}, headers=ro).status_code == 403

    # Losing the platform role ends any launched session.
    helper = next(u for u in client.get("/api/admin/users", params={"q": "help@"}, headers=h).json()["items"])
    client.patch(f"/api/admin/users/{helper['recordid']}", json={"platformrole": ""}, headers=h)
    assert client.get("/api/auth/me", headers=ro).status_code == 401


def test_account_statuses(client, admin, db):
    h = admin["h"]
    # Staff-created customers start active; setup can't be chosen by staff.
    r = client.post("/api/admin/accounts", json={"name": "Dormant Transit", "adminname": "Dee", "adminemail": "dee@dormant.test"},
                    headers=h).json()
    acct = r["recordid"]
    assert client.get(f"/api/admin/accounts/{acct}", headers=h).json()["status"] == "active"
    assert client.post("/api/admin/accounts", json={"name": "X", "status": "setup", "adminname": "X",
                                                    "adminemail": "x@x.test"}, headers=h).status_code == 400
    assert client.patch(f"/api/admin/accounts/{acct}", json={"status": "setup"}, headers=h).status_code == 400

    # An online signup still in setup (set by the system) can sign in to finish its application,
    # and staff saving its profile unchanged keeps it in setup.
    with db.begin() as conn:
        conn.execute(text("UPDATE accounts SET status = 'setup' WHERE recordid = :a"), {"a": acct})
    token = r["invitation"]["link"].split("token=", 1)[1]
    assert client.get(f"/api/auth/reset/{token}").status_code == 200
    assert client.patch(f"/api/admin/accounts/{acct}", json={"status": "setup", "city": "Ocala"}, headers=h).status_code == 200

    # Inactive refuses the link; active accepts it again.
    assert client.patch(f"/api/admin/accounts/{acct}", json={"status": "inactive"}, headers=h).status_code == 200
    assert client.get(f"/api/auth/reset/{token}").status_code == 410
    assert client.patch(f"/api/admin/accounts/{acct}", json={"status": "active"}, headers=h).status_code == 200
    assert client.post("/api/auth/reset", json={"token": token, "password": "dormant no more!"}).status_code == 200
    counts = client.get("/api/admin/overview", headers=h).json()["counts"]
    assert {"inactive", "setup"} <= set(counts)


def test_customer_grid_filters_and_sort(client, admin):
    h = admin["h"]
    get = lambda **kw: client.get("/api/admin/accounts", params={"pagesize": 100, **kw}, headers=h).json()
    all_ = get()
    names = [a["name"] for a in get(sort="name")["items"]]
    assert names == sorted(names, key=str.lower)
    assert [a["name"] for a in get(sort="name", dir="desc")["items"]] == names[::-1]
    risk = get(sort="atrisk", dir="desc")["items"]
    assert [float(a["atrisk"]) for a in risk] == sorted((float(a["atrisk"]) for a in risk), reverse=True)
    nums = [a["accountnumber"] for a in get(sort="accountnumber")["items"]]
    assert nums == sorted(nums)
    # Filters narrow the total and every row matches.
    inactive = get(status="inactive")
    assert all(a["status"] == "inactive" for a in inactive["items"]) and inactive["total"] < all_["total"]
    atrisk = get(risk="yes")
    assert atrisk["total"] >= 1 and all(float(a["atrisk"]) > 0 for a in atrisk["items"])
    assert get(risk="no")["total"] + atrisk["total"] == all_["total"]
    # Each row carries the admin's email, and search finds customers by it.
    demo = next(a for a in all_["items"] if a["name"] == "Bay Test Transport")
    assert demo["adminemail"] == "owner@a.test"
    assert [a["name"] for a in get(q="owner@a.test")["items"]] == ["Bay Test Transport"]
    # Unknown sort keys fall back to name rather than reaching the SQL.
    assert client.get("/api/admin/accounts", params={"sort": "name; DROP TABLE accounts"}, headers=h).status_code == 200


def test_admin_plans(client, admin):
    h = admin["h"]
    plans = client.get("/api/admin/plans", headers=h).json()
    growth = next(p for p in plans if p["code"] == "GROWTH")
    assert growth["subscribers"] >= 1        # the application tests signed someone up on it
    body = {k: growth[k] for k in ("code", "name", "description", "minvehicles", "maxvehicles", "monthlyprice", "trialdays",
                                   "features", "active", "sortorder")}
    body["monthlyprice"] = float(body["monthlyprice"])
    # Tiers can't overlap: a fleet must map to exactly one plan.
    assert client.post("/api/admin/plans", json={**body, "code": "CLASH", "minvehicles": 10, "maxvehicles": 20}, headers=h).status_code == 409
    assert client.put(f"/api/admin/plans/{growth['recordid']}", json={**body, "maxvehicles": 4}, headers=h).status_code == 400
    assert client.put(f"/api/admin/plans/{growth['recordid']}", json={**body, "monthlyprice": 259}, headers=h).status_code == 200
    assert float(next(p for p in client.get("/api/admin/plans", headers=h).json() if p["code"] == "GROWTH")["monthlyprice"]) == 259
    # An inactive tier may overlap (it's retired); support staff can't edit.
    assert client.post("/api/admin/plans", json={**body, "code": "OLDGROWTH", "active": False}, headers=h).status_code == 200
    assert client.put(f"/api/admin/plans/{growth['recordid']}", json=body, headers=admin["support"]).status_code == 403


def test_users_grid_is_staff_only(client, admin):
    h = admin["h"]
    everyone = client.get("/api/admin/users", params={"pagesize": 1000}, headers=h).json()
    assert everyone["total"] == len(everyone["items"]) >= 2 and everyone["staffaccountid"]
    emails = {u["email"] for u in everyone["items"]}
    assert "root@tripproof.test" in emails and not any(e.endswith("@sunrise.test") for e in emails)   # no customer logins
    supers = client.get("/api/admin/users", params={"role": "superadmin"}, headers=h).json()["items"]
    assert supers and all(u["platformrole"] == "superadmin" for u in supers)
    by_email = client.get("/api/admin/users", params={"sort": "email", "dir": "desc"}, headers=h).json()["items"]
    assert [u["email"] for u in by_email] == sorted((u["email"] for u in by_email), reverse=True)
    page2 = client.get("/api/admin/users", params={"pagesize": 1, "page": 2}, headers=h).json()
    assert len(page2["items"]) == 1 and page2["total"] == everyone["total"]


def test_activity_for_one_user(client, admin):
    h = admin["h"]
    root = next(u for u in client.get("/api/admin/users", params={"q": "root@"}, headers=h).json()["items"] if u["email"] == "root@tripproof.test")
    items = client.get("/api/admin/activity", params={"userid": root["recordid"]}, headers=h).json()["items"]
    assert items and all(i["email"] == "root@tripproof.test" for i in items)
    assert [i["added"] for i in items] == sorted((i["added"] for i in items), reverse=True)     # newest first


def test_each_user_has_a_time_zone(client, admin):
    h = admin["h"]
    me = client.get("/api/auth/me", headers=h).json()
    assert me["usertimezone"] == "America/New_York"                      # staff start on Eastern
    staff = next(u for u in client.get("/api/admin/users", params={"q": "root@"}, headers=h).json()["items"]
                 if u["email"] == "root@tripproof.test")
    assert client.patch(f"/api/admin/users/{staff['recordid']}", json={"timezone": "Mars/Olympus"}, headers=h).status_code == 400
    assert client.put("/api/auth/me", json={"timezone": "America/Chicago"}, headers=h).json()["usertimezone"] == "America/Chicago"
    assert client.get("/api/auth/me", headers=h).json()["usertimezone"] == "America/Chicago"
    assert client.get("/api/auth/me", headers=h).json()["timezone"]        # the account's zone is still there for business dates
    client.put("/api/auth/me", json={"timezone": "America/New_York"}, headers=h)


def test_fee_schedule(client, admin):
    h = admin["h"]
    fees = client.get("/api/admin/fees", headers=h).json()
    assert [f["code"] for f in fees] == ["MVR", "CDLIS", "PSP", "CLEARINGHOUSE", "BACKGROUND"]
    assert all(f["price"] is None for f in fees)                          # prices start unset
    mvr = fees[0]
    assert client.put(f"/api/admin/fees/{mvr['recordid']}", json={**mvr, "price": 14.5}, headers=h).status_code == 200
    assert float(client.get("/api/admin/fees", headers=h).json()[0]["price"]) == 14.5
    assert client.put(f"/api/admin/fees/{mvr['recordid']}", json={**mvr, "price": -1}, headers=h).status_code == 400
    assert client.put(f"/api/admin/fees/{mvr['recordid']}", json={**mvr, "price": 20}, headers=admin["support"]).status_code == 403
    assert client.post("/api/admin/fees", json={"code": "mvr", "name": "Dup"}, headers=h).status_code == 409
    assert client.post("/api/admin/fees", json={"code": "drug", "name": "Drug Test", "price": 45}, headers=h).status_code == 200


