"""Laid-out reports shared by content, so a report opens without being laid out.

Laying a report out takes seconds (25 s cold with the server's Chromium, a
similar wait in the appraiser's browser on a host without one).  But the
layout depends only on what the report holds -- the render key
(``renders.Renderer.key``) is a digest of the document, its media, the editor
state and the renderer's own code -- not on which case it is.  Every new
report starts as the same document, so every new report has the same key, and
its layout only ever has to be made once.

So a finished layout is kept here under its key, case-neutral (the one place a
case id appears, an image URL ``/api/cases/<id>/asset/...``, is replaced by a
token and put back when served), in memory and in the shared store every
server copy reads (``app/durable.py``: Vercel Blob or a shared directory), or
under the work folder on a single server.  Opening any report whose key has
been laid out before -- by this server or any other copy, for this case or any
other -- is one read.

What is shared is a page the server itself built: from its own Chromium
(``flow.build``), or from a browser's layout pass in which only the browser's
numbers are used and every block's markup is the server's own galley for that
key (``flow.trusted``) -- so a shared layout never holds anything a browser
sent.  It is stored only when that pass reports that every page fits.
"""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path

TOKEN = "__UAD_CASE__"
_KEY = re.compile(r"^[0-9a-f]{16}$")
_MEMORY_LIMIT = 24


def neutral(html: str, case_id: str) -> str:
    return html.replace(f"/api/cases/{case_id}/", f"/api/cases/{TOKEN}/")


def for_case(html: str, case_id: str) -> str:
    return html.replace(f"/api/cases/{TOKEN}/", f"/api/cases/{case_id}/")


class Layouts:
    def __init__(self, backend=None, folder: Path | None = None):
        self.backend = backend
        self.folder = folder
        self._memory: dict[tuple[str, str], str] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _name(key: str, kind: str) -> str:
        return f"layouts/{kind}/{key}.html"

    def get(self, key: str, kind: str) -> str | None:
        if not _KEY.match(key or ""):
            return None
        with self._lock:
            hit = self._memory.get((key, kind))
        if hit is not None:
            return hit
        html = None
        if self.backend is not None:
            try:
                status, data, _etag = self.backend.get(self._name(key, kind))
                if status == 200 and data:
                    html = data.decode("utf-8")
            except Exception:
                html = None
        if html is None and self.folder is not None:
            path = self.folder / self._name(key, kind)
            if path.is_file():
                html = path.read_text(encoding="utf-8")
        if html is not None:
            self._remember(key, kind, html)
        return html

    def put(self, key: str, kind: str, html: str) -> None:
        if not _KEY.match(key or "") or not html:
            return
        with self._lock:
            if self._memory.get((key, kind)) == html:
                return
        self._remember(key, kind, html)
        if self.backend is not None:
            threading.Thread(target=self._upload, args=(key, kind, html), daemon=True).start()
        elif self.folder is not None:
            path = self.folder / self._name(key, kind)
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_suffix(".part")
                tmp.write_text(html, encoding="utf-8")
                os.replace(tmp, path)
            except OSError:
                pass

    def _upload(self, key: str, kind: str, html: str) -> None:
        try:
            self.backend.put(self._name(key, kind), html.encode("utf-8"), "text/html")
        except Exception:
            pass                            # a cache: the next layout tries again

    def _remember(self, key: str, kind: str, html: str) -> None:
        with self._lock:
            self._memory.pop((key, kind), None)
            self._memory[(key, kind)] = html
            while len(self._memory) > _MEMORY_LIMIT:
                self._memory.pop(next(iter(self._memory)))
