"""Download product: the desktop edition, handed over for the licence key.

The installer is built by ``desktop/build.py`` and committed under
``downloads/desktop/``: a ``manifest.json`` and the installer cut into parts
of under 4 MB.  Parts, because a serverless function answers at most 4.5 MB
(Vercel), and the installer is several times that; the browser fetches the
parts in order, checks each digest, and saves the joined file.

    POST /api/desktop/ticket   {"key": ...}   -> {"ticket", "name", "version", "size", "sha256", "parts"}
    GET  /api/desktop/part/{n}?t=<ticket>     -> the n-th part (0-based)
    GET  /api/desktop/info                    -> whether this is the desktop edition, what is on offer

The key is checked against the verifier in app/license.json (never stored in
plain text) and wrong keys are throttled per address.  These routes and the
public ``/download`` page are open without the web passcode (app/access.py
OPEN_PREFIXES): a licence holder needs the key, not the office's passcode.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, Body, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response

from app import license as lic

ROOT = Path(__file__).resolve().parents[2]
SHELF = Path(os.environ.get("URAR_DOWNLOADS") or ROOT / "downloads" / "desktop")
router = APIRouter(prefix="/api/desktop")
page_router = APIRouter()
THROTTLE = lic.Throttle()


def manifest() -> dict | None:
    path = SHELF / "manifest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return None


def _who(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else
            (request.client.host if request.client else "")) or "?"


@router.get("/info")
def info() -> dict:
    m = manifest()
    return {"desktop": os.environ.get("URAR_DESKTOP") == "1",
            "available": m is not None,
            **({"name": m["name"], "version": m["version"], "size": m["size"],
                "built": m.get("built", "")} if m else {})}


@router.post("/ticket")
def ticket(request: Request, body: dict = Body(...)) -> dict:
    who = _who(request)
    if THROTTLE.blocked(who):
        raise HTTPException(429, "Too many wrong keys from this address. Wait 15 minutes.")
    t = lic.check(str(body.get("key", "")))
    if t is None:
        THROTTLE.failed(who)
        raise HTTPException(403, "That licence key is not valid.")
    THROTTLE.cleared(who)
    m = manifest()
    if m is None:
        raise HTTPException(404, "The desktop installer has not been built on this server yet.")
    return {"ticket": t, "name": m["name"], "version": m["version"], "size": m["size"],
            "sha256": m["sha256"], "parts": [{"size": p["size"], "sha256": p["sha256"]}
                                             for p in m["parts"]]}


@router.get("/part/{n}")
def part(n: int, t: str = Query("")) -> Response:
    if not lic.ticket_valid(t):
        raise HTTPException(403, "This download needs the licence key.")
    m = manifest()
    if m is None or not 0 <= n < len(m["parts"]):
        raise HTTPException(404, "no such part")
    path = SHELF / m["parts"][n]["file"]
    if not path.is_file():
        raise HTTPException(404, "no such part")
    return Response(path.read_bytes(), media_type="application/octet-stream",
                    headers={"Cache-Control": "private, max-age=3600"})


@page_router.get("/download", response_class=HTMLResponse)
def download_page() -> HTMLResponse:
    """The public page with the Download product dialog (ui/download.js)."""
    return HTMLResponse(PAGE)


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Download UAD 3.6</title><link rel="icon" href="/ui/brand/app-icon-64.png" type="image/png">
<style>
@font-face{font-family:"Geist";src:url(/ui/fonts/Geist-Variable.woff2) format("woff2");font-weight:100 900}
@font-face{font-family:"Geist Mono";src:url(/ui/fonts/GeistMono-Variable.woff2) format("woff2");font-weight:100 900}
:root{color-scheme:dark;--bg:#0a0a0b;--bg-2:#0d0d0f;--surface:#111113;--surface-2:#161619;--sunk:#1b1b1f;
 --ink:#f4f4f5;--ink-2:#cdcdd2;--muted:#8c8c94;--faint:#5e5e66;--line:rgba(255,255,255,.08);
 --line-2:rgba(255,255,255,.14);--line-3:rgba(255,255,255,.26);--btn:#f4f4f5;--btn-ink:#0a0a0b;
 --hover:rgba(255,255,255,.05);--good:#4fd1a5;--bad:#f2787e;--shadow-lg:0 36px 90px rgba(0,0,0,.55);
 --sans:"Geist","Segoe UI",system-ui,sans-serif;--mono:"Geist Mono",ui-monospace,Consolas,monospace}
*{box-sizing:border-box;border-radius:0}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--ink);font:400 14px/1.55 var(--sans);
 display:grid;grid-template-rows:auto 1fr}
.top{display:flex;align-items:center;gap:12px;padding:20px 28px;border-bottom:1px solid var(--line)}
.logo{width:32px;height:32px;display:grid;place-items:center}.logo img{height:30px;width:auto;display:block}
.top b{font:500 17px/1 var(--sans)}.top a{margin-left:auto;color:var(--muted);font-size:13px}
main{display:grid;place-items:center;padding:40px 16px;text-align:center}
.eyebrow{display:inline-flex;align-items:center;gap:9px;font:500 10.5px/1.2 var(--sans);letter-spacing:.17em;
 text-transform:uppercase;color:var(--ink-2)}
.eyebrow:before{content:'+';font:300 17px/1 var(--sans);letter-spacing:0;color:var(--ink)}
h1{margin:18px 0 10px;font:500 44px/1 var(--sans);letter-spacing:-.045em}h1 span{display:block;color:#7c7c84}
p{color:var(--muted);max-width:52ch;margin:0 auto 24px}
.go{appearance:none;border:0;background:var(--btn);color:var(--btn-ink);padding:15px 22px;font:600 14px/1 var(--sans);cursor:pointer}
@keyframes pop2{from{opacity:0;transform:translateY(8px)}}
</style></head><body>
<div class="top"><span class="logo"><img src="/ui/brand/mark-white.png" alt=""></span><b>UAD 3.6</b><a href="/">Sign in to the web app</a></div>
<main><div><span class="eyebrow">Download product</span>
<h1>UAD 3.6 for Windows<span>on your own PC.</span></h1>
<p>The report editor, the compliance review, the PDF and the delivery ZIP run on your computer, and your reports stay there. You need your licence key.</p>
<button class="go" id="open">Download &rarr;</button></div></main>
<script src="/ui/download.js"></script>
<script>
var info={};
fetch('/api/desktop/info').then(function(r){return r.json();}).then(function(d){ info=d; UADDownload.open(info); });
document.getElementById('open').onclick=function(){ UADDownload.open(info); };
</script></body></html>"""
