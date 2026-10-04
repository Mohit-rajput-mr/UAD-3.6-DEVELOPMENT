"""Street View captures for comparables that have no usable listing photo.

    python tools/streetview.py --out DIR name=lat,lon[,heading] ...

Owner instruction (2026-10-02, 601 Euclid): rental comparable photos come from
Google Maps.  A headless Edge is driven over CDP with the bridge's own client;
Google's consent page is answered "Reject all" (the privacy-preserving choice),
then the Street View panorama at the coordinates is captured.  Every capture is
LOOKED AT before it is placed (CATALOG E-047): Street View can open facing the
wrong side of the street.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bridge import cdp  # noqa: E402

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333


def _page():
    for _ in range(40):
        try:
            tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json/list", timeout=3))
            pages = [t for t in tabs if t.get("type") == "page"]
            if pages:
                return cdp.Page(pages[0]["webSocketDebuggerUrl"], timeout=60)
        except OSError:
            pass
        time.sleep(0.5)
    raise RuntimeError("headless Edge did not start")


REJECT = r"""(() => {
  const b = [...document.querySelectorAll('button, input[type=submit]')]
    .find(e => /^(reject all|rechazar todo|tout refuser|alle ablehnen)$/i.test((e.innerText || e.value || '').trim()));
  if (b) { b.click(); return true; } return false; })()"""


def _go(url: str, wait: float):
    # a cross-site navigation swaps the renderer: re-attach afterwards
    try:
        _page().send("Page.navigate", url=url)
    except Exception:
        pass
    time.sleep(wait)
    return _page()


def capture(page, lat: float, lon: float, heading: float | None, out: Path) -> Path:
    url = f"https://www.google.com/maps/@?api=1&map_action=pano&viewpoint={lat},{lon}"
    if heading is not None:
        url += f"&heading={heading}"
    page = _go(url, 8)
    try:
        rejected = page.evaluate(REJECT)
    except Exception:
        rejected = False
    if rejected:
        time.sleep(4)
        page = _go(url, 10)
    time.sleep(4)
    page = _page()
    page.send("Emulation.setDeviceMetricsOverride", width=1280, height=860, deviceScaleFactor=1, mobile=False)
    time.sleep(1)
    import base64
    data = page.send("Page.captureScreenshot", format="jpeg", quality=88)["data"]
    out.write_bytes(base64.b64decode(data))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("points", nargs="+", help="name=lat,lon[,heading]")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    prof = os.path.join(os.environ.get("TEMP", "."), "uad36edge_sv")
    proc = subprocess.Popen([EDGE, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--lang=en-US",
                             f"--user-data-dir={prof}", f"--remote-debugging-port={PORT}",
                             "--window-size=1280,860", "about:blank"])
    try:
        page = _page()
        page.send("Emulation.setDeviceMetricsOverride", width=1280, height=860, deviceScaleFactor=1, mobile=False)
        for spec in a.points:
            name, _, coords = spec.partition("=")
            parts = [float(x) for x in coords.split(",")]
            f = capture(page, parts[0], parts[1], parts[2] if len(parts) > 2 else None, out / f"{name}.jpg")
            print(name, f)
    finally:
        proc.terminate()


if __name__ == "__main__":
    main()
