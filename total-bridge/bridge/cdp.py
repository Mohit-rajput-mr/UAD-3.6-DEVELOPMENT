"""A small Chrome DevTools Protocol client for TOTAL's embedded browser.

TOTAL hosts its UAD 3.6 form in CefSharp and the host exposes CDP on
127.0.0.1:8088.  Only the *page* endpoint is used: the browser-level endpoint
answers "Browser context management is not supported" to the handshake a
general-purpose driver performs, and page-level Runtime is all that reading and
filling a form needs.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

import websocket           # websocket-client

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8088


class NotRunning(RuntimeError):
    """TOTAL is not reachable on the debugging port."""


class PageGone(RuntimeError):
    """The report page this connection served no longer exists (CATALOG E-040)."""


def endpoint(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> str:
    return f"http://{host}:{port}"


def targets(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> list[dict]:
    try:
        with urllib.request.urlopen(f"{endpoint(host, port)}/json/list", timeout=8) as fh:
            return json.load(fh)
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise NotRunning(
            f"cannot reach TOTAL on {host}:{port} -- is TOTAL running with a "
            f"UAD 3.6 report open? ({exc})") from exc


def pages(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> list[dict]:
    return [t for t in targets(host, port) if t.get("type") == "page"]


class Page:
    """One CDP page connection.

    ``timeout`` is generous on purpose: a MISMO import or a full re-render can
    hold the page for a long time, and a client that gives up first reports a
    failure that did not happen.
    """

    #: how often a waiting call looks whether the page still exists
    POLL = 15.0

    def __init__(self, ws_url: str, timeout: float = 180.0):
        self.url = ws_url
        self.timeout = timeout
        self.ws = websocket.create_connection(ws_url, timeout=min(timeout, self.POLL),
                                              suppress_origin=True,
                                              max_size=64 * 1024 * 1024)
        self._id = 0

    def heap_mb(self, collect: bool = False) -> dict:
        """The page's JavaScript heap in MB, after a garbage collection when
        `collect`.  TOTAL's browser is 32-bit (WOW64 Chrome 109) and its
        renderer has died out of memory mid-batch (CATALOG E-040): measured
        between files so the limit is learned rather than hit."""
        if collect:
            self.send("HeapProfiler.collectGarbage")
        used = self.send("Runtime.getHeapUsage")
        return {"used": round(used.get("usedSize", 0) / 2**20, 1),
                "total": round(used.get("totalSize", 0) / 2**20, 1)}

    def alive(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> bool:
        """Is this page still one TOTAL's browser serves?  When the renderer
        dies (knowledge/errors/CATALOG.md E-040) the report's page vanishes from
        the target list and a call on it may never answer."""
        try:
            return any(t.get("webSocketDebuggerUrl") == self.url for t in pages(host, port))
        except NotRunning:
            return False

    def send(self, method: str, **params):
        """One call, answered.  Waits in slices: between slices it looks whether
        the page still exists, so a renderer that dies mid-call (E-040) is an
        error within seconds, not a wait that never ends."""
        import time
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method, "params": params}))
        started = time.time()
        while True:
            try:
                raw = self.ws.recv()
            except websocket.WebSocketTimeoutException:
                if not self.alive():
                    raise PageGone(f"{method}: TOTAL's report page is gone (its browser process ended) -- "
                                   "reopen the report in TOTAL") from None
                if time.time() - started > self.timeout:
                    raise TimeoutError(f"{method}: no answer in {self.timeout:.0f}s") from None
                continue
            except (websocket.WebSocketConnectionClosedException, ConnectionError, OSError) as exc:
                raise PageGone(f"{method}: connection to the report page lost ({exc})") from None
            message = json.loads(raw)
            if message.get("id") == self._id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            # protocol events are not used here

    def evaluate(self, expression: str, await_promise: bool = False):
        result = self.send("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=await_promise)
        details = result.get("exceptionDetails")
        if details:
            text = (details.get("exception", {}).get("description")
                    or details.get("text", "unknown"))
            raise RuntimeError(f"page error: {text}")
        return result.get("result", {}).get("value")

    def handle(self, expression: str) -> str:
        """Evaluate and keep the result as a remote object, not a copy.

        A DOM node cannot be carried back as a value; file upload needs the
        node itself, so its objectId is what comes back here.
        """
        result = self.send("Runtime.evaluate", expression=expression,
                           returnByValue=False)
        details = result.get("exceptionDetails")
        if details:
            raise RuntimeError(f"page error: {details.get('text')}")
        object_id = result.get("result", {}).get("objectId")
        if not object_id:
            raise RuntimeError("expression did not yield an element")
        return object_id

    def set_files(self, object_id: str, paths: list[str]) -> None:
        """Hand files to a file input, as choosing them in the dialog would.

        The page sees exactly what it sees from a real selection -- its own
        change handler runs -- so nothing has to be faked about how a photo
        arrives.
        """
        self.send("DOM.setFileInputFiles", files=paths, objectId=object_id)

    def release(self, object_id: str) -> None:
        try:
            self.send("Runtime.releaseObject", objectId=object_id)
        except Exception:
            pass

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
