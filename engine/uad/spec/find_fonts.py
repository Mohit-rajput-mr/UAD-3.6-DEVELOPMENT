"""Search this machine's licensed Adobe installs for Myriad Pro faces.

The URAR is set in Myriad Pro.  Adobe licenses it with its applications, so the
only legitimate source on a given machine is that machine's own Adobe install
or Adobe Fonts cache -- never a download site.  The CoreSync cache stores its
faces without extensions, so candidates there are identified by reading the
font's internal name table rather than by filename.
"""
from __future__ import annotations

import os
from pathlib import Path

from fontTools.ttLib import TTFont

HOME = Path.home()
ROOTS = [
    Path(r"C:\Program Files\Adobe"),
    Path(r"C:\Program Files (x86)\Adobe"),
    Path(r"C:\Program Files\Common Files\Adobe"),
    Path(r"C:\Program Files (x86)\Common Files\Adobe"),
    Path(r"C:\Windows\Fonts"),
    HOME / "AppData/Roaming/Adobe/CoreSync/plugins/livetype",
    HOME / "AppData/Local/Adobe",
]
WANT = "myriad"


def name(font: TTFont, nid: int) -> str:
    for rec in font["name"].names:
        if rec.nameID == nid:
            try:
                return rec.toUnicode()
            except Exception:
                continue
    return ""


def identify(path: Path) -> dict | None:
    try:
        font = TTFont(str(path), fontNumber=0, lazy=True)
    except Exception:
        return None
    try:
        full = name(font, 4) or name(font, 6)
        family = name(font, 1)
        if WANT not in (full + family).lower():
            return None
        os2 = font["OS/2"] if "OS/2" in font else None
        return {
            "path": str(path),
            "full": full,
            "family": family,
            "postscript": name(font, 6),
            "version": name(font, 5),
            "manufacturer": name(font, 8),
            "fsType": getattr(os2, "fsType", None),
            "weight": getattr(os2, "usWeightClass", None),
            "size": path.stat().st_size,
        }
    finally:
        font.close()


def sweep() -> list[dict]:
    found, seen = [], set()
    for root in ROOTS:
        if not root.exists():
            continue
        for dirpath, _dirs, files in os.walk(root):
            for fn in files:
                p = Path(dirpath) / fn
                ext = p.suffix.lower()
                # Named font files, plus the extensionless CoreSync cache.
                if ext not in (".otf", ".ttf", ".ttc", ".pfb", "") :
                    continue
                if ext == "" and p.stat().st_size < 20_000:
                    continue
                if ext in (".otf", ".ttf", ".ttc") and WANT not in fn.lower():
                    # still worth opening -- CIDFont names can differ
                    if "myriad" not in fn.lower():
                        continue
                info = identify(p)
                if info and info["postscript"] not in seen:
                    seen.add(info["postscript"])
                    found.append(info)
    return found


def main() -> None:
    rows = sweep()
    print(f"{len(rows)} distinct Myriad face(s) on this machine\n")
    for r in sorted(rows, key=lambda r: (r["weight"] or 0, r["postscript"])):
        print(f"  {r['postscript']:<28} w{r['weight']:<4} fsType={r['fsType']} "
              f"{r['version'][:24]:<26} {r['manufacturer'][:28]}")
        print(f"      {r['path']}")
    have = {r["postscript"] for r in rows}
    for want in ("MyriadPro-Black", "MyriadPro-BlackIt"):
        print(f"\n  {want}: {'FOUND' if want in have else 'NOT PRESENT'}")


if __name__ == "__main__":
    main()
