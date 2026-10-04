"""Shared, durable case storage for a server that runs as many copies.

A serverless deployment (Vercel) runs several short-lived copies of this
server, each with its own temporary disk.  Without a shared store a case made
on one copy does not exist on the next, and the report a user just created
"does not load".  This module keeps every case in one place all copies read:

* each case's bundle (app/cases.py ``Store.bundle``, without images) at
  ``cases/<id>/case.zip`` -- overwritten on every change;
* each image once, at ``cases/<id>/img/<filename>``.

Before a request about a case is handled the copy asks the store whether its
local copy is current (a conditional GET on the bundle's ETag: one small round
trip, 304 when nothing changed) and takes the newer bundle if there is one.
After a request changes a case the copy writes the new bundle back.  So every
copy works from the latest version and none can overwrite newer work with an
older one -- the last write, in time order, is the one kept.

The backend is Vercel Blob (private store), spoken over its REST protocol --
the same requests the official ``@vercel/blob`` client sends (API version 12).
It is enabled by ``BLOB_READ_WRITE_TOKEN``, which Vercel sets when a Blob
store is connected to the project.  Without it this module does nothing and
the local disk is the store, as on a desktop or a server with a real disk.

``URAR_DURABLE_DIR`` selects a shared directory instead (several containers
on one mounted volume; the multi-copy tests).  A Postgres backend (Supabase, Neon) can implement the same five methods of
``Backend`` and be selected the same way; nothing else would change.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = os.environ.get("VERCEL_BLOB_API_URL", "https://vercel.com/api/blob")
API_VERSION = "12"
MARKER = ".durable.json"          # which images this copy has already sent
TIMEOUT = 25


class Backend:
    """What a shared store must do."""

    def get(self, key: str, etag: str = "") -> tuple[int, bytes, str]: ...
    def put(self, key: str, data: bytes, content_type: str) -> str: ...
    def list(self, prefix: str) -> list[dict]: ...
    def delete(self, urls: list[str]) -> None: ...


class BlobBackend(Backend):
    def __init__(self, token: str):
        self.token = token
        parts = token.split("_")
        self.store_id = parts[3] if len(parts) > 3 else ""
        if self.store_id.startswith("store_"):
            self.store_id = self.store_id[len("store_"):]

    def _api(self, path: str, *, method: str = "GET", data: bytes | None = None,
             headers: dict | None = None) -> dict:
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "authorization": f"Bearer {self.token}",
            "x-api-version": API_VERSION,
            "x-vercel-blob-store-id": self.store_id,
            **(headers or {})})
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            body = r.read()
        return json.loads(body) if body else {}

    def get(self, key: str, etag: str = "") -> tuple[int, bytes, str]:
        url = (f"https://{self.store_id}.private.blob.vercel-storage.com/"
               f"{urllib.parse.quote(key)}?cache=0")
        headers = {"authorization": f"Bearer {self.token}"}
        if etag:
            headers["If-None-Match"] = etag
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
                return r.status, r.read(), r.headers.get("etag", "")
        except urllib.error.HTTPError as e:
            if e.code in (304, 404):
                return e.code, b"", etag if e.code == 304 else ""
            raise

    def put(self, key: str, data: bytes, content_type: str) -> str:
        q = urllib.parse.urlencode({"pathname": key})
        res = self._api(f"/?{q}", method="PUT", data=data, headers={
            "x-vercel-blob-access": "private", "x-add-random-suffix": "0",
            "x-allow-overwrite": "1", "x-content-type": content_type,
            "x-cache-control-max-age": "60"})
        return res.get("etag", "")

    def list(self, prefix: str) -> list[dict]:
        out, cursor = [], ""
        while True:
            q = {"prefix": prefix, "limit": "1000"}
            if cursor:
                q["cursor"] = cursor
            res = self._api("/?" + urllib.parse.urlencode(q))
            out.extend(res.get("blobs") or [])
            cursor = res.get("cursor") or ""
            if not res.get("hasMore") or not cursor:
                return out

    def delete(self, urls: list[str]) -> None:
        for i in range(0, len(urls), 100):
            self._api("/delete", method="POST", data=json.dumps({"urls": urls[i:i + 100]}).encode(),
                      headers={"content-type": "application/json"})


class DirBackend(Backend):
    """A shared directory (a mounted volume, or a test): same contract as Blob."""

    def __init__(self, root: str):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root.resolve() not in path.parents:
            raise ValueError(key)
        return path

    def get(self, key: str, etag: str = "") -> tuple[int, bytes, str]:
        path = self._path(key)
        if not path.is_file():
            return 404, b"", ""
        data = path.read_bytes()
        tag = hashlib.sha1(data).hexdigest()
        return (304, b"", tag) if tag == etag else (200, data, tag)

    def put(self, key: str, data: bytes, content_type: str) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + f".{os.getpid()}.{threading.get_ident()}")
        tmp.write_bytes(data)
        os.replace(tmp, path)
        return hashlib.sha1(data).hexdigest()

    def list(self, prefix: str) -> list[dict]:
        return [{"pathname": p.relative_to(self.root).as_posix(), "url": p.relative_to(self.root).as_posix()}
                for p in sorted(self.root.rglob("*")) if p.is_file()
                and p.relative_to(self.root).as_posix().startswith(prefix)]

    def delete(self, urls: list[str]) -> None:
        for u in urls:
            self._path(u).unlink(missing_ok=True)


def _case_key(case_id: str) -> str:
    return f"cases/{case_id}/case.zip"


class Durable:
    """Keeps a Store in step with a shared Backend."""

    def __init__(self, backend: Backend | None):
        self.backend = backend
        self._etags: dict[str, str] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()

    @property
    def on(self) -> bool:
        return self.backend is not None

    def _lock(self, case_id: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(case_id, threading.Lock())

    # --------------------------------------------------------------- read
    def pull(self, store, case_id: str) -> bool:
        """Make this copy's case current.  True when the case exists."""
        if not self.on:
            return True
        with self._lock(case_id):
            local = _exists(store, case_id)
            status, data, etag = self.backend.get(_case_key(case_id),
                                                  self._etags.get(case_id, "") if local else "")
            if status == 304:
                return True
            if status == 404:
                return local
            store.restore(data, replace=True, trusted=True)
            self._etags[case_id] = etag
            for m in store.missing_media(case_id):
                st, img, _ = self.backend.get(f"cases/{case_id}/img/{m.filename}")
                if st == 200:
                    store.put_media_file(case_id, m.media_id, img, quiet=True)
            _write_marker(store, case_id, {m.filename for m in store.media(case_id)})
            return True

    def pull_all(self, store) -> None:
        """Bring every case in the shared store onto this copy (the case list)."""
        if not self.on:
            return
        known = set()
        for blob in self.backend.list("cases/"):
            parts = (blob.get("pathname") or "").split("/")
            if len(parts) == 3 and parts[2] == "case.zip":
                known.add(parts[1])
                try:
                    self.pull(store, parts[1])
                except Exception:
                    continue
        for case in store.list():
            if case.case_id not in known:
                # deleted elsewhere, or never stored (made before the store existed)
                if case.case_id in self._etags:
                    store.delete(case.case_id)

    # -------------------------------------------------------------- write
    def push(self, store, case_id: str) -> None:
        """Write this copy's version of the case to the shared store."""
        if not self.on or not _exists(store, case_id):
            return
        with self._lock(case_id):
            sent = _read_marker(store, case_id)
            for m in store.media(case_id):
                path = store.media_dir(case_id) / m.filename
                if m.filename not in sent and path.is_file():
                    self.backend.put(f"cases/{case_id}/img/{m.filename}", path.read_bytes(),
                                     m.content_type or "application/octet-stream")
                    sent.add(m.filename)
            _write_marker(store, case_id, sent)
            etag = self.backend.put(_case_key(case_id), store.bundle(case_id, images=False),
                                    "application/zip")
            self._etags[case_id] = etag

    def forget(self, case_id: str) -> None:
        if not self.on:
            return
        urls = [b["url"] for b in self.backend.list(f"cases/{case_id}/") if b.get("url")]
        if urls:
            self.backend.delete(urls)
        self._etags.pop(case_id, None)


def _exists(store, case_id: str) -> bool:
    try:
        store.get(case_id)
        return True
    except KeyError:
        return False


def _read_marker(store, case_id: str) -> set[str]:
    path = store.folder(case_id) / MARKER
    try:
        return set(json.loads(path.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        return set()


def _write_marker(store, case_id: str, names: set[str]) -> None:
    (store.folder(case_id) / MARKER).write_text(json.dumps(sorted(names)), encoding="utf-8")


def from_env() -> Durable:
    token = os.environ.get("BLOB_READ_WRITE_TOKEN", "").strip()
    if token:
        return Durable(BlobBackend(token))
    folder = os.environ.get("URAR_DURABLE_DIR", "").strip()
    return Durable(DirBackend(folder) if folder else None)
