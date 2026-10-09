"""Drive the Edge or Chrome already on the machine, without Playwright.

The renderer measures the report, checks its pages and prints the PDF in a
real Chromium.  Playwright brings its own Chromium and a Node.js driver -- more
than 150 MB -- which the desktop edition cannot ship.  Every Windows 10 / 11 PC
already has Microsoft Edge, which is Chromium; this module speaks to it over
the Chrome DevTools Protocol (the protocol Playwright itself uses) and offers
the small part of Playwright's sync API the renderer calls:

    with sync_playwright() as p:
        browser = p.chromium.launch(args=[...])
        context = browser.new_context(viewport=..., device_scale_factor=...)
        context.add_cookies([...])
        page = context.new_page()            # or browser.new_page(...)
        page.set_content(html, wait_until="load", timeout=...)
        page.goto(url, wait_until=..., timeout=...)
        page.evaluate("() => ...")  /  page.wait_for_function(...)
        page.wait_for_timeout(ms)
        page.pdf(path=..., width="8.5in", height="14in", ...)
        browser.close()

``uad/report/browser.py`` chooses: Playwright where it is installed (the
development machine, the tests), this driver where only a system browser is
(the desktop edition), and nothing on a serverless host.

The browser is found by ``URAR_BROWSER`` (a path), else the usual install
places of Edge, Chrome and Chromium for the platform.  It runs headless, with
its own throwaway profile, on a debugging port bound to 127.0.0.1 and removed
when the browser closes.
"""
from __future__ import annotations

import base64
import contextlib
import itertools
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


class CDPError(RuntimeError):
    """The browser refused a command or did not answer in time."""


# ----------------------------------------------------------------- finding it
def find_browser() -> str | None:
    """The Edge / Chrome / Chromium executable to drive, or None."""
    env = os.environ.get("URAR_BROWSER", "").strip().strip('"')
    if env:
        return env if Path(env).is_file() else None
    candidates: list[Path] = []
    if sys.platform == "win32":
        for var in ("PROGRAMFILES(X86)", "PROGRAMFILES", "LOCALAPPDATA"):
            base = os.environ.get(var)
            if base:
                candidates += [Path(base) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                               Path(base) / "Google" / "Chrome" / "Application" / "chrome.exe"]
    elif sys.platform == "darwin":
        candidates += [Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
                       Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
                       Path("/Applications/Chromium.app/Contents/MacOS/Chromium")]
    else:
        for name in ("microsoft-edge", "microsoft-edge-stable", "google-chrome",
                     "google-chrome-stable", "chromium", "chromium-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(Path(found))
        root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or "/opt/pw-browsers")
        candidates += sorted(root.glob("chromium-*/chrome-linux*/chrome"), reverse=True)
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def available() -> bool:
    if find_browser() is None:
        return False
    try:
        import websocket  # noqa: F401  (websocket-client)
    except ImportError:
        return False
    return True


# ------------------------------------------------------------------ the wire
class _Connection:
    """One websocket to the browser; commands answered in order, events kept."""

    def __init__(self, url: str):
        import websocket
        # no Origin header: the browser only accepts its own pages' origins
        self.ws = websocket.create_connection(url, timeout=30, suppress_origin=True,
                                              enable_multithread=False)
        self.ids = itertools.count(1)
        self.events: list[dict] = []

    def _recv(self, deadline: float) -> dict:
        import websocket
        left = deadline - time.time()
        if left <= 0:
            raise CDPError("the browser did not answer in time")
        self.ws.settimeout(max(0.05, left))
        try:
            data = self.ws.recv()
        except websocket.WebSocketTimeoutException:
            raise CDPError("the browser did not answer in time") from None
        except (websocket.WebSocketConnectionClosedException, OSError) as exc:
            raise CDPError(f"the browser closed the connection: {exc}") from None
        return json.loads(data)

    def call(self, method: str, params: dict | None = None, session: str | None = None,
             timeout: float = 60.0) -> dict:
        msg_id = next(self.ids)
        msg: dict = {"id": msg_id, "method": method, "params": params or {}}
        if session:
            msg["sessionId"] = session
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while True:
            m = self._recv(deadline)
            if m.get("id") == msg_id:
                if "error" in m:
                    raise CDPError(f"{method}: {m['error'].get('message', m['error'])}")
                return m.get("result") or {}
            if "method" in m:
                self.events.append(m)

    def wait_event(self, method: str, session: str | None, timeout: float) -> dict:
        deadline = time.time() + timeout
        while True:
            for i, e in enumerate(self.events):
                if e.get("method") == method and e.get("sessionId") == session:
                    return self.events.pop(i)
            m = self._recv(deadline)
            if "method" in m:
                self.events.append(m)

    def drop_events(self, session: str | None) -> None:
        self.events = [e for e in self.events if e.get("sessionId") != session]

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.ws.close()


# ------------------------------------------------------------------- helpers
_UNITS = {"px": 1 / 96, "in": 1.0, "cm": 1 / 2.54, "mm": 1 / 25.4}


def _inches(value, default: float) -> float:
    """Playwright's page sizes and margins ("8.5in", "0.62in", 816, "21cm")."""
    if value is None or value == "":
        return default
    if isinstance(value, (int, float)):
        return float(value) / 96
    text = str(value).strip().lower()
    for unit, factor in _UNITS.items():
        if text.endswith(unit):
            return float(text[: -len(unit)]) * factor
    return float(text) / 96


_PAPER = {"letter": (8.5, 11), "legal": (8.5, 14), "tabloid": (11, 17), "a4": (8.27, 11.7),
          "a3": (11.7, 16.54)}

# Playwright accepts either an expression or a function's source and calls the
# function; the wrapper does the same, and awaits whatever comes back.
_EVAL = "(async () => {{ const __v = ({src}); return (typeof __v === 'function') ? await __v() : await __v; }})()"


# --------------------------------------------------------------------- pages
class Page:
    def __init__(self, browser: "Browser", context_id: str, viewport: dict | None,
                 device_scale_factor: float | None):
        self._b = browser
        conn = browser._conn
        target = conn.call("Target.createTarget", {"url": "about:blank",
                                                   "browserContextId": context_id})["targetId"]
        self._target = target
        self._s = conn.call("Target.attachToTarget", {"targetId": target, "flatten": True})["sessionId"]
        conn.call("Page.enable", session=self._s)
        vp = viewport or {"width": 1280, "height": 720}
        conn.call("Emulation.setDeviceMetricsOverride",
                  {"width": int(vp["width"]), "height": int(vp["height"]),
                   "deviceScaleFactor": float(device_scale_factor or 1), "mobile": False},
                  session=self._s)

    # -------------------------------------------------------------- loading
    def _wait_loaded(self, wait_until: str, timeout: float) -> None:
        event = "Page.domContentEventFired" if wait_until == "domcontentloaded" else "Page.loadEventFired"
        self._b._conn.wait_event(event, self._s, timeout)
        if wait_until == "networkidle":
            time.sleep(0.5)

    def goto(self, url: str, wait_until: str = "load", timeout: float = 30_000):
        conn = self._b._conn
        conn.drop_events(self._s)
        res = conn.call("Page.navigate", {"url": url}, session=self._s, timeout=timeout / 1000)
        if res.get("errorText"):
            raise CDPError(f"could not open {url}: {res['errorText']}")
        self._wait_loaded(wait_until, timeout / 1000)

    def set_content(self, html: str, wait_until: str = "load", timeout: float = 30_000) -> None:
        """Write the document, as Playwright does, and wait for it to load --
        fonts and images included."""
        conn = self._b._conn
        doc = conn.call("Runtime.evaluate", {"expression": "document", "objectGroup": "set"},
                        session=self._s)["result"]
        conn.call("Runtime.callFunctionOn", {
            "objectId": doc["objectId"],
            "functionDeclaration": "function(h){ this.open(); this.write(h); this.close(); }",
            "arguments": [{"value": html}]}, session=self._s, timeout=timeout / 1000)
        conn.call("Runtime.releaseObjectGroup", {"objectGroup": "set"}, session=self._s)
        state = "complete" if wait_until in ("load", "networkidle") else "interactive"
        self.wait_for_function(
            f"() => document.readyState === 'complete' || document.readyState === '{state}'",
            timeout=timeout)
        if wait_until == "networkidle":
            time.sleep(0.5)

    # ------------------------------------------------------------ scripting
    def evaluate(self, expression: str, arg=None):
        conn = self._b._conn
        if arg is not None:
            win = conn.call("Runtime.evaluate", {"expression": "window", "objectGroup": "arg"},
                            session=self._s)["result"]
            try:
                res = conn.call("Runtime.callFunctionOn", {
                    "objectId": win["objectId"],
                    "functionDeclaration": f"async function(a){{ const __f = ({expression}); "
                                           f"return (typeof __f === 'function') ? await __f(a) : await __f; }}",
                    "arguments": [{"value": arg}], "awaitPromise": True, "returnByValue": True},
                    session=self._s, timeout=120)
            finally:
                conn.call("Runtime.releaseObjectGroup", {"objectGroup": "arg"}, session=self._s)
        else:
            res = conn.call("Runtime.evaluate", {
                "expression": _EVAL.format(src=expression), "awaitPromise": True,
                "returnByValue": True}, session=self._s, timeout=120)
        if res.get("exceptionDetails"):
            d = res["exceptionDetails"]
            text = (d.get("exception") or {}).get("description") or d.get("text") or "script error"
            raise CDPError(text)
        return (res.get("result") or {}).get("value")

    def wait_for_function(self, expression: str, timeout: float = 30_000, polling: float = 100):
        deadline = time.time() + timeout / 1000
        while True:
            value = self.evaluate(expression)
            if value:
                return value
            if time.time() > deadline:
                raise CDPError("waited too long for the page")
            time.sleep(polling / 1000)

    def wait_for_timeout(self, ms: float) -> None:
        time.sleep(ms / 1000)

    # -------------------------------------------------------------- printing
    def pdf(self, path=None, *, width=None, height=None, format=None, print_background=False,
            margin=None, prefer_css_page_size=False, display_header_footer=False,
            header_template="", footer_template="", scale=1, landscape=False,
            page_ranges="", **_ignored) -> bytes:
        paper = _PAPER.get((format or "letter").lower(), (8.5, 11))
        m = margin or {}
        params = {
            "landscape": bool(landscape), "printBackground": bool(print_background),
            "scale": float(scale), "preferCSSPageSize": bool(prefer_css_page_size),
            "paperWidth": _inches(width, paper[0]), "paperHeight": _inches(height, paper[1]),
            "marginTop": _inches(m.get("top"), 0), "marginBottom": _inches(m.get("bottom"), 0),
            "marginLeft": _inches(m.get("left"), 0), "marginRight": _inches(m.get("right"), 0),
            "displayHeaderFooter": bool(display_header_footer),
            "headerTemplate": header_template or "<span></span>",
            "footerTemplate": footer_template or "<span></span>",
            "pageRanges": page_ranges, "transferMode": "ReturnAsStream",
            # as Playwright prints: no tagged structure, no outline (Chromium
            # otherwise adds both and the file more than doubles)
            "generateTaggedPDF": False, "generateDocumentOutline": False,
        }
        conn = self._b._conn
        stream = conn.call("Page.printToPDF", params, session=self._s, timeout=180)["stream"]
        chunks: list[bytes] = []
        while True:
            part = conn.call("IO.read", {"handle": stream, "size": 1 << 20}, session=self._s)
            data = part.get("data", "")
            chunks.append(base64.b64decode(data) if part.get("base64Encoded") else data.encode("latin-1"))
            if part.get("eof"):
                break
        conn.call("IO.close", {"handle": stream}, session=self._s)
        out = b"".join(chunks)
        if path:
            Path(path).write_bytes(out)
        return out

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._b._conn.call("Target.closeTarget", {"targetId": self._target})


class Context:
    def __init__(self, browser: "Browser", viewport=None, device_scale_factor=None):
        self._b = browser
        self._id = browser._conn.call("Target.createBrowserContext", {"disposeOnDetach": True})[
            "browserContextId"]
        self._viewport, self._dsf = viewport, device_scale_factor

    def new_page(self) -> Page:
        return Page(self._b, self._id, self._viewport, self._dsf)

    def add_cookies(self, cookies: list[dict]) -> None:
        clean = []
        for c in cookies:
            c = {k: v for k, v in c.items() if v is not None}
            if "url" in c and "domain" in c:
                c.pop("url")
            clean.append(c)
        self._b._conn.call("Storage.setCookies", {"cookies": clean, "browserContextId": self._id})

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self._b._conn.call("Target.disposeBrowserContext", {"browserContextId": self._id})


# ------------------------------------------------------------------ browsers
class Browser:
    def __init__(self, executable: str, args: list[str] | None = None):
        self._profile = tempfile.mkdtemp(prefix="uad-browser-")
        cmd = [executable, "--headless=new", "--remote-debugging-port=0",
               f"--user-data-dir={self._profile}", "--no-first-run", "--no-default-browser-check",
               "--disable-extensions", "--disable-background-networking", "--disable-sync",
               "--disable-component-update", "--disable-default-apps", "--mute-audio",
               "--hide-scrollbars", "--disable-features=Translate,MediaRouter",
               *(args or []), "about:blank"]
        if sys.platform.startswith("linux") and hasattr(os, "geteuid") and os.geteuid() == 0:
            # a container running as root: Chromium will not start sandboxed
            # (Playwright passes the same flag); never on Windows or macOS
            cmd.insert(1, "--no-sandbox")
        flags = 0x08000000 if sys.platform == "win32" else 0      # CREATE_NO_WINDOW
        self._proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                      stderr=subprocess.DEVNULL, creationflags=flags)
        port_file = Path(self._profile) / "DevToolsActivePort"
        deadline = time.time() + 45
        while not port_file.exists() or len(port_file.read_text().splitlines()) < 2:
            if self._proc.poll() is not None:
                self._cleanup()
                raise CDPError(f"the browser exited at start ({executable})")
            if time.time() > deadline:
                self.close()
                raise CDPError("the browser did not start in time")
            time.sleep(0.05)
        port, ws_path = port_file.read_text().splitlines()[:2]
        self._conn = _Connection(f"ws://127.0.0.1:{port.strip()}{ws_path.strip()}")

    def new_context(self, viewport=None, device_scale_factor=None, **_ignored) -> Context:
        return Context(self, viewport, device_scale_factor)

    def new_page(self, viewport=None, device_scale_factor=None, **_ignored) -> Page:
        return Context(self, viewport, device_scale_factor).new_page()

    def close(self) -> None:
        conn = getattr(self, "_conn", None)
        if conn is not None:
            with contextlib.suppress(Exception):
                conn.call("Browser.close", timeout=5)
            conn.close()
        try:
            self._proc.wait(timeout=10)
        except Exception:
            with contextlib.suppress(Exception):
                self._proc.kill()
        self._cleanup()

    def _cleanup(self) -> None:
        for _ in range(20):            # Windows holds the profile a moment after exit
            try:
                shutil.rmtree(self._profile)
                return
            except FileNotFoundError:
                return
            except OSError:
                time.sleep(0.1)


class _Chromium:
    def launch(self, args: list[str] | None = None, headless: bool = True,
               executable_path: str | None = None, **_ignored) -> Browser:
        exe = executable_path or find_browser()
        if not exe:
            raise CDPError("no Edge or Chrome was found on this computer")
        return Browser(exe, args)


class _Driver:
    chromium = _Chromium()


@contextlib.contextmanager
def sync_playwright():
    yield _Driver()
