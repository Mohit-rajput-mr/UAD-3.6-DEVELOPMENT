r"""Package this folder for another device.

    python setup/export_for_device.py                       # -> Documents\UAD36_for_device_<date>.zip
    python setup/export_for_device.py --out D:\share\uad36.zip
    python setup/export_for_device.py --include-case-material --include-git

By default the package carries everything a device needs to install the MOD
and run cases -- the MOD, the engine, the official specifications, the
knowledge base, the appraiser profiles, the worked example -- and leaves out:

* `.git` (641 MB of history; the private GitHub repository holds it)
* caches and build junk (`__pycache__`, `.pytest_cache`, tile caches)
* `total-bridge/tools/.cache` -- a la mode's own code, never redistributed
  (knowledge/README.md); the receiving device re-reads its own TOTAL
* **real client case material** -- borrower and owner names, loan and order
  numbers, delivered reports, inspection photos of real homes.  Appraisal
  files are confidential to the client; send them only if the receiving
  appraiser is entitled to them, with --include-case-material.

Everything it leaves out is listed in EXPORT_MANIFEST.txt inside the zip.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALWAYS_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".ruff_cache", "node_modules", ".venv", "venv"}
ALWAYS_SKIP_PATHS = {"total-bridge/tools/.cache", "_work/tilecache", "_work/test-temp-20260916c"}

#: real assignments: client names, loan/order numbers, delivered reports, photos of real homes
CASE_MATERIAL = {
    "_work/cases", "_work/cases-test", "_work/rockland", "_work/bathbeach", "_work/euclid", "_work/w57",
    "_work/ozone", "_work/shore", "_work/woodycrest", "_work/bedford", "_work/manhattan", "_work/reference",
    "_work/sf_guide", "_work/Images", "_work/dossier", "_work/total_backup", "_work/verify", "_work/compare",
    "_work/packtest", "_work/test-temp-20260916a", "_work/test-temp-20260916b", "_work/test-temp-20260916c",
    "_work/filled_report.pdf", "_work/deliverable.zip", "_work/contact_sheet.png",
    "_work/r0.html", "_work/r2.html", "_work/cloudflared.exe", "MATERIALS",
    "condocase.txt", "newcase.txt", "demo_case.txt",
    "profiles/documents",              # licence + E&O images
    "engine/assets/fonts",             # Adobe Myriad Pro: licensed for embedding, not redistribution
    "setup/redact_terms.txt",          # the list of client identifiers itself
}


def rel(p: Path) -> str:
    return p.relative_to(ROOT).as_posix()


TEXT = {".md", ".txt", ".json", ".py", ".csv"}


def redactions() -> list[tuple[str, str]]:
    """setup/redact_terms.txt: client identifiers replaced in shipped text files."""
    f = ROOT / "setup" / "redact_terms.txt"
    out = []
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            if line.strip() and not line.startswith("#") and "=>" in line:
                a, b = (s.strip() for s in line.split("=>", 1))
                out.append((a, b))
    return sorted(out, key=lambda t: -len(t[0]))      # longest first


def main():
    ap = argparse.ArgumentParser()
    # the user's Documents: the folder's parent is often a drive root, which
    # needs administrator rights to write to
    ap.add_argument("--out", default=str(Path.home() / "Documents" / f"UAD36_for_device_{dt.date.today():%Y%m%d}.zip"))
    ap.add_argument("--include-case-material", action="store_true")
    ap.add_argument("--include-git", action="store_true")
    args = ap.parse_args()

    skip = set(ALWAYS_SKIP_PATHS)
    if not args.include_case_material:
        skip |= CASE_MATERIAL
    if not args.include_git:
        skip.add(".git")

    out = Path(args.out)
    files, skipped, total = [], [], 0
    for dirpath, dirnames, filenames in os.walk(ROOT):
        d = Path(dirpath)
        keep = []
        for name in dirnames:
            r = rel(d / name)
            if name in ALWAYS_SKIP_DIRS or r in skip:
                if r in skip:
                    skipped.append(r + "/")
                continue
            keep.append(name)
        dirnames[:] = keep
        for name in filenames:
            p = d / name
            r = rel(p)
            if r in skip or p.suffix in (".pyc", ".pyo") or p.resolve() == out.resolve():
                if r in skip:
                    skipped.append(r)
                continue
            files.append(p)
            total += p.stat().st_size

    manifest = [f"UAD 3.6 development folder, exported {dt.datetime.now():%Y-%m-%d %H:%M} for another device.",
                "Open START_HERE.md first.", "",
                f"files: {len(files)}   uncompressed: {total / 1e6:.0f} MB", "",
                "Left out (see setup/export_for_device.py for why):"] + [f"  {s}" for s in sorted(skipped)]
    print(f"packing {len(files)} files, {total / 1e6:.0f} MB -> {out}")
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as z:
        z.writestr("UAD 3.6 DEVELOPMENT/EXPORT_MANIFEST.txt", "\n".join(manifest))
        terms = [] if args.include_case_material else redactions()
        redacted = 0
        for i, p in enumerate(files, 1):
            arc = "UAD 3.6 DEVELOPMENT/" + rel(p)
            if terms and p.suffix.lower() in TEXT and p.stat().st_size < 20_000_000 \
                    and rel(p) != "setup/redact_terms.txt":
                text = p.read_text(encoding="utf-8", errors="surrogateescape")
                new = text
                for a, b in terms:
                    new = new.replace(a, b)
                if new != text:
                    redacted += 1
                    z.writestr(arc, new.encode("utf-8", errors="surrogateescape"))
                    continue
            z.write(p, arc)
            if i % 2000 == 0:
                print(f"   {i}/{len(files)}")
    print(f"done: {out}  ({out.stat().st_size / 1e6:.0f} MB); client identifiers redacted in {redacted} file(s)")
    print("left out:", *sorted(skipped), sep="\n  ")


if __name__ == "__main__":
    main()
