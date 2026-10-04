"""Prepare photographs for the deliverable.

UAD names image files by what they depict, and the XML references each one by
that name, so the manifest drives both.  Phone photos also carry their rotation
in EXIF rather than in the pixels: left as-is they appear sideways in the PDF,
so every image is physically rotated before it is written out.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

MAX_EDGE = 1600           # plenty for a full-page exhibit, keeps the ZIP sane
JPEG_QUALITY = 85

MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


@dataclass
class Exhibit:
    """One prepared image, ready to write into the deliverable."""

    source: Path
    filename: str            # e.g. "UNIT_1_4.jpg"
    category: str
    caption: str

    @property
    def mime_type(self) -> str:
        return MIME_TYPES.get(Path(self.filename).suffix.lower(), "image/jpeg")

    @property
    def xml_path(self) -> str:
        r"""How the XML refers to it: \\Images\NAME.jpg"""
        return f"\\\\Images\\{self.filename}"

    def as_dict(self) -> dict[str, Any]:
        return {
            "filename": self.filename,
            "category": self.category,
            "caption": self.caption,
            "source": str(self.source),
        }


def load_manifest(config_dir: Path, project_root: Path) -> list[Exhibit]:
    """Read the photo manifest and number each image within its own group."""
    path = Path(config_dir) / "images.json"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        manifest = json.load(fh)

    root = Path(project_root) / manifest.get("_root", "")
    counters: dict[str, int] = {}
    exhibits: list[Exhibit] = []

    for entry in manifest.get("photos", []):
        source = root / entry["file"]
        if not source.exists():
            continue
        name = entry["name"]
        counters[name] = counters.get(name, 0) + 1

        suffix = ".png" if source.suffix.lower() == ".png" else ".jpg"
        exhibits.append(
            Exhibit(
                source=source,
                filename=f"{name}_{counters[name]}{suffix}",
                category=entry["category"],
                caption=entry.get("caption", ""),
            )
        )
    return exhibits


def write(exhibits: list[Exhibit], destination: Path) -> list[Path]:
    """Normalise orientation and size, then write each image out."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    for exhibit in exhibits:
        target = destination / exhibit.filename
        with Image.open(exhibit.source) as image:
            # Apply the EXIF orientation to the pixels themselves.
            image = ImageOps.exif_transpose(image)
            image.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)

            if target.suffix.lower() == ".jpg":
                image.convert("RGB").save(target, "JPEG", quality=JPEG_QUALITY, optimize=True)
            else:
                image.save(target, "PNG", optimize=True)
        written.append(target)
    return written


def image_nodes(exhibits: list[Exhibit]) -> list[dict]:
    """IMAGE elements for the MISMO model."""
    return [
        {
            "ImageCaptionCommentDescription": exhibit.caption,
            "ImageCategoryType": exhibit.category,
            "ImageFileLocationIdentifier": exhibit.xml_path,
            "MIMETypeIdentifier": exhibit.mime_type,
        }
        for exhibit in exhibits
    ]
