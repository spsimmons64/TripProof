"""How long the drive is from one place to another - for working a pickup time back from an
appointment.

OSRM (the Open Source Routing Machine) on OpenStreetMap roads: the fastest route by car and how
long it takes at the roads' speeds. The public server is meant for light use; `settings.osrm_url`
points it at a server of the company's own when there is one. When no route comes back, the
straight line is used instead - stretched for roads and driven at town speed - and said to be so.
"""

import json
import logging
import urllib.request
from functools import lru_cache

from app import dispatch
from app.config import settings

log = logging.getLogger(__name__)
TIMEOUT = 8
# The straight-line fallback: roads are about a third longer than the crow flies, and a van in
# town averages about 25 mph once lights and turns are counted.
ROAD_FACTOR = 1.3
TOWN_MPH = 25


def drive(a: tuple[float, float], b: tuple[float, float]) -> dict:
    """{minutes, miles, routed}: routed False when it is the straight-line estimate. Asked to the
    nearest hundred metres or so, and remembered: the board asks again every few seconds while a
    trip is under way, and the road between two points does not change in that time."""
    return dict(_drive(round(a[0], 3), round(a[1], 3), round(b[0], 3), round(b[1], 3)))


@lru_cache(maxsize=2048)
def _drive(alat: float, alng: float, blat: float, blng: float) -> tuple:
    a, b = (alat, alng), (blat, blng)
    base = (settings.osrm_url or "https://router.project-osrm.org").rstrip("/")
    url = f"{base}/route/v1/driving/{a[1]:.6f},{a[0]:.6f};{b[1]:.6f},{b[0]:.6f}?overview=false"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "TripProof/1.0"})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as answer:          # noqa: S310
            got = json.loads(answer.read().decode())
        route = (got.get("routes") or [None])[0]
        if got.get("code") == "Ok" and route:
            return tuple({"minutes": max(1, round(route["duration"] / 60)),
                          "miles": round(route["distance"] / 1609.344, 1), "routed": True}.items())
    except Exception as e:                                                    # noqa: BLE001
        log.warning("route lookup failed: %s", e)
    miles = dispatch._miles(a, b) * ROAD_FACTOR
    return tuple({"minutes": max(1, round(miles / TOWN_MPH * 60)), "miles": round(miles, 1), "routed": False}.items())
