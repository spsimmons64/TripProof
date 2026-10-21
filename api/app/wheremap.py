"""What goes on the dashboard map: the company's base, and where the drivers last were.

The base is a street address, so it has to be turned into a position once. That is done here
against Nominatim, OpenStreetMap's own geocoder, and the answer is kept on the account - one
lookup for the life of an address rather than one per page load. Nominatim asks callers to
identify themselves and to stay under a request a second, and caching the result is what keeps
us comfortably inside that.

Driver positions come from `driverlocations`, which GPS will fill. Until it does the map has
the base on it and says so. A driver's HOME address is deliberately not used as a stand-in: a
map showing four drivers parked at their houses looks like live tracking and is not.
"""

import json
import logging
import urllib.parse
import urllib.request

from datetime import timedelta
from math import asin, cos, radians, sin, sqrt

from sqlalchemy.engine import Connection

from app.db import row, rows, run, utcnow

log = logging.getLogger(__name__)

NOMINATIM = "https://nominatim.openstreetmap.org/search"
# MapTiler, where a key is configured: vector tiles for the renderer, and a geocoder that
# answers US street addresses far more often than Nominatim does.
MAPTILER_STYLE = "https://api.maptiler.com/maps/streets-v2/style.json?key={key}"
MAPTILER_GEOCODE = "https://api.maptiler.com/geocoding/{q}.json"
# Nominatim's policy asks for a real identifier and a contact, so somebody with a problem can
# reach whoever is making the requests.
AGENT = "TripProof/1.0 (+https://tripproofonline.com)"
TIMEOUT = 6


def style_url() -> str | None:
    """The map style the browser should render, or None to fall back to raster OSM."""
    from app.config import settings
    key = (settings.maptiler_key or "").strip()
    return MAPTILER_STYLE.format(key=key) if key else None


def _maptiler(address: str) -> tuple[float, float, str] | None:
    """Ask MapTiler where an address is. None where there is no key or no answer."""
    from app.config import settings
    # The server-only key first. The browser key is locked to our origin in the MapTiler account
    # and a server sends no Referer, so it is refused 403 - which is why every address booked
    # before this was stored without coordinates.
    key = (settings.maptiler_server_key or settings.maptiler_key or "").strip()
    if not key or not address:
        return None
    url = (MAPTILER_GEOCODE.format(q=urllib.parse.quote(address))
           + "?" + urllib.parse.urlencode({"key": key, "country": "us", "limit": 1}))
    try:
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:    # noqa: S310
            got = json.loads(answer.read().decode())
    except Exception as e:                                             # noqa: BLE001
        log.warning("maptiler geocode failed for %r: %s", address, e)
        return None
    for feature in got.get("features") or []:
        lng, lat = (feature.get("center") or [None, None])[:2]
        if lat is None:
            continue
        # MapTiler says what it matched on, so the pin can be honest about itself rather
        # than every answer claiming to be the front door.
        kind = (feature.get("place_type") or ["address"])[0]
        return float(lat), float(lng), ("address" if kind == "address" else kind)
    return None


def _address_of(account: dict) -> str:
    parts = [account.get("address1"), account.get("address2"), account.get("city"),
             account.get("state"), account.get("zip")]
    return ", ".join(p.strip() for p in parts if (p or "").strip())


def _ask(**terms) -> tuple[float, float] | None:
    """One query to Nominatim. None where it cannot answer or cannot be reached."""
    terms.update(format="json", limit=1)
    url = f"{NOMINATIM}?{urllib.parse.urlencode(terms)}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:    # noqa: S310
            got = json.loads(answer.read().decode())
    except Exception as e:                                             # noqa: BLE001
        # A map that cannot place the base is a map with the drivers on it, not an error page.
        log.warning("geocode failed for %r: %s", terms, e)
        return None
    if not got:
        return None
    try:
        return float(got[0]["lat"]), float(got[0]["lon"])
    except (KeyError, TypeError, ValueError):
        return None


def _lookup(account: dict) -> tuple[float, float, str] | None:
    """Where this address is, and how precisely. None where nothing resolves.

    A ladder, because OpenStreetMap's coverage of US street addresses is patchy - it does not
    hold this company's own street, and it is not unusual. Rather than give up and show no
    map, the lookup falls back to the town and then to the postcode, and says which it got so
    the screen can call the pin approximate instead of implying it is the front door. Google's
    geocoder answers the first rung far more often, which is what the swap buys.
    """
    # MapTiler first where it is configured, because it answers the street itself far more
    # often. The Nominatim ladder below is the keyless fallback, and the rung it reaches is
    # what the screen calls the pin.
    better = _maptiler(_address_of(account))
    if better:
        return better
    street = " ".join(x for x in (account.get("address1"), account.get("address2")) if x)
    city, state = (account.get("city") or ""), (account.get("state") or "")
    postcode = (account.get("zip") or "")
    for terms, precision in (
        ({"street": street, "city": city, "state": state, "postalcode": postcode}, "address"),
        ({"city": city, "state": state, "postalcode": postcode}, "town"),
        ({"postalcode": postcode}, "postcode"),
    ):
        if not all(terms.values()):
            continue
        found = _ask(country="US", **terms)
        if found:
            return found[0], found[1], precision
    return None


def base_of(conn: Connection, accountid: str) -> dict | None:
    """Where this company operates from, looking it up if nobody has yet.

    Looked up again when the address has changed since last time - `locatedfor` holds the
    address the stored position belongs to, so a company that moves does not keep a pin on
    the place it left."""
    a = row(conn, """
        SELECT name, address1, address2, city, state, zip, latitude, longitude, locatedfor
        FROM accounts WHERE recordid = :a
    """, a=accountid)
    if not a:
        return None
    address = _address_of(a)
    if not address:
        return None
    # `locatedfor` holds the address AND the precision it was found at, so a stored town-level
    # pin is not mistaken later for a building-level one.
    if a["latitude"] is not None and (a["locatedfor"] or "").startswith(address + "|"):
        return {"name": a["name"], "address": address,
                "lat": float(a["latitude"]), "lng": float(a["longitude"]),
                "precision": (a["locatedfor"] or "|").split("|")[-1]}
    found = _lookup(a)
    if not found:
        return None
    lat, lng, precision = found
    run(conn, """
        UPDATE accounts SET latitude = :lat, longitude = :lng, locatedon = :now,
                            locatedfor = :addr
        WHERE recordid = :a
    """, lat=lat, lng=lng, now=utcnow(), addr=f"{address}|{precision}"[:255], a=accountid)
    return {"name": a["name"], "address": address, "lat": lat, "lng": lng,
            "precision": precision}


def set_base(conn: Connection, accountid: str, lat: float, lng: float) -> bool:
    """Put the base where somebody says it is.

    Recorded at `address` precision because a person pointing at their own building is better
    evidence than any geocoder - and because that is what stops it being looked up again and
    quietly moved back to the middle of the town.
    """
    a = row(conn, "SELECT address1, address2, city, state, zip FROM accounts WHERE recordid = :a",
            a=accountid)
    if not a:
        return False
    return bool(run(conn, """
        UPDATE accounts SET latitude = :lat, longitude = :lng, locatedon = :now,
                            locatedfor = :addr
        WHERE recordid = :a
    """, lat=lat, lng=lng, now=utcnow(), addr=f"{_address_of(a)}|address"[:255],
        a=accountid).rowcount)


# A gap longer than this ends one stint and begins another. A van parked overnight and
# started again in the morning is two journeys, and averaging across the night would report a
# speed nobody drove.
STINT_GAP = timedelta(minutes=20)


def _miles(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = (radians(a[0]), radians(a[1]), radians(b[0]), radians(b[1]))
    h = (sin((lat2 - lat1) / 2) ** 2
         + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2)
    return 3958.8 * 2 * asin(sqrt(h))


# A jump larger than this between consecutive fixes did not happen on a road: the device was
# out of signal and came back somewhere else. Counting the straight line across it would bill
# a passenger for a journey through whatever lay between.
JUMP_MILES = 3.0


def trail_miles(conn: Connection, accountid: str, driverid: str, start, end) -> dict:
    """How far this vehicle actually drove between two moments.

    Summed from its own fixes, which is the only distance that can answer "how did you get
    that figure" with something other than an estimate. Returns the miles, how many fixes
    they were measured across, and what was skipped - because a leg measured from four fixes
    over twenty minutes is not evidence of anything and the caller has to be able to tell.
    """
    fixes = rows(conn, """
        SELECT latitude, longitude, recordedon
        FROM driverlocations
        WHERE accountid = :a AND driverid = :d
          AND recordedon >= :start AND recordedon <= :end
        ORDER BY recordedon
    """, a=accountid, d=driverid, start=start, end=end)
    miles, skipped = 0.0, 0
    for a, b in zip(fixes, fixes[1:]):
        step = _miles((float(a["latitude"]), float(a["longitude"])),
                      (float(b["latitude"]), float(b["longitude"])))
        if step > JUMP_MILES:
            skipped += 1
            continue
        miles += step
    return {"miles": round(miles, 2), "fixes": len(fixes), "gaps": skipped}


CENSUS = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"


def _census(address: str) -> tuple[float, float] | None:
    """Ask the US Census Bureau where an address is.

    This is the one that actually answers. MapTiler holds the only key this installation has, and
    that key is locked to our own origin in the MapTiler account - correctly, because it ships
    inside the browser bundle where anyone can read it. A server sends no Referer, so every
    server-side geocode was refused 403 and silently fell through. OpenStreetMap, the fallback,
    simply does not know most residential US streets: it failed on an address in Trinity, Florida
    that the Census matched to the house number.

    No key, no origin, no quota to leak - and it is the address range database the post office and
    everybody else is ultimately quoting. For a product that geocodes American street addresses
    and nothing else, it is a better source than either.

    `benchmark` is which vintage of the address file to match against; Public_AR_Current is the
    one that is kept up to date.
    """
    if not (address or "").strip():
        return None
    url = CENSUS + "?" + urllib.parse.urlencode(
        {"address": address, "benchmark": "Public_AR_Current", "format": "json"})
    try:
        req = urllib.request.Request(url, headers={"User-Agent": AGENT})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:      # noqa: S310
            got = json.loads(answer.read().decode())
    except Exception as e:                                                # noqa: BLE001
        log.warning("census geocode failed for %r: %s", address, e)
        return None
    for match in (got.get("result") or {}).get("addressMatches") or []:
        at = match.get("coordinates") or {}
        if at.get("y") is not None and at.get("x") is not None:
            return float(at["y"]), float(at["x"])
    return None


def place(address: str) -> tuple[float, float] | None:
    """Where an address is, for a trip that is being booked.

    Same ladder as the company base: MapTiler where a key is configured, then OpenStreetMap
    getting progressively less exact. Looked up ONCE, when the trip is written, because a
    dispatch screen sorting twenty drivers by distance must not geocode on every page load -
    and because the answer is about a place, which does not move.
    """
    if not (address or "").strip():
        return None
    # The Census first: it is free, needs no key, and knows American street addresses better than
    # either of the others. MapTiler second, for the day a server-side key exists. OpenStreetMap
    # last, because it is the one most likely to answer with the middle of a town.
    found = _census(address)
    if found:
        return found
    better = _maptiler(address)
    if better:
        return better[0], better[1]
    plain = _ask(q=address, countrycodes="us")
    return plain if plain else None


def drivers_at(conn: Connection, accountid: str) -> list[dict]:
    """Each driver's most recent position, and what the trail behind it says.

    The dashboard asks "where is everybody" - but somebody hovering a pin asks more than
    that, so the current stint comes too: when it started, how far it has run, how fast on
    average. Worked out from the fixes rather than stored, because a stored summary is a
    second copy of the trail and would drift from it.

    One query for the trail of everyone who has reported in the last day. That is fine for a
    yard of vans and wrong for a fleet of hundreds - see the note in db/migrations/266.
    """
    latest = rows(conn, """
        SELECT d.recordid AS driverid,
               TRIM(CONCAT(COALESCE(d.firstname, ''), ' ', COALESCE(d.lastname, ''))) AS name,
               l.latitude, l.longitude, l.accuracy, l.speed, l.heading, l.recordedon,
               v.externalid AS vehicle, v.make, v.model
        FROM driverlocations l
        JOIN drivers d ON d.recordid = l.driverid
        LEFT JOIN vehicles v ON v.recordid = l.vehicleid
        JOIN (
            SELECT driverid, MAX(recordedon) AS newest
            FROM driverlocations WHERE accountid = :a GROUP BY driverid
        ) newest ON newest.driverid = l.driverid AND newest.newest = l.recordedon
        WHERE l.accountid = :a AND d.deleted IS NULL
        GROUP BY d.recordid
        ORDER BY d.lastname, d.firstname
    """, a=accountid)
    if not latest:
        return []
    trail = rows(conn, """
        SELECT driverid, latitude, longitude, speed, recordedon
        FROM driverlocations
        WHERE accountid = :a AND recordedon >= :since
        ORDER BY driverid, recordedon
    """, a=accountid, since=utcnow() - timedelta(hours=24))

    # The leg each driver is on, if any: the one whose window covers their latest fix. A leg
    # still open - no drop-off recorded - counts from its pickup onward, because that is
    # exactly the state "on a job right now" means.
    legs = rows(conn, """
        SELECT l.driverid, l.legnumber, l.pickupat, l.dropoffat,
               t.externalid, t.tripdate, t.servicelevel
        FROM triplegs l
        JOIN trips t ON t.recordid = l.tripid AND t.deleted IS NULL
        WHERE l.accountid = :a AND l.driverid IS NOT NULL
          AND l.pickupat >= :since
        ORDER BY l.pickupat
    """, a=accountid, since=utcnow() - timedelta(hours=24))
    onleg: dict[str, dict] = {}
    for who in latest:
        when = who["recordedon"]
        for leg in legs:
            if leg["driverid"] != who["driverid"]:
                continue
            if leg["pickupat"] <= when and (leg["dropoffat"] is None
                                            or when <= leg["dropoffat"]):
                onleg[who["driverid"]] = leg

    walked: dict[str, list[dict]] = {}
    for fix in trail:
        walked.setdefault(fix["driverid"], []).append(fix)

    for who in latest:
        points = walked.get(who["driverid"], [])
        # Back from the newest fix until the trail breaks. That is this journey.
        stint = []
        for fix in reversed(points):
            if stint and stint[-1]["recordedon"] - fix["recordedon"] > STINT_GAP:
                break
            stint.append(fix)
        stint.reverse()
        miles, moving = 0.0, 0
        for a, b in zip(stint, stint[1:]):
            miles += _miles((float(a["latitude"]), float(a["longitude"])),
                            (float(b["latitude"]), float(b["longitude"])))
            if (b["speed"] or 0) > 1:
                moving += 1
        began = stint[0]["recordedon"] if stint else who["recordedon"]
        ran = (who["recordedon"] - began).total_seconds()
        who["since"] = began
        who["minutes"] = round(ran / 60)
        who["miles"] = round(miles, 1)
        # Average over the whole stint including the waiting, which is what "how long has
        # this taken" means to a dispatcher - not the average of the speeds reported.
        who["avgmph"] = round(miles / (ran / 3600), 1) if ran > 60 and miles else 0
        who["fixes"] = len(stint)
        who["standing"] = bool(stint) and (stint[-1]["speed"] or 0) <= 1
        leg = onleg.get(who["driverid"])
        who["trip"] = leg["externalid"] if leg else None
        who["leg"] = leg["legnumber"] if leg else None
        who["service"] = leg["servicelevel"] if leg else None
    return latest


def enroute(drivers: list[dict]) -> int:
    """How many are on a job right now. Counted off the same answer the map is drawn from,
    so the figure and the pins can never disagree."""
    return sum(1 for d in drivers if d.get("trip"))
