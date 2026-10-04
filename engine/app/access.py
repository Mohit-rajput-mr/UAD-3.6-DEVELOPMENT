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
<meta name="color-scheme" content="dark">
<title>UAD 3.6 Form Filler</title><style>
/* Frosted glass over deep navy and soft violet light -- the platform's own
   accent -- drawn in CSS alone, so the gate needs nothing from the network. */
:root{--bg:#090b1a;--ink:#f4f5ff;--muted:#a3a7c7;--line:rgba(255,255,255,.14);
 --glass:rgba(255,255,255,.065);--accent:#6d5dfc;--accent-2:#9d8fff;
 --sans:"Inter","Segoe UI Variable","Segoe UI",-apple-system,BlinkMacSystemFont,Roboto,"Helvetica Neue",Arial,sans-serif;
 --mono:"JetBrains Mono","Cascadia Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--ink);
 font:400 14px/1.5 var(--sans);-webkit-font-smoothing:antialiased;
 display:grid;place-items:center;padding:24px;overflow:hidden;position:relative}
.orb{position:fixed;border-radius:50%;filter:blur(60px);opacity:.75;pointer-events:none}
.o1{width:520px;height:520px;left:-120px;top:-140px;
 background:radial-gradient(circle at 35% 35%,#7b6cff,#3b2fb5 55%,transparent 70%)}
.o2{width:460px;height:460px;right:-120px;bottom:-160px;
 background:radial-gradient(circle at 60% 40%,#4f8bff,#2a3fb8 55%,transparent 72%)}
.o3{width:260px;height:260px;right:18%;top:12%;opacity:.45;
 background:radial-gradient(circle,#b9a8ff,transparent 70%)}
@media (prefers-reduced-motion:no-preference){
 .o1{animation:drift 18s ease-in-out infinite alternate}
 .o2{animation:drift 22s ease-in-out infinite alternate-reverse}}
@keyframes drift{to{transform:translate(40px,30px) scale(1.06)}}
.card{position:relative;width:min(100%,460px);padding:30px 32px 26px;border-radius:26px;
 background:var(--glass);border:1px solid var(--line);
 -webkit-backdrop-filter:blur(26px) saturate(140%);backdrop-filter:blur(26px) saturate(140%);
 box-shadow:0 30px 80px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.12)}
.top,.foot{display:flex;justify-content:space-between;gap:12px;font-size:12px;color:var(--muted)}
.brand{display:flex;align-items:center;gap:9px;color:var(--ink);font-weight:600;letter-spacing:.01em}
.logo{width:26px;height:26px;border-radius:8px;display:grid;place-items:center;
 background:linear-gradient(135deg,var(--accent-2),var(--accent));box-shadow:0 6px 18px rgba(109,93,252,.5)}
h1{margin:34px 0 8px;font:650 34px/1.08 var(--sans);letter-spacing:-.02em}
.pill{display:inline-block;margin:0 0 22px;padding:5px 12px;border:1px solid var(--line);
 border-radius:999px;font-size:12px;color:#d9dbf4}
p{margin:0 0 20px;color:var(--muted);font-size:13px}
label{display:block;font:600 11px/1 var(--sans);letter-spacing:.12em;text-transform:uppercase;
 color:var(--muted);margin-bottom:8px}
input{width:100%;padding:12px 14px;border-radius:12px;border:1px solid var(--line);
 background:rgba(255,255,255,.07);color:var(--ink);font:500 15px/1.2 var(--mono);letter-spacing:.12em;
 transition:border-color .15s,box-shadow .15s}
input:focus{outline:none;border-color:var(--accent-2);box-shadow:0 0 0 4px rgba(109,93,252,.28)}
button{width:100%;margin-top:14px;padding:12px;border:0;border-radius:12px;cursor:pointer;
 background:linear-gradient(180deg,var(--accent-2),var(--accent));color:#fff;
 font:600 14px/1.2 var(--sans);box-shadow:0 10px 26px rgba(109,93,252,.45);transition:filter .15s,transform .15s}
button:hover{filter:brightness(1.08)}
button:active{transform:translateY(1px)}
.err{margin-top:14px;padding:10px 12px;border-radius:12px;background:rgba(229,72,77,.16);
 border:1px solid rgba(229,72,77,.45);color:#ffc7c9;font-size:13px}
.foot{margin-top:26px;padding-top:16px;border-top:1px solid var(--line);font-size:11.5px}
</style></head><body>
<div class="orb o1"></div><div class="orb o2"></div><div class="orb o3"></div>
<form class="card" method="post" action="/access">
  <div class="top"><span class="brand"><span class="logo"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"><path d="M4 11.5 12 5l8 6.5"/><path d="M6.5 10v9h11v-9"/></svg></span>UAD 3.6 Form Filler</span>
    <span>Passcode protected</span></div>
  <h1>Appraisal<br>workspace</h1>
  <span class="pill">Uniform Residential Appraisal Report</span>
  <p>This workspace holds borrowers' names, property addresses and contract
     prices. Enter the passcode to open it.</p>
  <label for="code">Passcode</label>
  <input id="code" name="code" type="password" autocomplete="current-password"
         autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required>
  <button type="submit">Unlock</button>
  __ERROR__
  <div class="foot"><span>Fannie Mae | Freddie Mac</span><span>UAD 3.6 deliverable</span></div>
</form>
</body></html>"""


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
