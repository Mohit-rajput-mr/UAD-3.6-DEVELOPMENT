"""Access control: one shared passcode in front of every report.

A deployment is reachable by anyone who has the URL, and a report carries the
borrower's name, the property address and the contract price.  So nothing but
the unlock form and the health check answers until the passcode is given.

How the passcode is held -- and why it is never in plain text:

* ``engine/app/access.json`` holds a PBKDF2-SHA256 *verifier* for the passcode
  (salt, iterations, two digests).  The repository therefore never contains the
  passcode itself.  ``python engine/app/access.py set-passcode`` rewrites it.
* ``URAR_ACCESS_CODE`` in the server's environment overrides the file (the
  verifier is then derived at start-up).  Use it to change the passcode on a
  deployment without a commit.
* ``URAR_OPEN=1`` disables the gate.  Only on a trusted local machine.

The session is *stateless*, because a serverless deployment runs many
instances and a token kept in one instance's memory is unknown to the next
(which is how the earlier gate locked people out at random on Vercel):

* With ``URAR_SESSION_SECRET`` set, the cookie is ``expiry.HMAC(secret, expiry)``
  -- it expires on the server's clock and rotating the secret revokes all.
* Without it, the cookie is a key derived from the passcode (HMAC of the PBKDF2
  key), which only someone who knew the passcode can produce; the server keeps
  only its SHA-256.  Changing the passcode revokes every session.

Unlock attempts are throttled per client address.  The passcode is never
printed, logged or sent to the browser.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path

from fastapi import Request
from fastapi.responses import HTMLResponse, JSONResponse, Response

COOKIE = "urar_access"
# The unlock form itself must stay reachable, or there is no way in.
OPEN_PATHS = ("/healthz", "/access")
CONFIG = Path(__file__).resolve().parent / "access.json"
ITERATIONS = 600_000            # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
SESSION_HOURS = 12
# throttle: this many failures per address inside the window, then a lockout
MAX_FAILURES, WINDOW = 8, 15 * 60


def _derive(code: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, iterations)


def make_config(code: str, iterations: int = ITERATIONS) -> dict:
    """The verifier for ``code``: what access.json stores instead of the code."""
    salt = secrets.token_bytes(16)
    key = _derive(code, salt, iterations)
    token = hmac.new(key, b"session-v1", hashlib.sha256).hexdigest()
    return {"algorithm": "pbkdf2_sha256", "iterations": iterations, "salt": salt.hex(),
            "check": hashlib.sha256(b"check" + key).hexdigest(),
            "session": hashlib.sha256(token.encode()).hexdigest()}


class Access:
    def __init__(self, config: dict | None = None) -> None:
        self.open = os.environ.get("URAR_OPEN") == "1"
        env_code = os.environ.get("URAR_ACCESS_CODE")
        if config is None:
            if env_code:
                config = make_config(env_code, iterations=100_000)
            elif CONFIG.exists():
                config = json.loads(CONFIG.read_text(encoding="utf-8"))
            else:
                # no passcode configured anywhere: stay locked to everyone
                config = make_config(secrets.token_urlsafe(24), iterations=1000)
        self.config = config
        self._salt = bytes.fromhex(config["salt"])
        self._iterations = int(config["iterations"])
        self._secret = os.environ.get("URAR_SESSION_SECRET", "").encode() or None
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()
        # the server's own token, for its in-process tools (the headless map
        # tool calls back with it); random per process, never leaves the host
        self._own = "internal-" + secrets.token_urlsafe(32)

    # ------------------------------------------------------------ tokens
    def _token_for(self, code: str) -> str:
        key = _derive(code, self._salt, self._iterations)
        if self._secret:
            exp = str(int(time.time()) + SESSION_HOURS * 3600)
            sig = hmac.new(self._secret, exp.encode(), hashlib.sha256).hexdigest()
            return f"{exp}.{sig}"
        return hmac.new(key, b"session-v1", hashlib.sha256).hexdigest()

    def valid(self, token: str) -> bool:
        if not token:
            return False
        if hmac.compare_digest(token, self._own):
            return True
        if self._secret and "." in token:
            exp, _, sig = token.partition(".")
            good = hmac.new(self._secret, exp.encode(), hashlib.sha256).hexdigest()
            return (hmac.compare_digest(sig, good) and exp.isdigit()
                    and int(exp) > time.time())
        digest = hashlib.sha256(token.encode()).hexdigest()
        return hmac.compare_digest(digest, self.config["session"])

    def granted(self, request: Request) -> bool:
        if self.open:
            return True
        return self.valid(request.cookies.get(COOKIE, ""))

    @property
    def token(self) -> str:
        """The server's own session token (local runs only), for its tools."""
        return self._own

    # ------------------------------------------------------------ unlock
    def throttled(self, who: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._failures.get(who, []) if now - t < WINDOW]
            self._failures[who] = recent
            return len(recent) >= MAX_FAILURES

    def check(self, submitted: str, who: str = "") -> str | None:
        """The session token when ``submitted`` is the passcode, else None.

        Exact match (surrounding whitespace aside): the passcode is what the
        owner chose, character for character."""
        code = submitted.strip()
        key = _derive(code, self._salt, self._iterations)
        ok = hmac.compare_digest(hashlib.sha256(b"check" + key).hexdigest(),
                                 self.config["check"])
        if not ok:
            with self._lock:
                self._failures.setdefault(who, []).append(time.time())
            return None
        with self._lock:
            self._failures.pop(who, None)
        return self._token_for(code)

    def grant(self, response: Response, token: str, secure: bool = False) -> None:
        response.set_cookie(
            COOKIE, token, httponly=True, samesite="lax", secure=secure,
            max_age=SESSION_HOURS * 3600, path="/",
        )


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
    <input id="code" name="code" type="password" autocomplete="current-password"
           autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required>
    <button type="submit">Unlock</button>
    __ERROR__
  </div>
  <div class="foot">Fannie Mae | Freddie Mac &nbsp;·&nbsp; UAD 3.6 deliverable &nbsp;·&nbsp; powered by <b>Kech</b></div>
</form>
</main></body></html>"""


def gate_page(error: bool = False, throttled: bool = False) -> HTMLResponse:
    message = ('<div class="err">Too many attempts from this address. Wait 15 minutes.</div>'
               if throttled else
               '<div class="err">That passcode did not match. Try again.</div>' if error else "")
    return HTMLResponse(GATE.replace("__ERROR__", message), status_code=401)


def guard(access: Access, request: Request) -> Response | None:
    """The response to send instead of the page, or None to let it through."""
    if access.granted(request) or request.url.path in OPEN_PATHS:
        return None
    if request.url.path.startswith("/api/"):
        return JSONResponse({"error": "locked"}, status_code=401)
    return gate_page()


def client_address(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() if fwd else
            (request.client.host if request.client else "")) or "?"


if __name__ == "__main__":
    # python engine/app/access.py set-passcode      (prompts; nothing echoed)
    if sys.argv[1:2] != ["set-passcode"]:
        raise SystemExit("usage: access.py set-passcode")
    import getpass
    first = getpass.getpass("New passcode: ")
    if first != getpass.getpass("Again: ") or not first.strip():
        raise SystemExit("passcodes did not match")
    CONFIG.write_text(json.dumps(make_config(first.strip()), indent=2) + "\n", encoding="utf-8")
    print(f"wrote {CONFIG}")


def sign_in(client) -> None:
    """Let an in-process client (tests, the dossier tool) through the gate with
    the server's own token -- no passcode in the code that calls it."""
    from app.main import ACCESS
    client.cookies.set(COOKIE, ACCESS.token)
