"""Rendered reports, kept ready before anyone asks for them.

Laying the report out takes seconds: the page is measured in a real browser
and verified against the body rule.  Doing that on every request made every
page switch wait.  So the layout is done in the background instead:

* every change to a case (a value, a photo, an exhibit box, a comparable)
  queues a fresh render of the editor's form and the preview;
* a render is stored against a **key** -- a digest of the exact document,
  images, editor state and renderer code it was made from -- in memory and on
  disk, so a restart does not lose it;
* a request is answered at once with the render for the current key.  If
  that is not ready but an older one is, the older one is returned marked
  stale and the page swaps itself for the fresh one when it lands; if there is
  nothing yet, the caller shows a loading page that waits for it.

One worker renders at a time, newest request first per case, and a render
whose key changed while it ran is simply done again -- nothing stale is ever
stored under a current key.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from uad.report import browser, flow

KINDS = ("form", "preview")
DATA_URI = re.compile(r"data:([a-z]+/[a-z0-9.+-]+);base64,([A-Za-z0-9+/=]+)")
EXT = {"image/png": "png", "image/jpeg": "jpg", "image/gif": "gif", "image/webp": "webp",
       "image/svg+xml": "svg", "image/tiff": "tif", "image/bmp": "bmp",
       "font/ttf": "ttf", "font/otf": "otf", "font/woff2": "woff2", "font/woff": "woff"}
CODE = [Path(flow.__file__), Path(flow.__file__).with_name("form.py"),
        Path(flow.__file__).with_name("comparables.py"),
        Path(flow.__file__).with_name("rules.py"), Path(__file__)]


def background(work: Callable[[], None], name: str = "work") -> threading.Thread:
    """Run something off the request thread, so the page is answered at once."""
    thread = threading.Thread(target=work, name=name, daemon=True)
    thread.start()
    return thread


@dataclass
class Render:
    key: str
    html: str
    made: float


class Renderer:
    def __init__(self, store: Callable, media: Callable, prefs: Callable):
        self._store, self._media, self._prefs = store, media, prefs
        self._cache: dict[tuple[str, str], Render] = {}
        self._queue: dict[tuple[str, str], float] = {}
        self._busy: tuple[str, str] | None = None
        self._lock = threading.Condition()
        self._thread = threading.Thread(target=self._run, name="renderer", daemon=True)
        self._thread.start()

    # ----------------------------------------------------------------- keys
    def key(self, case_id: str, kind: str) -> str:
        st = self._store()
        h = hashlib.sha1(kind.encode())
        xml = st.xml_path(case_id)
        if xml.exists():
            stat = xml.stat()
            h.update(f"{stat.st_mtime_ns}:{stat.st_size}".encode())
        for m in self._media(case_id):
            h.update(json.dumps(m, sort_keys=True, default=str).encode())
        if kind == "form":
            prefs = self._prefs(case_id)
            h.update(json.dumps({"slots": prefs.get("exhibitSlots"), "fills": prefs.get("fills"),
                                 "imported": prefs.get("imported")},
                                sort_keys=True).encode())
        for path in CODE:
            if path.exists():
                h.update(str(path.stat().st_mtime_ns).encode())
        return h.hexdigest()[:16]

    def assets(self, case_id: str) -> Path:
        folder = self._store().folder(case_id) / "_render" / "assets"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _externalise(self, case_id: str, html: str) -> str:
        """Every embedded photograph and font, served once instead.

        The page is laid out and measured with everything inline, then each
        large data URI is written to a file named by its digest and the page
        points at that URL.  The bytes are the same, so the layout is the
        same; the browser fetches each file once and keeps it, so a page that
        was 11 MB is a few hundred KB, and the next render reuses the files.
        """
        folder = self.assets(case_id)

        def swap(match: "re.Match") -> str:
            mime, payload = match.group(1), match.group(2)
            if len(payload) < 4096:
                return match.group(0)
            digest = hashlib.sha1(payload.encode("ascii")).hexdigest()[:20]
            ext = EXT.get(mime, "bin")
            path = folder / f"{digest}.{ext}"
            if not path.exists():
                path.write_bytes(base64.b64decode(payload))
            return f"/api/cases/{case_id}/asset/{digest}.{ext}"

        return DATA_URI.sub(swap, html)

    def _disk(self, case_id: str, kind: str) -> Path:
        folder = self._store().folder(case_id) / "_render"
        folder.mkdir(exist_ok=True)
        return folder / f"{kind}.html"

    # ----------------------------------------------------------------- read
    def get(self, case_id: str, kind: str) -> tuple[Render | None, str]:
        """(the newest render there is, the key a fresh one would carry)."""
        want = self.key(case_id, kind)
        have = self._cache.get((case_id, kind))
        if have is None:
            path = self._disk(case_id, kind)
            meta = path.with_suffix(".json")
            if path.exists() and meta.exists():
                try:
                    info = json.loads(meta.read_text(encoding="utf-8"))
                    have = Render(info["key"], path.read_text(encoding="utf-8"), info["made"])
                    self._cache[(case_id, kind)] = have
                except (ValueError, KeyError, OSError):
                    have = None
        if (have is None or have.key != want) and browser.server_layout():
            self.request(case_id, kind)
        return have, want

    def ready(self, case_id: str, kind: str) -> bool:
        have, want = self.get(case_id, kind)
        return have is not None and have.key == want

    def wait(self, case_id: str, kind: str, timeout: float = 90.0) -> Render | None:
        end = time.time() + timeout
        while time.time() < end:
            have, want = self.get(case_id, kind)
            if have is not None and have.key == want:
                return have
            with self._lock:
                self._lock.wait(0.25)
        return None

    # ---------------------------------------------------------------- write
    def request(self, case_id: str, kind: str | None = None) -> None:
        with self._lock:
            for k in ([kind] if kind else KINDS):
                self._queue.setdefault((case_id, k), time.time())
            self._lock.notify_all()

    def changed(self, case_id: str) -> None:
        """A case changed: have its form and preview ready again soon."""
        self.request(case_id)

    def forget(self, case_id: str) -> None:
        with self._lock:
            for k in KINDS:
                self._cache.pop((case_id, k), None)
                self._queue.pop((case_id, k), None)

    def _next(self) -> tuple[str, str] | None:
        with self._lock:
            while not self._queue:
                self._lock.wait()
            # the editor's form before the preview; oldest request first
            job = min(self._queue, key=lambda j: (KINDS.index(j[1]), self._queue[j]))
            self._queue.pop(job)
            self._busy = job
            return job

    def _run(self) -> None:
        while True:
            job = self._next()
            try:
                self._render(*job)
            except Exception as exc:          # a broken case must not stop the worker
                print(f"[renderer] {job}: {exc!r}")
            finally:
                with self._lock:
                    self._busy = None
                    self._lock.notify_all()

    def build_kwargs(self, case_id: str, kind: str) -> dict:
        """What flow.build is given for this case and kind -- one place, so the
        server's own layout and the browser-measured one agree."""
        st = self._store()
        prefs = self._prefs(case_id)
        kwargs = dict(folder=st.folder(case_id), media=self._media(case_id), screen=True)
        if kind == "form":
            slots = [s for s in (prefs.get("exhibitSlots") or []) if isinstance(s, dict) and s.get("id")]
            # what an import answered, so the editor can show it in green
            brought = (prefs.get("imported") or {}).get("fields") or []
            kwargs.update(edit=True, slots=slots, imported=brought)
        return kwargs

    # ------------------------------------------- layout measured elsewhere
    # A host without Chromium (serverless) cannot measure a page.  The
    # appraiser's browser can: it is handed the galley, reports the geometry,
    # and is handed back pages to check.  The planning arithmetic stays in
    # flow.py.  Nothing the browser sends is stored or shown to anyone else --
    # the result goes back only to the browser that measured it.
    def client_galley(self, case_id: str, kind: str) -> str:
        kw = self.build_kwargs(case_id, kind)
        galley, _meta = flow.prepare(self._store().tree(case_id), folder=kw["folder"],
                                     media=kw["media"], edit=kw.get("edit", False),
                                     slots=kw.get("slots"), imported=kw.get("imported", ()))
        return self._externalise(case_id, galley)

    def client_pages(self, case_id: str, kind: str, measured: list[dict],
                     caps: dict[int, float]) -> tuple[str, list[float]]:
        kw = self.build_kwargs(case_id, kind)
        meta = flow.Meta.from_case(self._store().tree(case_id))
        html, pages = flow.paginate(measured, meta, caps, screen=True,
                                    edit=kw.get("edit", False),
                                    imported=kw.get("imported", ()))
        return self._externalise(case_id, html), [p.planned for p in pages]

    def _render(self, case_id: str, kind: str) -> None:
        st = self._store()
        if not st.xml_path(case_id).exists():
            return
        key = self.key(case_id, kind)
        have = self._cache.get((case_id, kind))
        if have is not None and have.key == key:
            return
        kwargs = self.build_kwargs(case_id, kind)
        html = flow.build(st.tree(case_id), **kwargs)
        html = self._externalise(case_id, html)
        if self.key(case_id, kind) != key:
            self.request(case_id, kind)       # changed while rendering: do it again
            return
        render = Render(key, html, time.time())
        path = self._disk(case_id, kind)
        path.write_text(html, encoding="utf-8")
        path.with_suffix(".json").write_text(json.dumps({"key": key, "made": render.made}),
                                             encoding="utf-8")
        with self._lock:
            self._cache[(case_id, kind)] = render
            self._lock.notify_all()
