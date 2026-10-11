"""The UAD 3.6 report platform, served on localhost.

Run it with::

    python -m uvicorn app.main:app --port 8765     (from the engine directory)

or simply ``python engine/app/main.py``.

The passcode gate stands in front of everything except the unlock form and the
health check, because a case carries the borrower's name, the property address
and the contract price.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request                           # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response  # noqa: E402
from fastapi.middleware.gzip import GZipMiddleware            # noqa: E402
from fastapi.staticfiles import StaticFiles                    # noqa: E402

from app import api                                            # noqa: E402
from app.access import Access, client_address, gate_page, guard  # noqa: E402
from app.cases import SchemaRegression, Store                  # noqa: E402
from uad.report import fonts                                   # noqa: E402
from uad.report.browser import BrowserUnavailable              # noqa: E402

# Where the reports live.  Normally one store per installation; URAR_WORK
# gives a second instance its own, which is what keeps two servers running
# from the same checkout -- a preview and a test, say -- from clearing each
# other's reports out from under an open editor.
# On Vercel (which sets VERCEL=1) the code is read-only and only /tmp is
# writable -- and /tmp is per instance and temporary, so a deployment there is
# a demonstration store, not the office's.  See DEPLOY_VERCEL.md.
ON_VERCEL = bool(os.environ.get("VERCEL"))
WORK = (Path(os.environ["URAR_WORK"]) if os.environ.get("URAR_WORK")
        else Path("/tmp/uad36/cases") if ON_VERCEL else ROOT / "_work" / "cases")
WORK.mkdir(parents=True, exist_ok=True)
UI = Path(__file__).resolve().parent / "ui"

# The passcode is held as a PBKDF2 verifier in app/access.json (never in plain
# text); URAR_ACCESS_CODE in the environment overrides it.  See app/access.py.

app = FastAPI(title="UAD 3.6 Report Platform", docs_url="/api/docs",
              openapi_url="/api/openapi.json")
ACCESS = Access()
api.STORE = Store(WORK)
app.include_router(api.router)
from app import download as _download                          # noqa: E402
app.include_router(_download.router)        # Download product (the desktop edition)
app.include_router(_download.page_router)   # ... and its public page, /download
# ------------------------------------------------------------- case vault
# The browser keeps a copy of each case (app/ui/vault.js) so a case survives
# the server copy that held it -- the norm on a serverless host, where several
# short-lived copies each have their own disk.  Two things make that safe:
#   * every change to a case answers with the case's fresh bundle, so the
#     browser's copy is never behind the server that made the change;
#   * the browser sends the revision it holds (X-UAD-Rev, the case's
#     ``updated`` stamp); a server copy holding an older revision answers 409
#     so the browser replaces it before the request is made again.
# Only requests that ask (X-UAD-Vault: 1) are touched.  Registered before the
# gzip middleware so it sees plain JSON.
import base64 as _b64          # noqa: E402
import re as _re               # noqa: E402

_VAULT_CASE = _re.compile(r"^/api/cases/([0-9a-f]{12})(/|$)")


@app.middleware("http")
async def vault(request: Request, call_next):
    if request.headers.get("x-uad-vault") != "1":
        return await call_next(request)
    path = request.url.path
    m = _VAULT_CASE.match(path)
    cid = m.group(1) if m else None
    rev = request.headers.get("x-uad-rev", "")
    if cid and rev and not DURABLE.on:
        try:
            if api.store().get(cid).updated < rev:
                return JSONResponse({"stale": True, "case_id": cid,
                                     "detail": "this server copy holds an older revision"},
                                    status_code=409)
        except KeyError:
            pass
    response = await call_next(request)
    if (request.method == "GET" or not 200 <= response.status_code < 300
            or "application/json" not in response.headers.get("content-type", "")):
        return response
    body = b"".join([chunk async for chunk in response.body_iterator])
    headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
    try:
        data = json.loads(body)
    except ValueError:
        return Response(body, status_code=response.status_code, headers=headers)
    if not isinstance(data, dict):
        return Response(body, status_code=response.status_code, headers=headers)
    if path == "/api/cases" and request.method == "POST":
        cid = data.get("case_id")
    elif path == "/api/import":
        cid = (data.get("case") or {}).get("case_id")
    if not cid or path == "/api/cases/restore" or (
            request.method == "DELETE" and path == f"/api/cases/{cid}"):
        return Response(body, status_code=response.status_code, headers=headers)
    try:
        case = api.store().get(cid)
        bundle = api.store().bundle(cid, images=False, history=300)
        data["_vault"] = {"case_id": cid, "updated": case.updated, "name": case.name,
                          "bundle": _b64.b64encode(bundle).decode("ascii")}
    except KeyError:
        pass
    return JSONResponse(data, status_code=response.status_code, headers=headers)


# ------------------------------------------------------- shared case store
# On a host that runs many server copies (Vercel), every copy reads and writes
# the same shared store (app/durable.py): a request about a case first makes
# this copy's case current, and a request that changed it writes it back.
# Without BLOB_READ_WRITE_TOKEN this is off and the local disk is the store.
from app import durable as _durable                     # noqa: E402
from starlette.concurrency import run_in_threadpool     # noqa: E402

DURABLE = _durable.from_env()
api.DURABLE = DURABLE
_CREATES = ("/api/cases", "/api/import", "/api/cases/restore", "/api/warm")


@app.middleware("http")
async def shared_store(request: Request, call_next):
    if not DURABLE.on or not request.url.path.startswith("/api/"):
        return await call_next(request)
    path, method = request.url.path, request.method
    m = _VAULT_CASE.match(path)
    cid = m.group(1) if m else None
    try:
        if cid:
            await run_in_threadpool(DURABLE.pull, api.store(), cid)
        elif path == "/api/cases" and method == "GET":
            await run_in_threadpool(DURABLE.pull_all, api.store())
    except Exception as exc:                 # the store is down: say so, never guess
        print(f"durable store read failed for {path}: {exc!r}", file=sys.stderr, flush=True)
        return JSONResponse({"detail": f"the shared case store could not be read: {exc}"},
                            status_code=503)
    response = await call_next(request)
    if method == "GET" or not 200 <= response.status_code < 300:
        return response
    try:
        if cid and method == "DELETE" and path == f"/api/cases/{cid}":
            await run_in_threadpool(DURABLE.forget, cid)
        elif cid:
            await run_in_threadpool(DURABLE.push, api.store(), cid)
        elif path in _CREATES and method == "POST":
            body = b"".join([chunk async for chunk in response.body_iterator])
            headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
            try:
                data = json.loads(body)
                new = data.get("case_id") or (data.get("case") or {}).get("case_id")
                if new:
                    await run_in_threadpool(DURABLE.push, api.store(), new)
            except ValueError:
                pass
            return Response(body, status_code=response.status_code, headers=headers)
    except Exception as exc:
        print(f"durable store write failed for {path}: {exc!r}", file=sys.stderr, flush=True)
        return JSONResponse({"detail": "the change was made on this server copy but could not "
                             f"be saved to the shared case store: {exc}"}, status_code=503)
    return response


# A rendered page is mostly text; compressed, it arrives several times faster.
app.add_middleware(GZipMiddleware, minimum_size=2048)


@app.exception_handler(BrowserUnavailable)
async def _no_browser(request, exc):
    # layout / PDF on a host without Chromium: say so, do not fail as a 500
    return JSONResponse({"detail": str(exc)}, status_code=503)


@app.exception_handler(SchemaRegression)
async def _schema_regression(request, exc):
    # a refused write is the appraiser's to correct, not a server failure
    return JSONResponse({"detail": str(exc)}, status_code=422)
# Every change to a case queues a fresh layout in the background, so the page
# is ready before the appraiser switches to it.
# Where the appraiser's own browser lays the report out (a serverless host, the
# desktop edition) the server never needs its own layout, so none is queued --
# on one PC each would cost a headless browser run after every change.
from uad.report import browser as _browser                       # noqa: E402
api.STORE.listeners = [] if ON_VERCEL else (
    ([lambda case_id: api.renderer().changed(case_id)] if _browser.server_layout() else [])
    + [lambda case_id: api.mapper().changed(case_id)])


@app.on_event("startup")
def prewarm() -> None:
    """Lay out the most recently worked cases while nobody is waiting, and
    retire maps the guidelines do not define."""
    if ON_VERCEL:
        return          # no background rendering in a serverless function
    for case in api.store().list():
        try:
            api.mapper().retire(case.case_id)
        except Exception:
            pass
    if not _browser.server_layout():
        return
    for case in api.store().list()[:4]:
        api.renderer().request(case.case_id)

if Path(fonts.ASSETS).exists():       # the licensed Myriad Pro files are not redistributed
    app.mount("/assets/fonts",
              StaticFiles(directory=str(fonts.ASSETS)), name="fonts")
if UI.exists():
    app.mount("/ui", StaticFiles(directory=str(UI)), name="ui")


# the desktop edition: the app window's way in and activation (app/desktop.py);
# registered before the gate, so the gate is checked first
if os.environ.get("URAR_DESKTOP") == "1":
    from app import desktop as _desktop                         # noqa: E402
    _desktop.install(app, ACCESS)


@app.middleware("http")
async def gate(request: Request, call_next):
    blocked = guard(ACCESS, request)
    if blocked is not None:
        return blocked
    return await call_next(request)


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "cases": len(api.store().list())}


@app.post("/access")
async def unlock(request: Request):
    who = client_address(request)
    if ACCESS.throttled(who):
        return gate_page(throttled=True)
    form = await request.form()
    token = ACCESS.check(str(form.get("code", "")), who)
    if token is None:
        return gate_page(error=True)
    # 303 so a reload of the landing page never re-posts the passcode
    response = HTMLResponse('<meta http-equiv="refresh" content="0; url=/">Unlocked.',
                            status_code=303, headers={"Location": "/"})
    secure = (request.url.scheme == "https"
              or request.headers.get("x-forwarded-proto", "") == "https")
    ACCESS.grant(response, token, secure=secure)
    return response


def shell_digest(folder: Path | None = None) -> str:
    """The editor shell's files (ui/shell/*) as one content digest.

    index.html loads them as ``/ui/shell/x.js?v={{SHELLV}}``; /ui is plain
    static files with no cache-busting, so without this a new page could run
    an old shell file.  Content only, never file times: every server copy
    (each Vercel instance) must agree on it.
    """
    import hashlib
    folder = UI / "shell" if folder is None else folder
    h = hashlib.sha1()
    if folder.is_dir():
        for f in sorted(p for p in folder.rglob("*") if p.is_file()):
            h.update(f.relative_to(folder).as_posix().encode("utf-8") + b"\0")
            h.update(f.read_bytes() + b"\0")
    return h.hexdigest()[:12]


SHELLV = shell_digest()          # once, at import


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    index = UI / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>UAD 3.6</h1><p>The interface is not built.</p>")
    return HTMLResponse(index.read_text(encoding="utf-8").replace("{{SHELLV}}", SHELLV))


def lan_address() -> str:
    """This machine's address on the local network, for a second device.

    Found by asking the OS which interface it would use to reach the outside
    world; no packet is actually sent.  Falls back to the loopback address,
    which is the honest answer when there is no network.
    """
    import socket
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        probe.close()


def main() -> None:
    import uvicorn
    port = int(os.environ.get("URAR_PORT", "8765"))
    # Loopback unless asked otherwise.  URAR_HOST=0.0.0.0 puts the platform on
    # the local network so a phone or a second machine can reach it -- which
    # also puts every report on it, so the passcode gate matters there in a way
    # it does not on a machine only this user can touch.
    host = os.environ.get("URAR_HOST", "127.0.0.1")
    # the headless map tool reaches this server on its own address and session
    from app.access import COOKIE
    api.SERVER = {"base": f"http://127.0.0.1:{port}", "cookie": COOKIE, "token": ACCESS.token}
    # the passcode is never printed: it is the owner's, and consoles get logged
    print(f"UAD 3.6 platform on http://127.0.0.1:{port}")
    if host not in ("127.0.0.1", "localhost"):
        print(f"  on this network:   http://{lan_address()}:{port}")
        if ACCESS.open:
            print("  WARNING: URAR_OPEN=1 -- no passcode, and the reports are "
                  "reachable by anything on this network.")
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
