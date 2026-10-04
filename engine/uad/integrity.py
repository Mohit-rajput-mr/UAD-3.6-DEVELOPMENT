"""What the deliverable says against what the case says.

The compliance engine reads the MISMO document and the renderer draws from the
same document, so in principle they cannot disagree.  In practice they can:
an image is filed against a comparable that was deleted, a photograph the GSEs
supplied to illustrate a sample is still attached, the archive picks up an
editor file that is nobody's business outside this machine.  None of that is a
compliance rule -- H-1 has nothing to say about a ZIP -- so it is checked here,
against the package that is actually about to be handed over.

Three questions, in the order they are worth asking:

``assets``      is everything in this report the appraiser's own work?
``consistency`` do the XML and the rendered report tell the same story --
                the address, the comparables and their numbering, the figures
                and dates, and who each photograph belongs to?
``package``     does the archive contain the deliverable and nothing else?

A Fatal finding here blocks the signature exactly as a Fatal compliance finding
does, because a package that contradicts itself is not one a lender can use.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable

from .report import comparables

FATAL = "Fatal"
WARNING = "Warning"

ASSETS = "assets"
CONSISTENCY = "consistency"
PACKAGE = "package"

# What belongs in the archive, and nothing else.  Anything not matching one of
# these is either working state or something that leaked in.
# B-1 p69: one XML, one PDF and the Images folder.
ALLOWED = ("appraisal.pdf", "mismo.xml")
ALLOWED_PREFIX = ("Images/",)

# Files that mean something went out that should have stayed here.
STRAY = re.compile(
    r"(^|/)(\.|~|__pycache__|Thumbs\.db|desktop\.ini)"
    r"|\.(tmp|temp|bak|orig|swp|log|py|pyc|db|db-wal|db-shm)$"
    r"|(^|/)editor\.json$", re.I)


@dataclass
class Finding:
    check: str
    severity: str
    code: str
    message: str
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _text(node) -> str:
    return " ".join((node.text or "").split()) if node is not None else ""


def _digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


# --------------------------------------------------------------------- assets
def check_assets(media: Iterable[Any]) -> list[Finding]:
    """Nothing the GSEs supplied to illustrate the form may ship as somebody's
    appraisal."""
    out = []
    borrowed = [m for m in media if getattr(m, "provenance", "") == "template"]
    for item in borrowed:
        out.append(Finding(
            ASSETS, FATAL, "SAMPLE-ASSET",
            "This report still carries an image that came from the GSEs' "
            "sample case, not from this appraisal.",
            f"{item.filename} -- remove it, or replace it with your own photograph"))
    return out


# ---------------------------------------------------------------- consistency
def check_consistency(tree, media: Iterable[Any], html: str = "") -> list[Finding]:
    """The document and the drawn report, compared where they must agree."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    out: list[Finding] = []

    props = comparables.properties(root, "SalesComparable")
    labels = [comparables.label_of(p) for p in props]

    # Every comparable is numbered once, from one, in order.
    numbers = []
    for prop in props:
        node = comparables.ordinal_node(prop)
        numbers.append(_text(node))
    if numbers != [str(i) for i in range(1, len(props) + 1)]:
        out.append(Finding(
            CONSISTENCY, FATAL, "COMP-NUMBERING",
            "The comparables are not numbered 1..n in the order the report "
            "prints them.",
            f"found {numbers or 'none'}"))

    # A photograph must belong to a comparable that still exists.
    known = set(labels)
    for item in media:
        key = getattr(item, "comp_key", "")
        number = getattr(item, "comparable", 0) or 0
        if key and key not in known:
            out.append(Finding(
                CONSISTENCY, FATAL, "ORPHAN-PHOTO",
                "An image is filed against a comparable that is no longer in "
                "this report.",
                f"{item.filename} -> {key}"))
        elif number and number > len(props):
            out.append(Finding(
                CONSISTENCY, FATAL, "ORPHAN-PHOTO",
                "An image is filed against a comparable number this report "
                "does not have.",
                f"{item.filename} -> comparable #{number} of {len(props)}"))
        elif key and number and labels[number - 1] != key:
            out.append(Finding(
                CONSISTENCY, FATAL, "PHOTO-MISNUMBERED",
                "An image's comparable number does not match the comparable "
                "it belongs to.",
                f"{item.filename}: #{number} is {labels[number - 1]}, not {key}"))

    if not html:
        return out

    # The figures that identify the report: if the drawn page disagrees with
    # the document, one of them is wrong and neither can be trusted.
    drawn = re.sub(r"<[^>]+>", " ", html)
    drawn = " ".join(drawn.split())

    address = root.find(f".//{{{_ns(root)}}}AddressLineText")
    if address is not None and _text(address):
        line = _text(address)
        if line not in drawn:
            out.append(Finding(
                CONSISTENCY, FATAL, "ADDRESS-MISMATCH",
                "The subject's address in the document does not appear in the "
                "report that would be delivered.",
                line))

    value = root.find(f".//{{{_ns(root)}}}OpinionOfValueAmount")
    if value is not None and _digits(_text(value)):
        raw = _digits(_text(value))
        shown = {_digits(m) for m in re.findall(r"\$[\d,]+", drawn)}
        if raw not in shown:
            out.append(Finding(
                CONSISTENCY, FATAL, "VALUE-MISMATCH",
                "The opinion of value in the document does not appear in the "
                "report that would be delivered.",
                f"{raw} is not among the figures printed"))
    return out


def _ns(root) -> str:
    from . import bind
    return bind.MISMO


# ------------------------------------------------------------------- package
def check_package(names: Iterable[str], media: Iterable[Any]) -> list[Finding]:
    """The archive holds the deliverable and nothing else."""
    out: list[Finding] = []
    listed = list(names)

    for name in listed:
        if STRAY.search(name):
            out.append(Finding(
                PACKAGE, FATAL, "STRAY-FILE",
                "The archive contains a file that is not part of the "
                "deliverable.", name))
            continue
        if name in ALLOWED or name.startswith(ALLOWED_PREFIX):
            continue
        out.append(Finding(
            PACKAGE, WARNING, "UNEXPECTED-FILE",
            "The archive contains a file the deliverable does not define.",
            name))

    for required in ("appraisal.pdf", "mismo.xml"):
        if required not in listed:
            out.append(Finding(
                PACKAGE, FATAL, "MISSING-FILE",
                "The archive is missing part of the deliverable.", required))

    # Every image in the archive is one the case knows about, and every image
    # the case knows about is in the archive.
    packed = {n[len("Images/"):] for n in listed if n.startswith("Images/")}
    known = {m.filename for m in media}
    for extra in sorted(packed - known):
        out.append(Finding(
            PACKAGE, FATAL, "UNKNOWN-IMAGE",
            "The archive carries an image this report does not reference.",
            f"Images/{extra}"))
    for missing in sorted(known - packed):
        out.append(Finding(
            PACKAGE, WARNING, "IMAGE-NOT-PACKED",
            "An image this report references is not in the archive.",
            f"Images/{missing}"))
    return out


# ----------------------------------------------------------------------- all
def check(tree, media: Iterable[Any], *, html: str = "",
          names: Iterable[str] | None = None) -> list[Finding]:
    media = list(media)
    out = check_assets(media) + check_consistency(tree, media, html)
    if names is not None:
        out += check_package(names, media)
    return out


def counts(findings: Iterable[Finding]) -> dict[str, int]:
    found = list(findings)
    return {"fatal": sum(1 for f in found if f.severity == FATAL),
            "warning": sum(1 for f in found if f.severity == WARNING),
            "total": len(found)}
