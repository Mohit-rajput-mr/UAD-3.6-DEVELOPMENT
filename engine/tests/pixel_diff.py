"""Pixel diff of one report page against the GSE sample.

    python engine/tests/pixel_diff.py <template-key> <page> [dpi] [x0 y0 x1 y1]

Writes ``_work/form/<key>_diff_p<page>.png``: ink only in ours shows red, ink
only in the GSE page shows blue, ink in both shows black.  Prints the share of
ink pixels that differ -- 0.0% is identical.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pymupdf
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

from uad import templates  # noqa: E402
from uad.spec.measure_geometry import report_start  # noqa: E402


def raster(page, dpi: int, clip=None) -> np.ndarray:
    pix = page.get_pixmap(dpi=dpi, clip=clip, colorspace=pymupdf.csGRAY)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)


def main(key: str, n: int, dpi: int = 150, clip=None) -> float:
    tpl = templates.get(key)
    ours = pymupdf.open(ROOT / "_work" / "form" / f"{key}.pdf")[n - 1]
    gdoc = pymupdf.open(tpl.pdf)
    gse = gdoc[report_start(gdoc) + n - 1]
    rect = pymupdf.Rect(*clip) if clip else None
    a = raster(ours, dpi, rect).astype(int)
    b = raster(gse, dpi, rect).astype(int)
    h, w = min(a.shape[0], b.shape[0]), min(a.shape[1], b.shape[1])
    a, b = a[:h, :w], b[:h, :w]
    ink_a, ink_b = a < 200, b < 200
    out = np.full((h, w, 3), 255, dtype=np.uint8)
    both = ink_a & ink_b
    out[both] = (0, 0, 0)
    out[ink_a & ~ink_b] = (230, 0, 0)
    out[ink_b & ~ink_a] = (0, 90, 255)
    name = f"{key}_diff_p{n}" + ("_clip" if clip else "") + ".png"
    Image.fromarray(out).save(ROOT / "_work" / "form" / name)
    union = (ink_a | ink_b).sum()
    diff = (ink_a ^ ink_b).sum()
    # grey-level difference catches weight changes that stay inside the ink
    tone = np.abs(a - b)[ink_a | ink_b].mean() if union else 0.0
    share = 100.0 * diff / union if union else 0.0
    print(f"{key} p{n}: {share:.2f}% of ink differs, mean tone diff {tone:.1f} -> {name}")
    return share


if __name__ == "__main__":
    args = sys.argv[1:]
    key, n = args[0], int(args[1])
    dpi = int(args[2]) if len(args) > 2 else 150
    clip = [float(x) for x in args[3:7]] if len(args) >= 7 else None
    main(key, n, dpi, clip)
