"""Where the subject and the comparables are, for the Sales Comparison Map.

The map itself is drawn by the in-app Location Map tool (``app/mapper.py``
opens it headless), so the printed map is the tool's.  This module reads the
places from the document, judges whether a coordinate can be right, gives
distance and direction, and fingerprints what the map shows so it is redrawn
only when that changes.  A-1 requires LatitudeIdentifier / LongitudeIdentifier
for the subject (0100.0015/.0016) and each comparable.
"""
from __future__ import annotations

import hashlib
import io
import json
import math
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from . import bind
from .report import comparables, fonts

M = f"{{{bind.MISMO}}}"
ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / "_work" / "tilecache"
CONFIG = Path(__file__).resolve().parents[1] / "config" / "maps.json"

# Appendix E: 45 x 48 picas less 6 pt each side, drawn at 2.5 px per point
PT_W, PT_H = 45 * 12 - 12, 48 * 12 - 12
SCALE = 2.5
W, H = int(PT_W * SCALE), int(PT_H * SCALE)
TILE = 256
USER_AGENT = "UAD36-FormFiller/1.0 (appraisal report maps)"

DEFAULTS = {
    "street": {"tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
               "credit": "Map data © OpenStreetMap contributors"},
    "aerial": {"tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
                         "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}",
                         "https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"],
               "credit": "Imagery © Esri, Maxar, Earthstar Geographics"},
    "geocoder": "https://nominatim.openstreetmap.org/search",
}

# callout colours, after the reports appraisers already read
STYLE = {"subject": ((255, 255, 255), (60, 60, 60)),
         "sale": ((255, 241, 118), (176, 150, 0)),
         "listing": ((206, 190, 240), (110, 80, 180))}
LISTING = {"Active", "Pending", "ActiveUnderContract", "ComingSoon", "Contingent"}


@dataclass
class Place:
    kind: str                 # subject / sale / listing
    title: str                # "Subject", "Comparable Sale 1"
    lines: list[str]
    address: str
    number: int = 0
    lat: float | None = None
    lon: float | None = None
    source: str = ""          # document / geocoded
    note: str = ""            # distance and direction, filled in later
    node: etree._Element | None = field(default=None, repr=False)


def config() -> dict:
    if CONFIG.is_file():
        return {**DEFAULTS, **json.loads(CONFIG.read_text(encoding="utf-8"))}
    return DEFAULTS


# ------------------------------------------------------------------ places
def _address(prop) -> tuple[str, list[str]]:
    a = prop.find(f"{M}ADDRESS")
    if a is None:
        return "", []
    get = lambda n: (a.findtext(f"{M}{n}") or "").strip()      # noqa: E731
    line1 = get("AddressLineText")
    if get("AddressUnitIdentifier"):
        line1 = f"{line1} {get('AddressUnitDesignatorType')} {get('AddressUnitIdentifier')}".strip()
    line2 = ", ".join(x for x in (get("CityName"), f"{get('StateCode')} {get('PostalCode')}".strip()) if x)
    full = ", ".join(x for x in (line1, line2) if x)
    return full, [x for x in (line1, line2) if x]


def _coords(prop) -> tuple[float | None, float | None]:
    geo = prop.find(f"{M}LOCATION_IDENTIFIER/{M}GEOSPATIAL_INFORMATION")
    if geo is None:
        return None, None
    try:
        return float(geo.findtext(f"{M}LatitudeIdentifier")), float(geo.findtext(f"{M}LongitudeIdentifier"))
    except (TypeError, ValueError):
        return None, None


def places(root, kind: str = "sales") -> list[Place]:
    out = []
    subject = bind.subject(root)
    if subject is not None:
        full, lines = _address(subject)
        lat, lon = _coords(subject)
        out.append(Place("subject", "Subject", lines, full, 0, lat, lon, "document", node=subject))
    _sheet, role, _t = comparables.SHEETS[kind]
    for n, prop in enumerate(comparables.properties(root, role), start=1):
        full, lines = _address(prop)
        lat, lon = _coords(prop)
        status = (prop.findtext(f".//{M}ListingStatusType") or "").strip()
        k = "listing" if status in LISTING else "sale"
        title = f"Comparable {'Listing' if k == 'listing' else 'Sale'} {n}"
        out.append(Place(k, title, lines, full, n, lat, lon, "document", node=prop))
    return out


def miles(a: Place, b: Place) -> float:
    r = 3958.8
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def bearing(a: Place, b: Place) -> str:
    y = math.sin(math.radians(b.lon - a.lon)) * math.cos(math.radians(b.lat))
    x = (math.cos(math.radians(a.lat)) * math.sin(math.radians(b.lat))
         - math.sin(math.radians(a.lat)) * math.cos(math.radians(b.lat)) * math.cos(math.radians(b.lon - a.lon)))
    deg = (math.degrees(math.atan2(y, x)) + 360) % 360
    return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][int((deg + 22.5) // 45) % 8]


def plausible(p: Place, subject: Place | None) -> bool:
    if p.lat is None or p.lon is None:
        return False
    if not (17.0 <= p.lat <= 72.0 and -180.0 <= p.lon <= -64.0):   # the US and its territories
        return False
    if subject is not None and p is not subject and subject.lat is not None:
        return miles(subject, p) <= 50
    return True


def geocode(address: str) -> tuple[float, float] | None:
    """Look an address up (Nominatim, once per second, cached)."""
    if not address:
        return None
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"geo-{hashlib.sha1(address.lower().encode()).hexdigest()[:16]}.json"
    if key.exists():
        data = json.loads(key.read_text())
        return tuple(data) if data else None
    url = config()["geocoder"] + "?" + urllib.parse.urlencode(
        {"q": address, "format": "json", "limit": 1, "countrycodes": "us"})
    time.sleep(1.0)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=12) as r:
            hits = json.loads(r.read())
    except Exception:
        return None
    found = (float(hits[0]["lat"]), float(hits[0]["lon"])) if hits else None
    key.write_text(json.dumps(found))
    return found


_SUGGEST_LOCK = __import__("threading").Lock()
_SUGGEST_LAST = [0.0]


def suggest(query: str, limit: int = 5) -> list[dict]:
    """Real addresses matching what has been typed, split into the parts a
    report address is made of.  They are offered, never written on their own:
    the appraiser picks one, and can still change every part of it.

    Nominatim's usage policy allows one request a second; requests are spaced
    and every answer is cached."""
    query = " ".join((query or "").split())
    if len(query) < 4:
        return []
    CACHE.mkdir(parents=True, exist_ok=True)
    key = CACHE / f"sug-{hashlib.sha1(query.lower().encode()).hexdigest()[:16]}.json"
    if key.exists():
        return json.loads(key.read_text(encoding="utf-8"))
    url = config()["geocoder"] + "?" + urllib.parse.urlencode(
        {"q": query, "format": "jsonv2", "addressdetails": 1, "limit": limit, "countrycodes": "us"})
    with _SUGGEST_LOCK:
        wait = 1.05 - (time.time() - _SUGGEST_LAST[0])
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=12) as r:
                hits = json.loads(r.read())
        except Exception:
            return []
        finally:
            _SUGGEST_LAST[0] = time.time()
    typed_number = (query.split()[0] if query.split() and query.split()[0].isdigit() else "")
    out, seen = [], set()
    for h in hits:
        a = h.get("address") or {}
        road = a.get("road") or a.get("pedestrian") or a.get("residential") or ""
        if not road:
            continue
        number = a.get("house_number") or ""
        state = (a.get("ISO3166-2-lvl4") or "").replace("US-", "")
        item = {
            "street": " ".join(x for x in (number or typed_number, road) if x),
            "house_number_matched": bool(number),
            "city": a.get("city") or a.get("village") or a.get("hamlet") or a.get("town") or "",
            "state": state if len(state) == 2 else "",
            "postal_code": (a.get("postcode") or "")[:10],
            "county": a.get("county") or "",
            "lat": float(h["lat"]), "lng": float(h["lon"]),
        }
        item["label"] = ", ".join(x for x in (item["street"], item["city"],
                                              f"{item['state']} {item['postal_code']}".strip()) if x)
        if item["label"] in seen:
            continue
        seen.add(item["label"])
        out.append(item)
    key.write_text(json.dumps(out), encoding="utf-8")
    return out


def locate(ps: list[Place]) -> list[str]:
    """Fill in coordinates the document lacks; return what could not be placed."""
    subject = next((p for p in ps if p.kind == "subject"), None)
    if subject is not None and not plausible(subject, None):
        found = geocode(subject.address)
        if found:
            subject.lat, subject.lon, subject.source = found[0], found[1], "geocoded"
    problems = []
    for p in ps:
        if p is subject:
            if not plausible(p, None):
                problems.append(f"{p.title}: no usable coordinates and the address could not be found")
            continue
        if not plausible(p, subject):
            found = geocode(p.address)
            if found:
                p.lat, p.lon, p.source = found[0], found[1], "geocoded"
        if not plausible(p, subject):
            problems.append(f"{p.title}: no usable coordinates and the address could not be found")
    if subject is not None and subject.lat is not None:
        for p in ps:
            if p is not subject and p.lat is not None:
                p.note = f"{miles(subject, p):.2f} miles {bearing(subject, p)}"
    return problems


def signature(ps: list[Place]) -> str:
    """Changes when anything the map shows changes."""
    raw = json.dumps([(p.kind, p.title, p.address, p.lat, p.lon) for p in ps])
    return hashlib.sha1(raw.encode()).hexdigest()[:16]
