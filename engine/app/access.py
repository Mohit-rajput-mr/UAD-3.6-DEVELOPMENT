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
# the gate page's own typeface (SIL OFL, engine/app/ui/fonts/OFL-Geist.txt) --
# public files, nothing behind the passcode
OPEN_PATHS = ("/healthz", "/access", "/ui/fonts/Geist-Variable.woff2",
              "/ui/fonts/GeistMono-Variable.woff2")
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
/* Monochrome, editorial: near-black, white type, a chrome ribbon and a glass
   card with a silver edge.  Everything is local -- the typeface is served from
   this host (SIL OFL) -- so the gate needs nothing from the network. */
@font-face{font-family:"Geist";src:url(/ui/fonts/Geist-Variable.woff2) format("woff2");font-weight:100 900;font-display:swap}
@font-face{font-family:"Geist Mono";src:url(/ui/fonts/GeistMono-Variable.woff2) format("woff2");font-weight:100 900;font-display:swap}
:root{--bg:#0a0a0b;--ink:#f4f4f5;--ink-2:#c9c9ce;--muted:#8b8b93;--line:rgba(255,255,255,.09);
 --sans:"Geist","Inter","Segoe UI",-apple-system,Roboto,Arial,sans-serif;
 --mono:"Geist Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
*{box-sizing:border-box}
html,body{height:100%}
body{margin:0;min-height:100vh;background:var(--bg);color:var(--ink);font:400 14px/1.55 var(--sans);
 -webkit-font-smoothing:antialiased;display:grid;grid-template-rows:auto 1fr auto;overflow-x:hidden;position:relative}
body:before{content:'';position:fixed;inset:0;pointer-events:none;
 background-image:linear-gradient(rgba(255,255,255,.035) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.035) 1px,transparent 1px);
 background-size:72px 72px;-webkit-mask-image:radial-gradient(ellipse at 60% 40%,#000 20%,transparent 75%);
 mask-image:radial-gradient(ellipse at 60% 40%,#000 20%,transparent 75%)}
.ribbon{position:fixed;right:-120px;top:-160px;width:720px;height:720px;pointer-events:none;opacity:.9}
.top,.foot{position:relative;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:22px 40px}
.top{border-bottom:1px solid var(--line)}
.foot{border-top:1px solid var(--line);color:var(--muted);font-size:12px;flex-wrap:wrap}
.brand{display:flex;align-items:center;gap:12px}
.logo{width:34px;height:34px;display:grid;place-items:center;background:var(--ink);color:var(--bg);
 font:800 17px/1 var(--sans);letter-spacing:-.04em}
.bt b{display:block;font:500 18px/1 var(--sans);letter-spacing:-.02em}
.bt span{display:block;margin-top:4px;font:500 9.5px/1 var(--sans);letter-spacing:.2em;color:var(--muted)}
.top .r{font-size:12px;color:var(--muted);display:flex;align-items:center;gap:8px}
.top .r:before{content:'';width:6px;height:6px;border-radius:50%;background:#4fd1a5;box-shadow:0 0 0 4px rgba(79,209,165,.15)}
main{position:relative;display:grid;grid-template-columns:minmax(0,1.15fr) minmax(0,.85fr);gap:56px;align-items:center;
 width:min(100%,1180px);margin:0 auto;padding:56px 40px}
@media (max-width:900px){main{grid-template-columns:1fr;gap:32px;padding:36px 22px}.top,.foot{padding:18px 22px}}
.lbl{display:flex;align-items:center;gap:10px;font:500 11px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--ink-2)}
.lbl:before{content:'+';font:300 18px/1 var(--sans);letter-spacing:0}
h1{margin:26px 0 22px;font:500 clamp(40px,5vw,66px)/.98 var(--sans);letter-spacing:-.045em}
h1 span{display:block;color:#7c7c84}
.lede{margin:0;max-width:44ch;color:var(--muted);font-size:15px}
.card{position:relative;padding:32px;border-radius:20px;border:1px solid transparent;
 background:linear-gradient(180deg,rgba(23,23,26,.92),rgba(14,14,16,.92)) padding-box,
   linear-gradient(135deg,rgba(255,255,255,.5),rgba(255,255,255,.06) 38%,rgba(255,255,255,.22) 72%,rgba(255,255,255,.05)) border-box;
 -webkit-backdrop-filter:blur(18px);backdrop-filter:blur(18px);box-shadow:0 40px 90px rgba(0,0,0,.55)}
.card h2{margin:0 0 6px;font:500 20px/1.2 var(--sans);letter-spacing:-.02em}
.card p{margin:0 0 24px;color:var(--muted);font-size:13px}
label{display:block;font:500 10.5px/1 var(--sans);letter-spacing:.18em;text-transform:uppercase;color:var(--muted);margin-bottom:10px}
input{width:100%;padding:14px 16px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.04);
 color:var(--ink);font:500 16px/1.2 var(--mono);letter-spacing:.14em;transition:border-color .15s,background .15s}
input:focus{outline:none;border-color:rgba(255,255,255,.5);background:rgba(255,255,255,.07)}
button{display:flex;align-items:center;justify-content:space-between;width:100%;margin-top:16px;padding:15px 18px;border:0;border-radius:12px;
 cursor:pointer;background:var(--ink);color:var(--bg);font:600 14px/1 var(--sans);letter-spacing:-.01em;transition:opacity .15s,transform .15s}
button:hover{opacity:.9}
button:active{transform:translateY(1px)}
.err{margin-top:16px;padding:11px 14px;border-radius:12px;background:rgba(240,113,120,.1);border:1px solid rgba(240,113,120,.35);
 color:#ffb4b8;font-size:13px}
.note{margin-top:22px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}
</style></head><body>
<svg class="ribbon" viewBox="0 0 720 720" aria-hidden="true"><defs>
 <linearGradient id="chrome" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#ffffff" stop-opacity=".95"/><stop offset=".22" stop-color="#6d6d72"/>
  <stop offset=".45" stop-color="#f2f2f2"/><stop offset=".7" stop-color="#3b3b40"/><stop offset="1" stop-color="#d9d9dc"/></linearGradient></defs>
 <path d="M140 40 C 300 160, 420 360, 360 700" fill="none" stroke="url(#chrome)" stroke-width="26" stroke-linecap="round" opacity=".85"/>
 <path d="M520 10 C 600 140, 700 220, 760 240" fill="none" stroke="url(#chrome)" stroke-width="14" stroke-linecap="round" opacity=".6"/>
</svg>
<div class="top"><div class="brand"><span class="logo">U</span><span class="bt"><b>UAD 3.6</b><span>FORM FILLER</span></span></div>
  <span class="r">Passcode protected</span></div>
<main>
  <div><span class="lbl">For U.S. appraisers &middot; URAR</span>
    <h1>Appraisal workspace.<span>One document, checked as you go.</span></h1>
    <p class="lede">The form you fill, the PDF and the MISMO XML are the same file,
      checked against the GSE subschema at every step.</p></div>
  <form class="card" method="post" action="/access">
    <h2>Sign in</h2>
    <p>This workspace holds borrowers' names, property addresses and contract prices.</p>
    <label for="code">Passcode</label>
    <input id="code" name="code" type="password" autocomplete="current-password"
           autocapitalize="off" autocorrect="off" spellcheck="false" autofocus required>
    <button type="submit"><span>Unlock</span><svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7M8 7h9v9"/></svg></button>
    __ERROR__
    <div class="note">Sessions last twelve hours on this device.</div>
  </form>
</main>
<div class="foot"><span>Fannie Mae | Freddie Mac &middot; Uniform Residential Appraisal Report</span><span>UAD 3.6 &middot; MISMO 3.6 deliverable</span></div>
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
