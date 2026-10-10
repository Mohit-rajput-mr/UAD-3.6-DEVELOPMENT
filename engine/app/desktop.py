"""The desktop edition's own doors: the app window's way in, and activation.

The desktop app (``desktop/launcher.py``) runs this same server on
127.0.0.1 and opens it in an Edge app window.  Two things differ from the web:

* **The way in.**  The launcher starts the server with a random one-time
  token (``URAR_DESKTOP_TOKEN``) and opens ``/desktop/unlock?k=<token>``,
  which sets the session cookie -- so the appraiser never types the web
  passcode on their own machine, and nothing else on the PC (another program,
  a web page) can use the local server without that token.
* **Activation.**  The installer checks the licence key and leaves an
  activation record (``activation.json``: the ticket only the key produces,
  app/license.py) in the app's data folder.  A copy without a valid record --
  copied from another PC, or installed silently without a key -- asks for the
  key once before anything else opens.

Nothing here is registered unless ``URAR_DESKTOP=1``.
"""
from __future__ import annotations

import hmac
import json
import os
import time
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app import license as lic
from app.access import COOKIE, client_address

THROTTLE = lic.Throttle()
LAST_SEEN = [time.time()]          # the last request from a window (the launcher reads it)


def idle_seconds() -> float:
    return time.time() - LAST_SEEN[0]


def data_dir() -> Path:
    base = os.environ.get("URAR_DESKTOP_DATA")
    if base:
        return Path(base)
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "UAD36"


def activation_file() -> Path:
    return data_dir() / "activation.json"


def activated() -> bool:
    try:
        record = json.loads(activation_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return lic.ticket_valid(str(record.get("ticket", "")))


def activate(ticket: str) -> None:
    path = activation_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ticket": ticket, "at": time.strftime("%Y-%m-%dT%H:%M:%S")}),
                    encoding="utf-8")


# what may open before activation: the activation page itself and its typeface
_BEFORE = ("/desktop/", "/ui/fonts/", "/ui/brand/", "/ui/icon.svg", "/healthz")


def install(app: FastAPI, access) -> None:
    token = os.environ.get("URAR_DESKTOP_TOKEN", "")

    @app.middleware("http")
    async def needs_activation(request: Request, call_next):
        path = request.url.path
        if path != "/healthz":
            LAST_SEEN[0] = time.time()
        if activated() or path.startswith(_BEFORE):
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse({"detail": "This copy of UAD 3.6 is not activated."}, status_code=403)
        return RedirectResponse("/desktop/activate", status_code=303)

    @app.get("/desktop/unlock")
    def unlock(k: str = ""):
        if not token or not hmac.compare_digest(k.encode(), token.encode()):
            return HTMLResponse(_page("This link is no longer valid",
                                      "<p>Open UAD 3.6 from the Start menu or the desktop shortcut.</p>"),
                                status_code=403)
        response = RedirectResponse("/" if activated() else "/desktop/activate", status_code=303)
        response.set_cookie(COOKIE, access.token, httponly=True, samesite="strict", path="/")
        return response

    @app.get("/desktop/activate", response_class=HTMLResponse)
    def activate_page():
        if activated():
            return RedirectResponse("/", status_code=303)
        return HTMLResponse(_activation_form(""))

    @app.post("/desktop/activate", response_class=HTMLResponse)
    async def activate_post(request: Request):
        who = client_address(request)
        if THROTTLE.blocked(who):
            return HTMLResponse(_activation_form("Too many wrong keys. Wait 15 minutes."), status_code=429)
        form = await request.form()
        ticket = lic.check(str(form.get("key", "")))
        if ticket is None:
            THROTTLE.failed(who)
            return HTMLResponse(_activation_form("That licence key is not valid."), status_code=401)
        THROTTLE.cleared(who)
        activate(ticket)
        return RedirectResponse("/", status_code=303)


def _activation_form(error: str) -> str:
    err = f"<p class='err'>{error}</p>" if error else ""
    return _page("Activate UAD 3.6", f"""
<p>Enter the licence key you were given. It is asked once on this computer.</p>{err}
<form method="post" action="/desktop/activate" autocomplete="off">
  <label for="key">Licence key</label>
  <input id="key" name="key" type="password" required autofocus spellcheck="false">
  <button type="submit">Activate &rarr;</button>
</form>""")


def _page(title: str, body: str) -> str:
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{title}</title>
<link rel="icon" href="/ui/brand/app-icon-64.png" type="image/png"><style>
@font-face{{font-family:"Geist";src:url(/ui/fonts/Geist-Variable.woff2) format("woff2");font-weight:100 900}}
*{{box-sizing:border-box;border-radius:0}}
body{{margin:0;min-height:100vh;display:grid;place-items:center;background:#0a0a0b;color:#f4f4f5;
  font:400 14px/1.55 "Geist","Segoe UI",system-ui,sans-serif;padding:16px}}
main{{width:min(440px,100%);border:1px solid rgba(255,255,255,.26);background:#111113;padding:28px}}
.k{{font:500 10.5px/1 "Geist",sans-serif;letter-spacing:.17em;text-transform:uppercase;color:#cdcdd2}}
.k:before{{content:'+ ';font-weight:300}}
h1{{margin:12px 0 8px;font:500 26px/1.1 "Geist",sans-serif;letter-spacing:-.035em}}
p{{color:#8c8c94;margin:0 0 14px}}
label{{display:block;font-size:12px;color:#cdcdd2;margin:16px 0 6px}}
input{{width:100%;padding:11px 12px;background:#0d0d0f;color:#f4f4f5;border:1px solid rgba(255,255,255,.26);
  font:500 15px/1 ui-monospace,Consolas,monospace;letter-spacing:.08em}}
input:focus{{outline:2px solid #f4f4f5;outline-offset:-1px}}
button{{margin-top:14px;width:100%;padding:12px;background:#f4f4f5;color:#0a0a0b;border:0;font:600 14px/1 "Geist",sans-serif;cursor:pointer}}
.err{{color:#f2787e;border-left:2px solid #f2787e;padding-left:10px}}
</style></head><body><main><span class="k">UAD 3.6 desktop</span><h1>{title}</h1>{body}</main></body></html>"""
