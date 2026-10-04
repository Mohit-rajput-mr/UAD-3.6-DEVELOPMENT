"""The photographs a UAD 3.6 file carries.

A 3.6 file comes in two flavours and both have to work:

* a **portable** file embeds each photograph in the document as base64, so the
  one file carries the whole job;
* a **delivery** file only names them, and the pictures travel beside it in an
  ``Images`` folder -- which is what goes to UCDP.

Either way the document says what each picture *is*: its UAD category, its
caption, and which property it belongs to.  That is what decides where a
picture goes in the form, so it is read from the document rather than guessed
from a filename.
"""
from __future__ import annotations

import base64
import hashlib
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from lxml import etree

MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
BACKSLASH = chr(92)

EXTENSION = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
             "image/gif": ".gif", "image/tiff": ".tif", "image/bmp": ".bmp"}


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _text(node, name: str) -> str:
    """The text of a descendant with this local name, in any namespace.

    Namespace-blind on purpose.  A picture embedded in a portable file sits in
    the writing vendor's own extension namespace -- ours is
    ``urn:uad36:portable:1`` -- and every vendor picks a different one.
    Matching the namespace as well as the name finds pictures in our own files
    and silently finds none in anybody else's.
    """
    for found in node.iter():
        if not isinstance(found.tag, str):
            continue
        if _local(found.tag) == name and (found.text or "").strip():
            return found.text.strip()
    return ""


def _basename(location: str) -> str:
    """The file's own name, from a path written with either slash.

    Deliberately not pathlib.  The document writes a doubled leading backslash,
    and Windows reads that as a UNC share root whose name is empty -- so every
    picture would come back unnamed.
    """
    cleaned = location.replace(BACKSLASH, "/")
    return cleaned.rstrip("/").rsplit("/", 1)[-1].strip()


@dataclass
class Photo:
    category: str            # UAD ImageCategoryType
    caption: str
    location: str            # what the document calls the file
    mime: str
    data: bytes | None       # present when the file embeds it
    source: Path | None      # present when it sits beside the document
    owner: str               # ValuationUseType of the PROPERTY it sits under
    ordinal: int             # which comparable, when it belongs to one

    @property
    def name(self) -> str:
        return (_basename(self.location)
                or f"{self.category or 'image'}{EXTENSION.get(self.mime, '.jpg')}")

    @property
    def available(self) -> bool:
        return bool(self.data) or bool(self.source and self.source.exists())

    def materialise(self, folder: Path) -> Path | None:
        """Put the picture on disk so it can be handed to a file input."""
        if self.source and self.source.exists():
            return self.source
        if not self.data:
            return None
        folder.mkdir(parents=True, exist_ok=True)
        # The document's own name, made unique: two sections can each carry a
        # picture called PHOTO_1.jpg and they are not the same picture.
        digest = hashlib.sha1(self.data).hexdigest()[:8]
        path = folder / f"{digest}-{self.name}"
        if not path.exists():
            path.write_bytes(self.data)
        return path


def photos(xml_path: str | Path) -> list[Photo]:
    """Every photograph the file carries or names."""
    path = Path(xml_path)
    root = etree.parse(str(path)).getroot()
    beside = path.parent / "Images"

    found = []
    for image in root.iter(f"{{{MISMO_NS}}}IMAGE"):
        location = _text(image, "ImageFileLocationIdentifier")
        mime = _text(image, "MIMETypeIdentifier") or "image/jpeg"
        encoded = _text(image, "EmbeddedFile")

        data = None
        if encoded:
            try:
                data = base64.b64decode(re.sub(r"\s+", "", encoded))
            except Exception:
                data = None

        source = None
        if data is None and location:
            candidate = beside / _basename(location)
            if candidate.exists():
                source = candidate

        # Which property is this picture about?  One under a comparable belongs
        # in that comparable's column, not the subject's.
        owner, ordinal = "", 0
        for ancestor in image.iterancestors():
            if _local(ancestor.tag) != "PROPERTY":
                continue
            owner = ancestor.get("ValuationUseType") or ""
            for node in ancestor.iter(f"{{{MISMO_NS}}}PropertyOrdinalNumber"):
                try:
                    ordinal = int((node.text or "0").strip())
                except ValueError:
                    ordinal = 0
                break
            # Not every writer fills PropertyOrdinalNumber.  Where it is absent
            # the document's own order settles it -- which is better than
            # treating the comparable as unnumbered and filing its photograph
            # in the subject's column, where it silently replaces the subject.
            if owner and not ordinal:
                same = [pr for pr in root.iter(f"{{{MISMO_NS}}}PROPERTY")
                        if pr.get("ValuationUseType") == owner]
                if ancestor in same:
                    ordinal = same.index(ancestor) + 1
            break

        found.append(Photo(
            category=_text(image, "ImageCategoryType"),
            caption=_text(image, "ImageCaptionCommentDescription"),
            location=location, mime=mime, data=data, source=source,
            owner=owner, ordinal=ordinal))
    return found


def staging(name: str = "uad36-bridge") -> Path:
    return Path(tempfile.gettempdir()) / name


def summarise(found: list[Photo]) -> str:
    embedded = sum(1 for p in found if p.data)
    beside = sum(1 for p in found if p.source)
    missing = len(found) - embedded - beside
    by_category: dict[str, int] = {}
    for p in found:
        key = p.category or "(uncategorised)"
        by_category[key] = by_category.get(key, 0) + 1
    lines = [f"{len(found)} photograph(s): {embedded} embedded, "
             f"{beside} alongside the file, {missing} not available"]
    for category, n in sorted(by_category.items(), key=lambda kv: -kv[1]):
        lines.append(f"    {category:<38} {n}")
    return "\n".join(lines)
