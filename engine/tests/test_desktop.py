"""The desktop edition and Download product (owner, 2026-10-09).

* the licence key is held as a PBKDF2 verifier and checked the same way by the
  web download, the installer and the app (app/license.py);
* Download product hands out the installer in parts only for the key
  (app/download.py);
* the desktop app's window has a one-time way in, and an unactivated copy
  asks for the key before anything else (app/desktop.py);
* the renderer drives the system Edge / Chrome without Playwright and gets
  the very same measurements, page checks and PDF (uad/report/cdp.py);
* two speed fixes found while measuring: per-version results are computed
  once when asked for together, and a report opened on another report's
  shared layout finds that report's images instead of rebuilding itself once
  per image.

Run with the rest: ``python -m pytest -q tests/test_desktop.py``.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE))
from app import license as lic  # noqa: E402

KEY = "test-key-only-for-tests"


@pytest.fixture
def licence(tmp_path, monkeypatch):
    """A verifier for a key known only to these tests, in place of the real one."""
    cfg = lic.make_config(KEY, iterations=1000)
    path = tmp_path / "license.json"
    path.write_text(json.dumps(cfg))
    monkeypatch.setattr(lic, "CONFIG", path)
    return cfg


# ----------------------------------------------------------------- the key
def test_the_shipped_verifier_holds_no_key():
    cfg = json.loads((ENGINE / "app" / "license.json").read_text())
    assert set(cfg) == {"algorithm", "iterations", "salt", "check", "ticket"}
    assert cfg["algorithm"] == "pbkdf2_sha256" and cfg["iterations"] >= 600_000
    # nothing but hex digests and the salt: no plain text anywhere in it
    for k in ("salt", "check", "ticket"):
        int(cfg[k], 16)
    for wrong in ("", "uad3.6", "password", "licence"):
        assert lic.check(wrong, cfg) is None


def test_key_ticket_and_refusals(licence):
    ticket = lic.check(KEY)
    assert ticket and len(ticket) == 64 and lic.ticket_valid(ticket)
    assert lic.check("  " + KEY + "\n") == ticket          # surrounding spaces only
    assert lic.check(KEY.upper()) is None and lic.check(KEY + "x") is None
    assert not lic.ticket_valid("0" * 64) and not lic.ticket_valid("")


def test_the_installer_check_reads_utf16_and_removes_the_key_file(licence, tmp_path):
    key_file = tmp_path / "key.txt"
    key_file.write_bytes(b"\xff\xfe" + KEY.encode("utf-16-le"))     # NSIS FileWriteUTF16LE /BOM
    run = [sys.executable, "-I", "-S", str(ENGINE / "app" / "license.py"), "check",
           str(key_file), str(lic.CONFIG)]
    assert subprocess.run(run).returncode == 0
    assert not key_file.exists()
    assert lic.ticket_valid((tmp_path / "ticket.txt").read_text(), licence)
    (tmp_path / "ticket.txt").unlink()
    key_file.write_text("wrong", encoding="utf-8")
    assert subprocess.run(run).returncode == 1
    assert not key_file.exists() and not (tmp_path / "ticket.txt").exists()


# ------------------------------------------------------- Download product
@pytest.fixture
def shelf(tmp_path, monkeypatch):
    from app import download
    data = os.urandom(9_000)
    parts = [data[:4000], data[4000:8000], data[8000:]]
    folder = tmp_path / "shelf"
    folder.mkdir()
    entries = []
    for n, chunk in enumerate(parts):
        (folder / f"setup.part{n:02d}").write_bytes(chunk)
        entries.append({"file": f"setup.part{n:02d}", "size": len(chunk),
                        "sha256": hashlib.sha256(chunk).hexdigest()})
    (folder / "manifest.json").write_text(json.dumps({
        "name": "Setup.exe", "version": "9.9.9", "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(), "parts": entries}))
    monkeypatch.setattr(download, "SHELF", folder)
    monkeypatch.setattr(download, "THROTTLE", lic.Throttle())
    app = FastAPI()
    app.include_router(download.router)
    return TestClient(app), data


def test_download_needs_the_key_and_the_parts_join_to_the_installer(licence, shelf):
    client, data = shelf
    assert client.get("/api/desktop/info").json()["available"] is True
    bad = client.post("/api/desktop/ticket", json={"key": "nope"})
    assert bad.status_code == 403                 # never 401: the editor reloads on 401
    assert client.get("/api/desktop/part/0").status_code == 403
    assert client.get("/api/desktop/part/0?t=" + "0" * 64).status_code == 403
    ok = client.post("/api/desktop/ticket", json={"key": KEY}).json()
    assert ok["version"] == "9.9.9" and len(ok["parts"]) == 3
    got = b"".join(client.get(f"/api/desktop/part/{n}?t={ok['ticket']}").content
                   for n in range(len(ok["parts"])))
    assert got == data and hashlib.sha256(got).hexdigest() == ok["sha256"]
    assert client.get(f"/api/desktop/part/3?t={ok['ticket']}").status_code == 404


def test_wrong_keys_are_throttled(licence, shelf):
    client, _ = shelf
    for _ in range(lic.MAX_FAILURES):
        assert client.post("/api/desktop/ticket", json={"key": "guess"}).status_code == 403
    assert client.post("/api/desktop/ticket", json={"key": KEY}).status_code == 429


def test_the_shelved_installer_matches_its_manifest():
    shelf = ENGINE.parent / "downloads" / "desktop"
    if not (shelf / "manifest.json").exists():
        pytest.skip("no installer built (python desktop/build.py)")
    m = json.loads((shelf / "manifest.json").read_text())
    data = b""
    for p in m["parts"]:
        chunk = (shelf / p["file"]).read_bytes()
        assert len(chunk) < 4_500_000                       # a serverless answer's limit
        assert hashlib.sha256(chunk).hexdigest() == p["sha256"]
        data += chunk
    assert len(data) == m["size"] and hashlib.sha256(data).hexdigest() == m["sha256"]
    assert data[:2] == b"MZ"                                # a Windows executable


def test_the_installer_script_is_plain_ascii_and_asks_for_the_key():
    nsi = (ENGINE.parent / "desktop" / "installer.nsi").read_text(encoding="utf-8")
    assert all(ord(c) < 128 for c in nsi)        # a "\u" once became a Hangul syllable
    assert "Page custom KeyPage KeyLeave" in nsi
    assert "license.py\" check" in nsi and "RequestExecutionLevel user" in nsi
    assert "license.json" in nsi and "qwerty" not in nsi.lower()


# --------------------------------------------------------- desktop doors
@pytest.fixture
def desktop_app(licence, tmp_path, monkeypatch):
    from app import desktop
    from app.access import Access, COOKIE, guard, make_config
    monkeypatch.setenv("URAR_DESKTOP_DATA", str(tmp_path / "data"))
    monkeypatch.setenv("URAR_DESKTOP_TOKEN", "window-token")
    monkeypatch.setattr(desktop, "THROTTLE", lic.Throttle())
    access = Access(make_config("unused-passcode", iterations=1000))
    app = FastAPI()

    @app.get("/")
    def home():
        return {"editor": True}

    @app.get("/api/cases")
    def cases():
        return {"cases": []}

    desktop.install(app, access)

    @app.middleware("http")
    async def gate(request, call_next):
        blocked = guard(access, request)
        return blocked if blocked is not None else await call_next(request)

    return TestClient(app), desktop, COOKIE


def test_the_window_key_is_the_only_way_in(desktop_app):
    client, desktop, cookie = desktop_app
    desktop.activate(lic.check(KEY))
    assert client.get("/").status_code == 401                    # the web passcode gate
    assert client.get("/desktop/unlock?k=wrong", follow_redirects=False).status_code == 403
    r = client.get("/desktop/unlock?k=window-token", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/" and cookie in r.cookies
    assert client.get("/").json() == {"editor": True}


def test_an_unactivated_copy_asks_for_the_key_first(desktop_app):
    client, desktop, _ = desktop_app
    r = client.get("/desktop/unlock?k=window-token", follow_redirects=False)
    assert r.headers["location"] == "/desktop/activate"
    assert client.get("/", follow_redirects=False).headers["location"] == "/desktop/activate"
    assert client.get("/api/cases").status_code == 403
    assert "Licence key" in client.get("/desktop/activate").text
    assert client.post("/desktop/activate", data={"key": "wrong"}).status_code == 401
    assert not desktop.activated()
    r = client.post("/desktop/activate", data={"key": KEY}, follow_redirects=False)
    assert r.status_code == 303 and desktop.activated()
    assert client.get("/api/cases").json() == {"cases": []}


def test_a_forged_activation_record_is_refused(desktop_app):
    _, desktop, _ = desktop_app
    path = desktop.activation_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"ticket": "f" * 64}))
    assert not desktop.activated()


# --------------------------------------------- the system browser, no Playwright
def _system_browser() -> str | None:
    from uad.report import cdp
    return cdp.find_browser() if cdp.available() else None


@pytest.mark.skipif(_system_browser() is None, reason="no Edge / Chrome / Chromium here")
def test_the_system_browser_measures_checks_and_prints_like_playwright(tmp_path, monkeypatch):
    pytest.importorskip("playwright")
    import glob
    from lxml import etree
    from uad.report import cdp, flow
    sample = sorted(glob.glob(str(ENGINE.parent / "specs/official/**/SF1_Appraisal_v1.4.xml"),
                              recursive=True))[0]
    galley, meta = flow.prepare(etree.parse(sample))
    by_playwright = flow.measure(galley)
    monkeypatch.setattr(flow, "sync_playwright", cdp.sync_playwright)
    by_system = flow.measure(galley)
    assert by_system == by_playwright                    # every block, every number
    html, _pages = flow.paginate(by_system, meta, {})
    bottoms = flow.verify(html)
    flow.to_pdf(html, tmp_path / "system.pdf")
    monkeypatch.undo()
    assert bottoms == flow.verify(html)
    flow.to_pdf(html, tmp_path / "playwright.pdf")
    pymupdf = pytest.importorskip("pymupdf")
    a, b = pymupdf.open(tmp_path / "system.pdf"), pymupdf.open(tmp_path / "playwright.pdf")
    assert len(a) == len(b) and a[0].rect == b[0].rect          # Legal, every page
    for i in range(len(a)):
        assert a[i].get_text() == b[i].get_text()
        assert a[i].get_pixmap(dpi=50).samples == b[i].get_pixmap(dpi=50).samples


def test_the_driver_is_chosen_by_what_the_host_has():
    code = ("import sys; sys.path.insert(0, %r); from uad.report import browser; "
            "print(browser.DRIVER)" % str(ENGINE))
    env = {**os.environ, "URAR_BROWSER_DRIVER": "cdp", "URAR_BROWSER": "/nonexistent/browser"}
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
    assert out.stdout.strip() == ""                       # asked for the system browser, none there
    if _system_browser():
        env["URAR_BROWSER"] = _system_browser()
        out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True)
        assert out.stdout.strip() == "cdp"


# ------------------------------------------------------------ speed fixes
def test_a_per_version_result_is_computed_once_when_asked_together(tmp_path):
    from app.cases import Store
    st = Store(tmp_path / "cases")
    try:
        cid = st.create(template="sf1_appraisal_v1_4", name="memo", blank=True, actor="t").case_id
        calls = []

        def slow():
            calls.append(1)
            time.sleep(0.3)
            return "built"
        threads = [threading.Thread(target=lambda: st._memo("probe", cid, slow)) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(calls) == 1 and st._memo("probe", cid, slow) == "built"
    finally:
        st.conn.close()


def test_a_shared_layout_finds_its_images_without_rebuilding(tmp_path, monkeypatch):
    from app import api, renders
    from app.access import sign_in
    from app.cases import Store
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    with TestClient(app) as c:
        sign_in(c)
        a = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False}).json()["case_id"]
        b = c.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False}).json()["case_id"]
        c.get(f"/api/cases/{a}/layout/form/galley")              # a's render writes its images
        names = [p.name for p in api.renderer().assets(a).iterdir()]
        assert names, "the sample's galley carries images"
        rebuilt = []
        monkeypatch.setattr(api.renderer(), "client_galley",
                            lambda *x, **k: rebuilt.append(x))
        for name in names:
            r = c.get(f"/api/cases/{b}/asset/{name}")
            assert r.status_code == 200 and r.content == (api.renderer().assets(a) / name).read_bytes()
        assert rebuilt == []
    store.conn.close()
    del renders


def test_download_is_open_without_the_passcode_but_reports_are_not(tmp_path, monkeypatch):
    from app import api
    from app.cases import Store
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    with TestClient(app) as c:                       # no sign-in: a licence holder off the street
        assert "/download" in c.get("/").text          # the sign-in page links to it
        page = c.get("/download")
        assert page.status_code == 200 and "/ui/download.js" in page.text
        assert c.get("/ui/download.js").status_code == 200
        assert c.get("/api/desktop/info").status_code == 200
        assert c.post("/api/desktop/ticket", json={"key": "guess"}).status_code == 403
        assert c.get("/api/cases").status_code == 401        # the reports stay behind the passcode
        assert c.get("/ui/index.html").status_code == 401
    store.conn.close()
