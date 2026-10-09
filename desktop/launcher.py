"""UAD 3.6 desktop: start the platform on this PC and open it in its own window.

What the Start-menu shortcut runs (``python\\pythonw.exe app\\desktop\\launcher.py``):

1. One copy at a time: a second start opens another window on the copy that
   is already running.
2. The server runs inside this process on 127.0.0.1 only -- nothing on the
   network can reach it -- with a random one-time key for the window
   (app/desktop.py) and the reports kept in ``%LOCALAPPDATA%\\UAD36\\cases``.
3. The window is Microsoft Edge in app mode (no address bar, no tabs) with its
   own profile, so the editor keeps its layouts and settings between runs.
4. Closing the last window stops the server.

The report is laid out in that window, as on the web, and the PDF and the
delivery ZIP are printed by the same Edge, driven headless
(uad/report/cdp.py) -- nothing is downloaded and nothing leaves the PC except
what the appraiser asks for (address lookup, map tiles).

Everything is logged to ``%LOCALAPPDATA%\\UAD36\\logs\\desktop.log``.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent              # <install>/app/desktop
APP = HERE.parent                                   # <install>/app
ENGINE = APP / "engine"
DATA = Path(os.environ.get("URAR_DESKTOP_DATA")
            or Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "UAD36")
RUN = DATA / "run.json"
PORTS = range(27536, 27556)


def _log_to_file() -> None:
    logs = DATA / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    path = logs / "desktop.log"
    if path.exists() and path.stat().st_size > 2_000_000:
        path.replace(logs / "desktop.old.log")
    stream = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = stream
    print(f"\n--- {time.strftime('%Y-%m-%d %H:%M:%S')} UAD 3.6 desktop starting (pid {os.getpid()})")


def _alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=2) as r:
            return r.status == 200
    except Exception:
        return False


def _free_port() -> int:
    for port in PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _browser() -> str | None:
    sys.path.insert(0, str(ENGINE))
    from uad.report import cdp
    return cdp.find_browser()


def _open_window(url: str) -> subprocess.Popen | None:
    exe = _browser()
    if not exe:
        import webbrowser
        webbrowser.open(url)
        return None
    profile = DATA / "window"
    profile.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen(
        [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run",
         "--no-default-browser-check", "--window-size=1600,1000", "--disable-sync",
         "--disable-features=msEdgeSidebarV2,msHubApps,Translate"],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _already_running() -> bool:
    """Another copy is serving: give it a new window and step aside."""
    try:
        run = json.loads(RUN.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if not _alive(int(run.get("port", 0))):
        return False
    _open_window(f"http://127.0.0.1:{run['port']}/desktop/unlock?k={run['token']}")
    return True


def main() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    _log_to_file()
    if _already_running():
        print("another copy is running: opened a window on it")
        return 0
    port = _free_port()
    token = secrets.token_urlsafe(32)
    (DATA / "cases").mkdir(parents=True, exist_ok=True)
    os.environ.update({
        "URAR_DESKTOP": "1",
        "URAR_DESKTOP_DATA": str(DATA),
        "URAR_DESKTOP_TOKEN": token,
        "URAR_WORK": str(DATA / "cases"),
        # the window lays the report out (fast, and what the web does); the
        # server keeps Edge for the PDF and the delivery ZIP
        "URAR_CLIENT_LAYOUT": "1",
        "URAR_BROWSER_DRIVER": "cdp",
        # the web passcode does not apply here: the window's one-time key does
        "URAR_ACCESS_CODE": secrets.token_urlsafe(24),
    })
    sys.path.insert(0, str(ENGINE))
    os.chdir(ENGINE)
    import uvicorn
    from app import api
    from app.access import COOKIE
    from app.main import ACCESS, app

    api.SERVER = {"base": f"http://127.0.0.1:{port}", "cookie": COOKIE, "token": ACCESS.token}
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning",
                                           access_log=False))

    def window_then_stop() -> None:
        for _ in range(300):
            if server.started:
                break
            time.sleep(0.1)
        RUN.write_text(json.dumps({"pid": os.getpid(), "port": port, "token": token}), encoding="utf-8")
        print(f"serving on http://127.0.0.1:{port}")
        proc = _open_window(f"http://127.0.0.1:{port}/desktop/unlock?k={token}")
        if proc is None:
            print("no Edge or Chrome found: opened the default browser; the server stays up")
            return
        proc.wait()
        # Edge can hand a window to a process of its own and exit at once; the
        # open editor checks in every 30 s, so stop only once none has
        from app import desktop
        while desktop.idle_seconds() < 90:
            time.sleep(5)
        print("window closed: stopping")
        server.should_exit = True

    threading.Thread(target=window_then_stop, name="window", daemon=True).start()
    try:
        server.run()
    finally:
        try:
            if json.loads(RUN.read_text(encoding="utf-8")).get("pid") == os.getpid():
                RUN.unlink()
        except (OSError, ValueError):
            pass
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:                       # the log is the only console a windowed app has
        import traceback
        traceback.print_exc()
        raise
