#!/usr/bin/env python3
"""Build the UAD 3.6 desktop installer for Windows -- on Linux or Windows.

    python desktop/build.py            # build, then shelve it for Download product
    python desktop/build.py --no-shelf # build only (desktop/dist/)

What it puts together, all without a Windows machine:

1. **Python 3.11 for Windows x64** -- the Python Software Foundation's own
   package as published on NuGet (``python`` 3.11.9), checked against the
   SHA-256 pinned below, with what an app does not need taken out (pip,
   setuptools, ensurepip, venv, headers).
2. **The libraries** in ``desktop/requirements.txt`` -- the versions the test
   suite passes with -- as Windows wheels from PyPI, unpacked into it.
3. **The platform** -- only files git tracks (so nothing local, no case
   material, no licensed fonts), without the tests: ``engine/``, the
   specification files the platform reads at run time (the same set the web
   deployment carries, vercel.json), and ``desktop/launcher.py``.
4. **An installer** made with NSIS (``makensis``; ``apt install nsis``) from
   ``desktop/installer.nsi``, which asks for the licence key first.
5. **The shelf**: the installer cut into parts of under 4 MB with a
   manifest of SHA-256 digests, in ``downloads/desktop/``, where the web
   platform's Download product button serves it from (app/download.py).

Nothing here needs the licence key: the installer and the app check it
against ``engine/app/license.json``, a PBKDF2 verifier.
"""
from __future__ import annotations

import argparse
import compileall
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
CACHE = HERE / ".cache"
STAGE = HERE / "build" / "stage"
DIST = HERE / "dist"
SHELF = ROOT / "downloads" / "desktop"
PART = 3_500_000                       # under the 4.5 MB a serverless answer may carry

PYTHON = "3.11.9"
PYTHON_URL = f"https://api.nuget.org/v3-flatcontainer/python/{PYTHON}/python.{PYTHON}.nupkg"

# what an installed app has no use for, in the Python package
PY_DROP = ["Lib/site-packages", "Lib/ensurepip", "Lib/venv", "Lib/idlelib", "Lib/tkinter",
           "Lib/turtledemo", "Lib/lib2to3", "Lib/pydoc_data", "Lib/distutils", "Lib/msilib",
           "Lib/test", "Tools", "include", "libs", "Scripts"]
# the specification files the platform reads at run time (vercel.json includeFiles)
SPEC_GLOBS = ["specs/official/**/*_Appraisal_v1.*.xml",
              "specs/official/**/*_AppraisalUpdate_v1.*.xml",
              "specs/official/**/*_CompletionReport_v1.*.xml",
              "specs/official/GSE_UAD_3.6.0_v1.3 (1)/**/*.xsd"]


def say(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# ------------------------------------------------------------------ python
def fetch_python() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    pkg = CACHE / f"python.{PYTHON}.nupkg"
    if not pkg.exists():
        say(f"downloading Python {PYTHON} for Windows (NuGet, Python Software Foundation)")
        with urllib.request.urlopen(PYTHON_URL, timeout=120) as r, open(pkg, "wb") as f:
            shutil.copyfileobj(r, f)
    digest = sha256(pkg)
    pinned = (HERE / "python.sha256")
    if pinned.exists():
        want = pinned.read_text().split()[0]
        if digest != want:
            pkg.unlink()
            raise SystemExit(f"the Python package does not match its pinned SHA-256 ({digest} != {want})")
    else:
        pinned.write_text(f"{digest}  python.{PYTHON}.nupkg\n")
        say(f"pinned the Python package's SHA-256 in {pinned.name}: {digest}")
    return pkg


def stage_python(pkg: Path) -> Path:
    out = STAGE / "python"
    with zipfile.ZipFile(pkg) as z:
        for info in z.infolist():
            if not info.filename.startswith("tools/") or info.is_dir():
                continue
            rel = info.filename[len("tools/"):]
            if any(rel == d or rel.startswith(d + "/") for d in PY_DROP):
                continue
            target = out / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                shutil.copyfileobj(src, dst)
    (out / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)
    return out


# --------------------------------------------------------------- libraries
def fetch_wheels() -> list[Path]:
    wheels = CACHE / "wheels"
    wheels.mkdir(parents=True, exist_ok=True)
    say("downloading the Windows wheels (PyPI)")
    subprocess.run([sys.executable, "-m", "pip", "download", "--quiet", "--no-deps",
                    "--only-binary=:all:", "--platform", "win_amd64", "--python-version", "3.11",
                    "--implementation", "cp", "--abi", "cp311", "-d", str(wheels),
                    "-r", str(HERE / "requirements.txt")], check=True)
    wanted = {}
    for line in (HERE / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if "==" in line:
            name, ver = line.split("==")
            wanted[name.lower().replace("-", "_")] = ver
    found = []
    for whl in sorted(wheels.glob("*.whl")):
        name, ver = whl.name.split("-")[:2]
        if wanted.get(name.lower().replace("-", "_")) == ver:
            found.append(whl)
    missing = set(wanted) - {w.name.split("-")[0].lower().replace("-", "_") for w in found}
    if missing:
        raise SystemExit(f"wheels missing for: {sorted(missing)}")
    return found


def install_wheels(wheels: list[Path], python: Path) -> None:
    site = python / "Lib" / "site-packages"
    for whl in wheels:
        with zipfile.ZipFile(whl) as z:
            for info in z.infolist():
                if info.is_dir():
                    continue
                parts = info.filename.split("/")
                if parts[0].endswith(".data"):
                    # scripts and headers are not needed; purelib / platlib are
                    if len(parts) > 2 and parts[1] in ("purelib", "platlib"):
                        rel = "/".join(parts[2:])
                    else:
                        continue
                else:
                    rel = info.filename
                target = site / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
    say(f"installed {len(wheels)} libraries")


# --------------------------------------------------------------- the platform
def tracked(prefix: str) -> list[str]:
    out = subprocess.run(["git", "ls-files", "-z", "--", prefix], cwd=ROOT, check=True,
                         capture_output=True).stdout.decode("utf-8")
    return [p for p in out.split("\0") if p]


def stage_app() -> Path:
    import glob
    app = STAGE / "app"
    files = [p for p in tracked("engine")
             if not p.startswith("engine/tests/") and "/__pycache__/" not in p]
    files += tracked("desktop/launcher.py")
    tracked_specs = set(tracked("specs/official"))
    for pattern in SPEC_GLOBS:
        for f in glob.glob(str(ROOT / pattern), recursive=True):
            rel = Path(f).relative_to(ROOT).as_posix()
            if rel in tracked_specs:
                files.append(rel)
    for rel in sorted(set(files)):
        src, dst = ROOT / rel, app / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    say(f"staged {len(set(files))} platform files")
    return app


def compile_all() -> None:
    # byte-code made here starts the app faster on first run; hash-checked,
    # so it never goes stale against its source
    if sys.version_info[:2] != (3, 11):
        say("not Python 3.11 here: byte-code is left for first start")
        return
    for d in (STAGE / "python" / "Lib", STAGE / "app"):
        compileall.compile_dir(str(d), quiet=1, workers=0,
                               invalidation_mode=compileall.py_compile.PycInvalidationMode.UNCHECKED_HASH)


def make_icon() -> Path:
    """The owner's app icon (brand/app-icon.ico, 16-256 px) for the window,
    the shortcuts, the installer and Add/Remove Programs."""
    out = STAGE / "icon.ico"
    shutil.copyfile(ROOT / "brand" / "app-icon.ico", out)
    return out


# ---------------------------------------------------------------- installer
def make_installer(version: str) -> Path:
    makensis = shutil.which("makensis")
    if not makensis:
        raise SystemExit("makensis (NSIS) is not installed: apt install nsis, or nsis.sourceforge.io")
    DIST.mkdir(parents=True, exist_ok=True)
    out = DIST / f"UAD36-Desktop-Setup-{version}.exe"
    if out.exists():
        out.unlink()
    say("making the installer (NSIS, LZMA)")
    subprocess.run([makensis, "-V2", f"-DVERSION={version}", f"-DSTAGE={STAGE}",
                    f"-DOUTFILE={out}", str(HERE / "installer.nsi")], check=True)
    return out


def shelve(installer: Path, version: str) -> None:
    SHELF.mkdir(parents=True, exist_ok=True)
    for old in SHELF.glob("*.part*"):
        old.unlink()
    data = installer.read_bytes()
    parts = []
    for n, start in enumerate(range(0, len(data), PART)):
        chunk = data[start:start + PART]
        name = f"{installer.stem}.part{n:02d}"
        (SHELF / name).write_bytes(chunk)
        parts.append({"file": name, "size": len(chunk), "sha256": hashlib.sha256(chunk).hexdigest()})
    manifest = {"name": installer.name, "version": version, "size": len(data),
                "sha256": hashlib.sha256(data).hexdigest(), "parts": parts,
                "built": time.strftime("%Y-%m-%d"), "python": PYTHON}
    (SHELF / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    say(f"shelved {len(parts)} parts in {SHELF.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--no-shelf", action="store_true", help="do not update downloads/desktop/")
    args = ap.parse_args()
    version = (HERE / "VERSION").read_text().strip()
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)
    python = stage_python(fetch_python())
    install_wheels(fetch_wheels(), python)
    stage_app()
    compile_all()
    make_icon()
    installer = make_installer(version)
    size = installer.stat().st_size
    say(f"{installer.name}: {size / 1e6:.1f} MB, sha256 {sha256(installer)}")
    if not args.no_shelf:
        shelve(installer, version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
