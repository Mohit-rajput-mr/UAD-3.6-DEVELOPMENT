"""Keeps each case's Sales Comparison Map current, drawn by the map tool itself.

The report's map is not drawn by separate code: the in-app Location Map tool
(``ui/map/index.html``) is opened in a headless browser at the Appendix E
frame (full page, 45 x 48 picas less 6 pt -- 704 x 752 CSS px), restores the
case's own map state (pins, callout positions, label size, layer), places any
property it has not placed yet, waits until every tile is drawn, and exports
the PNG with the same code as its "Save to the report" button.  What the
appraiser arranges in the tool is therefore exactly what prints.

Appendix E and B-1 define one map for the Sales Comparison Approach -- the
Sales Comparison Map (ImageCategoryType SalesComparableMap).  No aerial map is
drawn; any left over from earlier builds is removed.
"""
from __future__ import annotations

import base64
import threading
import time
from typing import Callable

from uad import bind, edit, maps

CAPTION = "Sales Comparison Map"
RETIRED = ("Aerial Map",)          # a full-page aerial "map" filed with the comparables
# The Site section's aerial view is an exhibit photograph like any other
# (A-1 ImageCategoryType SiteExhibit): it prints at the exhibit box's size,
# two to a row, and never as a page of its own.
AERIAL_CAPTION = "Aerial Map"
AERIAL_KEY = "Site Aerial Map"
SITE = 4


class Mapper:
    def __init__(self, store: Callable, prefs: Callable, set_prefs: Callable,
                 server: Callable[[], dict | None]):
        self._store, self._prefs, self._set_prefs, self._server = store, prefs, set_prefs, server
        self._due: dict[str, float] = {}
        self._status: dict[str, dict] = {}
        self._lock = threading.Condition()
        self._render_lock = threading.Lock()
        threading.Thread(target=self._run, name="mapper", daemon=True).start()

    def status(self, case_id: str) -> dict:
        return self._status.get(case_id, {"state": "idle"})

    # ---------------------------------------------------------------- when
    def changed(self, case_id: str) -> None:
        if self._prefs(case_id).get("autoMaps") is False:
            return
        with self._lock:
            self._due[case_id] = time.time() + 3.0         # let a burst of edits settle
            self._lock.notify_all()

    def _run(self) -> None:
        while True:
            with self._lock:
                while not self._due:
                    self._lock.wait()
                case_id, when = min(self._due.items(), key=lambda kv: kv[1])
                wait = when - time.time()
                if wait > 0:
                    self._lock.wait(wait)
                    continue
                self._due.pop(case_id)
            try:
                self.generate(case_id, force=False)
            except Exception as exc:
                self._status[case_id] = {"state": "failed", "problems": [repr(exc)]}

    # ---------------------------------------------------------------- what
    def signature(self, case_id: str) -> str:
        return maps.signature(maps.places(self._store().tree(case_id).getroot()))

    def generate(self, case_id: str, *, force: bool = True) -> dict:
        st = self._store()
        if not st.xml_path(case_id).exists():
            return {"state": "idle"}
        self.retire(case_id)
        ps = maps.places(st.tree(case_id).getroot())
        if len(ps) < 2:
            self._status[case_id] = {"state": "idle", "problems": ["there are no comparables to map yet"]}
            return self._status[case_id]
        have = self._prefs(case_id).get("generatedMaps") or {}
        sig = maps.signature(ps)
        if not force and have.get("signature") == sig and any(
                m.media_id == have.get(CAPTION) for m in st.media(case_id)):
            self._status[case_id] = {"state": "current", "problems": []}
            return self._status[case_id]
        server = self._server()
        if not server:
            self._status[case_id] = {"state": "failed",
                                     "problems": ["the map is drawn by the running server's map tool"]}
            return self._status[case_id]
        self._status[case_id] = {"state": "drawing"}
        with self._render_lock:
            result = render(server, case_id)
        if result.get("error"):
            self._status[case_id] = {"state": "failed", "problems": [result["error"]]}
            return self._status[case_id]
        self.store_png(case_id, result["png"], signature=sig)
        self.write_coordinates(case_id, result.get("state") or {})
        self._status[case_id] = {"state": "current", "problems": []}
        return self._status[case_id]

    # --------------------------------------------------------------- where
    def retire(self, case_id: str) -> None:
        """Maps the guidelines do not define are not kept."""
        st = self._store()
        for m in st.media(case_id):
            if m.category == "map" and (m.caption or "").strip() in RETIRED:
                st.remove_media(case_id, m.media_id)
        have = self._prefs(case_id).get("generatedMaps") or {}
        if any(k in have for k in RETIRED):
            self._set_prefs(case_id, {"generatedMaps": {k: v for k, v in have.items() if k not in RETIRED}})

    def aerial(self, case_id: str) -> dict:
        """Draw the subject from above into the Site exhibits."""
        st = self._store()
        ps = maps.places(st.tree(case_id).getroot())
        if not ps or not (ps[0].address or "").strip():
            return {"state": "idle", "problems": ["enter the subject's address first"]}
        server = self._server()
        if not server:
            return {"state": "failed", "problems": ["the map is drawn by the running server's map tool"]}
        with self._render_lock:
            result = render(server, case_id, aerial=True)
        if result.get("error"):
            return {"state": "failed", "problems": [result["error"]]}
        have = self._prefs(case_id).get("generatedMaps") or {}
        for m in st.media(case_id):
            if m.media_id == have.get(AERIAL_KEY):
                st.remove_media(case_id, m.media_id)
        name = "SiteAerialMap.png"
        (st.media_dir(case_id) / name).write_bytes(result["png"])
        item = st.add_media(case_id, category="other", filename=name, caption=AERIAL_CAPTION,
                            section=SITE, size=len(result["png"]), content_type="image/png")
        self._set_prefs(case_id, {"generatedMaps": {**have, AERIAL_KEY: item.media_id}})
        st.touch(case_id)
        return {"state": "current", "problems": [], "media_id": item.media_id}

    def store_png(self, case_id: str, png: bytes, *, signature: str = "") -> str:
        """Put the map into the report as its Sales Comparison Map."""
        st = self._store()
        prefs = self._prefs(case_id)
        have = prefs.get("generatedMaps") or {}
        for m in st.media(case_id):
            if m.category == "map" and ((m.caption or "").strip() == CAPTION or m.media_id == have.get(CAPTION)):
                st.remove_media(case_id, m.media_id)
        name = "SalesCompMap.png"
        (st.media_dir(case_id) / name).write_bytes(png)
        item = st.add_media(case_id, category="map", filename=name, caption=CAPTION,
                            section=22, size=len(png), content_type="image/png")
        # the document's own Sales Comparison Map box shows this map
        M = f"{{{bind.MISMO}}}"
        fills = {k: v for k, v in (prefs.get("fills") or {}).items() if v != have.get(CAPTION)}
        for image in st.tree(case_id).getroot().iter(f"{M}IMAGE"):
            if image.findtext(f"{M}ImageCategoryType", "").strip() == "SalesComparableMap":
                loc = image.findtext(f"{M}ImageFileLocationIdentifier", "").strip()
                if loc:
                    fills[loc] = item.media_id
        self._set_prefs(case_id, {"fills": fills,
                                  "generatedMaps": {**{k: v for k, v in have.items() if k == AERIAL_KEY},
                                                    CAPTION: item.media_id,
                                                    "signature": signature or self.signature(case_id)}})
        st.touch(case_id)
        return item.media_id

    def write_coordinates(self, case_id: str, state: dict) -> None:
        """A-1 requires coordinates; where the document lacks usable ones, the
        position the map settled on is written back, so XML and map agree."""
        st = self._store()
        tree = st.tree(case_id)
        ps = maps.places(tree.getroot())
        placed = [state.get("subject") or {}] + list(state.get("comps") or [])
        subject = ps[0] if ps else None
        wrote = False
        for p, spot in zip(ps, placed):
            lat, lon = spot.get("lat"), spot.get("lng")
            if lat is None or lon is None or p.node is None:
                continue
            if maps.plausible(p, None if p is subject else subject):
                continue
            geo, _ = edit.ensure_path(p.node, ["LOCATION_IDENTIFIER", "GEOSPATIAL_INFORMATION"])
            for name, value in (("LatitudeIdentifier", lat), ("LongitudeIdentifier", lon)):
                node = geo.find(f"{{{bind.MISMO}}}{name}")
                if node is None:
                    node = edit.insert_ordered(geo, name)
                node.text = f"{float(value):.6f}"
            if p is subject:
                p.lat, p.lon = float(lat), float(lon)
            wrote = True
        if wrote:
            st.save_tree(case_id, tree)


def render(server: dict, case_id: str, timeout: float = 90.0, *, aerial: bool = False) -> dict:
    """Open the map tool headless for this case and take its exported PNG."""
    from uad.report import flow
    from uad.report.browser import sync_playwright  # optional: BrowserUnavailable without Chromium

    flow._allow_subprocesses()
    base = server["base"].rstrip("/")
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--enable-unsafe-swiftshader", "--use-angle=swiftshader"])
        try:
            context = browser.new_context(viewport={"width": 900, "height": 900},
                                          device_scale_factor=2)
            host = base.split("//", 1)[1].split(":")[0]
            context.add_cookies([{"name": server["cookie"], "value": server["token"],
                                  "domain": host, "path": "/"}])
            page = context.new_page()
            page.goto(f"{base}/ui/map/index.html?case={case_id}&render=1&seed=1"
                      + ("&aerial=1" if aerial else ""),
                      wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function("() => !!window.__uadRendered", timeout=int(timeout * 1000))
            out = page.evaluate("() => window.__uadRendered")
        finally:
            browser.close()
    if not out or out.get("error"):
        return {"error": (out or {}).get("error") or "the map tool returned nothing"}
    data = out["png"].split(",", 1)[1]
    return {"png": base64.b64decode(data), "state": out.get("state") or {}}
