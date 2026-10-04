"""Access control for a publicly reachable review session.

A tunnel makes the review server reachable by anyone who has the URL, and the
report carries the borrower's name, the property address and the contract
price.  So the server asks for a passcode before it will show anything, and the
appraiser hands that code to colleagues along with the link.

Set ``URAR_ACCESS_CODE`` to choose the code; otherwise one is generated at
startup and printed to the console.  Set ``URAR_OPEN=1`` to run without a gate,
which is reasonable on a trusted network and never on a public tunnel.
"""
from __future__ import annotations

import hmac
import os
import secrets

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

COOKIE = "urar_access"
# The unlock form itself must stay reachable, or there is no way in.
OPEN_PATHS = ("/healthz", "/access")


class Access:
    def __init__(self) -> None:
        self.open = os.environ.get("URAR_OPEN") == "1"
        self.code = os.environ.get("URAR_ACCESS_CODE") or self._generate()
        self._token = secrets.token_urlsafe(32)

    @staticmethod
    def _generate() -> str:
        """Four short words are easier to read aloud than a random string."""
        words = (
            "amber birch cedar delta ember fjord grove harbor indigo jasper "
            "kestrel larch maple nimbus onyx poplar quarry rowan summit tamarind"
        ).split()
        return "-".join(secrets.choice(words) for _ in range(3))

    def granted(self, request: Request) -> bool:
        if self.open:
            return True
        return hmac.compare_digest(request.cookies.get(COOKIE, ""), self._token)

    @property
    def token(self) -> str:
        """The session token, for the server's own PDF renderer."""
        return self._token

    def grant(self, response: Response) -> None:
        response.set_cookie(
            COOKIE, self._token,
            httponly=True, samesite="lax", max_age=60 * 60 * 12,
        )

    def check(self, submitted: str) -> bool:
        return hmac.compare_digest(submitted.strip().lower(), self.code.lower())


GATE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>UAD 3.6 Report Platform</title><style>
/* The same monochrome the platform itself is set in: one neutral grey, black
   for emphasis, Bahnschrift condensed. */
:root{--ink:#101010;--paper:#f2f2f0;--surface:#fff;--sunk:#e8e8e5;
 --rule:#c9c9c5;--rule-2:#9a9a95;--muted:#6a6a66;
 --sans:"Bahnschrift","DIN Next","Segoe UI","Liberation Sans",sans-serif;
 --mono:"Cascadia Mono","Consolas",ui-monospace,monospace;--stretch:88%}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;background:var(--paper);color:var(--ink);
 font:400 13px/1.42 var(--sans);font-stretch:var(--stretch);
 display:grid;grid-template-rows:46px 1fr}
header{display:flex;align-items:center;gap:20px;padding:0 18px;
 background:var(--ink);color:var(--paper)}
header .mark{font:700 15px/1 var(--sans);letter-spacing:.22em}
header .sub{font-size:11px;color:#9d9d99;letter-spacing:.09em;text-transform:uppercase}
main{display:grid;place-items:center;padding:20px}
form{width:min(94vw,392px);background:var(--surface);border:1px solid var(--rule)}
.head{padding:13px 18px;border-bottom:1px solid var(--rule);background:var(--sunk)}
h1{margin:0;font:600 14px/1.3 var(--sans);letter-spacing:.01em}
.body{padding:18px}
p{margin:0 0 16px;color:var(--muted);font-size:12px}
label{display:block;font:600 10px/1 var(--sans);letter-spacing:.18em;
 text-transform:uppercase;color:var(--muted);margin-bottom:7px}
input{width:100%;padding:7px 9px;border:1px solid var(--rule-2);
 background:var(--surface);color:inherit;font:inherit;font-family:var(--mono);
 letter-spacing:.08em}
input:focus{outline:2px solid var(--ink);outline-offset:-1px}
button{width:100%;margin-top:14px;padding:9px;border:1px solid var(--ink);
 background:var(--ink);color:var(--paper);cursor:pointer;
 font:600 10px/1.2 var(--sans);letter-spacing:.14em;text-transform:uppercase;
 font-stretch:var(--stretch)}
button:hover{background:var(--surface);color:var(--ink)}
.err{margin-top:12px;padding:6px 9px;background:var(--ink);color:var(--paper);
 font-size:11.5px}
.foot{padding:9px 18px;border-top:1px solid var(--rule);color:var(--muted);
 font:400 10px/1.4 var(--mono)}
</style></head><body>
<header><span class="mark">UAD 3.6</span>
  <span class="sub">Uniform Residential Appraisal Report</span></header>
<main>
<form method="post" action="/access">
  <div class="head"><h1>Locked</h1></div>
  <div class="body">
    <p>This report carries the borrower's name, the property address and the
       contract price. Enter the passcode to open the platform.</p>
    <label for="code">Passcode</label>
    <input id="code" name="code" autocomplete="one-time-code" autofocus>
    <button type="submit">Unlock</button>
    __ERROR__
  </div>
  <div class="foot">Fannie Mae | Freddie Mac &nbsp;·&nbsp; UAD 3.6 deliverable &nbsp;·&nbsp; powered by <b>Kech</b></div>
</form>
</main></body></html>"""


def gate_page(error: bool = False) -> HTMLResponse:
    message = '<div class="err">That passcode did not match. Try again.</div>' if error else ""
    return HTMLResponse(GATE.replace("__ERROR__", message), status_code=401)


def guard(access: Access, request: Request) -> Response | None:
    """The response to send instead of the page, or None to let it through."""
    if access.granted(request) or request.url.path in OPEN_PATHS:
        return None
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "locked"}, status_code=401)
    return gate_page()
