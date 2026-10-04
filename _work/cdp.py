"""A minimal Chrome DevTools Protocol client for TOTAL's embedded browser.

TOTAL hosts its UAD 3.6 form in CefSharp and exposes CDP on 127.0.0.1:8088.
Playwright's ``connect_over_cdp`` cannot be used: it calls
``Browser.setDownloadBehavior`` during handshake and CefSharp answers "Browser
context management is not supported".  Talking to the *page* endpoint directly
avoids the browser-level API entirely, and page-level Runtime/DOM is all that
filling a form needs.
"""
from __future__ import annotations

import json
import urllib.request

import websocket           # websocket-client

CDP_HTTP = "http://127.0.0.1:8088"


def targets() -> list[dict]:
    with urllib.request.urlopen(f"{CDP_HTTP}/json/list", timeout=10) as fh:
        return json.load(fh)


def pages() -> list[dict]:
    return [t for t in targets() if t.get("type") == "page"]


class Page:
    """One CDP page connection."""

    def __init__(self, ws_url: str, timeout: float = 20.0):
        self.ws = websocket.create_connection(ws_url, timeout=timeout,
                                              suppress_origin=True)
        self._id = 0

    def send(self, method: str, **params):
        self._id += 1
        self.ws.send(json.dumps({"id": self._id, "method": method,
                                 "params": params}))
        while True:
            message = json.loads(self.ws.recv())
            if message.get("id") == self._id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message.get("result", {})
            # events are ignored

    def evaluate(self, expression: str, await_promise: bool = False):
        """Run JS in the page and return its value."""
        result = self.send("Runtime.evaluate", expression=expression,
                           returnByValue=True, awaitPromise=await_promise)
        details = result.get("exceptionDetails")
        if details:
            text = details.get("exception", {}).get("description") or details.get("text")
            raise RuntimeError(f"JS error: {text}")
        return result.get("result", {}).get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def open_form(index: int = 0) -> Page:
    """Connect to a UAD form page."""
    found = pages()
    if not found:
        raise SystemExit("no CDP page targets; is TOTAL open on the report?")
    return Page(found[index]["webSocketDebuggerUrl"])
