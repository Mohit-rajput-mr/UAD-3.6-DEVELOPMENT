"""The UAD 3.6 report platform, served on localhost.

Run it with::

    python -m uvicorn app.main:app --port 8765     (from the engine directory)

or simply ``python engine/app/main.py``.

The passcode gate stands in front of everything except the unlock form and the
health check, because a case carries the borrower's name, the property address
and the contract price.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "engine") not in sys.path:
    sys.path.insert(0, str(ROOT / "engine"))

from fastapi.responses import JSONResponse
from fastapi import FastAPI, Request                           # noqa: E402
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse  # noqa: E402
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
api.STORE.listeners = [] if ON_VERCEL else [lambda case_id: api.renderer().changed(case_id),
                                           lambda case_id: api.mapper().changed(case_id)]


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
    for case in api.store().list()[:4]:
        api.renderer().request(case.case_id)

if Path(fonts.ASSETS).exists():       # the licensed Myriad Pro files are not redistributed
    app.mount("/assets/fonts",
              StaticFiles(directory=str(fonts.ASSETS)), name="fonts")
if UI.exists():
    app.mount("/ui", StaticFiles(directory=str(UI)), name="ui")


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


@app.get("/", response_class=HTMLResponse)
def home() -> HTMLResponse:
    index = UI / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>UAD 3.6</h1><p>The interface is not built.</p>")
    return HTMLResponse(index.read_text(encoding="utf-8"))


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
