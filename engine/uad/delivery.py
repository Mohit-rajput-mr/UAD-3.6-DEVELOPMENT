"""The UCDP delivery package, as Appendix B-1 defines it.

B-1 "Creation of .zip File" (pp 69-73) and "Images" (pp 56-61):

* one ZIP per appraisal, not over 60 MB, holding one UAD 3.6 XML file, one
  appraisal report PDF and a folder named ``Images`` -- nothing else;
* the PDF is not embedded in the XML: FOREIGN_OBJECT/ObjectURL names it,
  relative to the root of the ZIP (``\\\\name.pdf``);
* images are not embedded either: each is an IMAGE container whose
  ImageFileLocationIdentifier points into ``\\\\Images\\\\``, every image in the
  folder is referenced at least once, and file names are unique;
* the allowed image types are A-1's MIMETypeIdentifier enumeration.

The case document stays as the appraiser edits it.  This module works on a
copy: it writes the IMAGE containers for the photographs the appraiser added,
points the document's own image boxes at their replacements, names the PDF and
the software that produced the report, and then says what the ZIP holds and
everything wrong with it.  Nothing here is typed from memory -- the paths, the
limits and the allowed types are read from the A-1 extract.
"""
from __future__ import annotations

import json
import mimetypes
import re
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from . import bind, edit
from .report import comparables, form

SPEC = Path(__file__).resolve().parents[1] / "spec"
CONFIG = Path(__file__).resolve().parents[1] / "config"
M = f"{{{bind.MISMO}}}"

PDF_NAME = "appraisal.pdf"
XML_NAME = "mismo.xml"
IMAGES = "Images"
# B-1 p69: "Create one .zip file for each appraisal (not to exceed 60 mb)"
MAX_BYTES = 60 * 1024 * 1024

FATAL = "Fatal"
WARNING = "Warning"


@dataclass
class Fault:
    severity: str
    code: str
    message: str
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@dataclass
class Package:
    tree: Any                                   # the XML that ships
    images: dict[str, Path] = field(default_factory=dict)   # name in Images/ -> file
    faults: list[Fault] = field(default_factory=list)
    total_image_bytes: int = 0

    @property
    def fatal(self) -> list[Fault]:
        return [f for f in self.faults if f.severity == FATAL]


# --------------------------------------------------------------- from A-1
@lru_cache(maxsize=1)
def _rows() -> list[dict]:
    return json.loads((SPEC / "delivery_spec.json").read_text(encoding="utf-8"))


def _enum_key(row: dict) -> str:
    return next(k for k in row if k.startswith("Supported Data Point Enumerations"))


def _row(name: str, xpath_part: str) -> dict:
    for r in _rows():
        if r["MISMO Data Point Name"] == name and xpath_part in r["MISMO xPath"]:
            return r
    raise KeyError(f"A-1 has no {name} under {xpath_part}")


@lru_cache(maxsize=1)
def image_mime_types() -> frozenset[str]:
    """A-1 MIMETypeIdentifier for images (the same list on every IMAGE row)."""
    r = _row("MIMETypeIdentifier", "INSPECTIONS/INSPECTION/IMAGES/IMAGE")
    return frozenset(v.strip() for v in r[_enum_key(r)].split("|") if v.strip())


def _length(name: str, xpath_part: str) -> int:
    details = _row(name, xpath_part)["UAD Data Point Format Details"]
    m = re.search(r"(\d+)", details)
    return int(m.group(1)) if m else 0


@lru_cache(maxsize=1)
def location_max() -> int:
    """A-1: ImageFileLocationIdentifier is 'String 50'."""
    return _length("ImageFileLocationIdentifier", "INSPECTIONS/INSPECTION/IMAGES/IMAGE")


@lru_cache(maxsize=1)
def caption_max() -> int:
    return _length("ImageCaptionCommentDescription", "INSPECTIONS/INSPECTION/IMAGES/IMAGE")


def _segments(name: str, xpath_part: str) -> list[str]:
    path = _row(name, xpath_part)["MISMO xPath"]
    return [s for s in path.strip("/").split("/") if s and s != "MESSAGE"]


# ---------------------------------------------------------------- vendor
def vendor() -> dict[str, str]:
    """This software's identity, from ``engine/config/vendor.json``.

    A-1 makes ValuationSoftwareVendorName and ValuationSoftwareProductName
    required.  They name whoever produced the report, so they are the
    publisher's to set -- never a sample's ("Nowhere Technologies").
    """
    path = CONFIG / "vendor.json"
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {k: str(v).strip() for k, v in data.items() if not k.startswith("_")}


def stamp_software(root) -> list[str]:
    """Write this software's identity into VALUATION_SOFTWARE_SYSTEM.

    The element is the producer's, not the appraiser's: A-1 requires all four
    children and the schema rejects the container without them.  A new case is
    stamped at creation so a blank report is not invalid for something no
    appraiser could ever answer.  Returns the names it could not set."""
    who = vendor()
    missing = []
    pairs = (("ValuationSoftwareProductIdentifier",
              who.get("product_identifier") or who.get("product_name", "")),
             ("ValuationSoftwareProductName", who.get("product_name", "")),
             ("ValuationSoftwareProductVersionIdentifier", who.get("product_version", "")),
             ("ValuationSoftwareVendorName", who.get("vendor_name", "")))
    for name, value in pairs:
        if value:
            _set_leaf(root, name, "VALUATION_SOFTWARE_SYSTEM", value)
        else:
            missing.append(name)
    return missing


def _existing(root, segments: list[str]) -> tuple[etree._Element, list[str]]:
    """The deepest container on this path that already exists, on whichever
    branch holds it, and the segments still to create below it.

    Walking first-child-first is wrong wherever a container repeats: Condo1
    has several SERVICEs and only one carries the VALUATION.
    """
    for depth in range(len(segments), 0, -1):
        found = root.find("/".join(f"{M}{s}" for s in segments[:depth]))
        if found is not None:
            return found, segments[depth:]
    return root, segments


def _set_leaf(root, name: str, xpath_part: str, value: str) -> None:
    base, rest = _existing(root, _segments(name, xpath_part))
    parent, _ = edit.ensure_path(base, rest)
    leaf = parent.find(f"{M}{name}")
    if leaf is None:
        leaf = edit.insert_ordered(parent, name)
    leaf.text = value


# ---------------------------------------------------------------- images
def mime_for(filename: str) -> str:
    guess = mimetypes.guess_type(filename)[0] or ""
    return {"image/jpg": "image/jpeg", "image/pjpeg": "image/jpeg"}.get(guess, guess)


def exif(path: Path) -> dict[str, str]:
    """When, where and at what altitude a photograph was taken, if it says.

    A-1 makes ImageDatetime and AltitudeElevationLinearMeasure conditional on
    the image existing; they are read from the file and never invented.
    """
    out: dict[str, str] = {}
    try:
        from PIL import Image
        with Image.open(path) as im:
            data = im.getexif()
            taken = data.get_ifd(0x8769).get(36867) or data.get(306)   # DateTimeOriginal / DateTime
            if taken:
                stamp = datetime.strptime(str(taken).strip()[:19], "%Y:%m:%d %H:%M:%S")
                out["ImageDatetime"] = stamp.strftime("%Y-%m-%dT%H:%M:%SZ")
            gps = data.get_ifd(0x8825)

            def degrees(values, ref) -> float:
                d, m, sec = (float(v) for v in values)
                value = d + m / 60 + sec / 3600
                return -value if ref in ("S", "W") else value

            if gps and 2 in gps and 4 in gps:
                out["LatitudeIdentifier"] = f"{degrees(gps[2], gps.get(1)):.6f}"
                out["LongitudeIdentifier"] = f"{degrees(gps[4], gps.get(3)):.6f}"
            if gps and 6 in gps:
                metres = float(gps[6])
                if gps.get(5) == 1:
                    metres = -metres
                out["AltitudeElevationLinearMeasure"] = str(int(round(metres * 3.28084)))
    except Exception:
        return out
    return out


def _category_for(section: str, caption: str) -> str:
    """The ImageCategoryType for an image filed under a section.

    A caption that is the display name of one of the section's own categories
    ("Property Access (Street Scene)") is that category; anything else is the
    section's Exhibit category.  Both come from the A-1 enumerations.
    """
    cats = form.image_categories()
    for value, (sec, shown) in cats.items():
        if sec == section and shown and shown.lower() == caption.strip().lower():
            return value
    for value, (sec, shown) in cats.items():
        if sec == section and value.endswith("Exhibit") and not shown:
            return value
    return ""


def _inspection(prop) -> etree._Element:
    parent, _ = edit.ensure_path(prop, ["INSPECTIONS", "INSPECTION"])
    return parent


def _add_image(prop, category: str, location: str, mime: str,
               caption: str = "", meta: dict[str, str] | None = None) -> etree._Element:
    images, _ = edit.ensure_path(_inspection(prop), ["IMAGES"])
    # The XSD makes IMAGES require an IMAGE, so creating the container leaves an
    # empty one behind; fill that rather than delivering it beside the real one.
    image = next((x for x in images.findall(f"{M}IMAGE") if not len(x)), None)
    if image is None:
        image = edit.insert_ordered(images, "IMAGE")
    values = {"ImageCategoryType": category, "ImageFileLocationIdentifier": location,
              "MIMETypeIdentifier": mime, "ImageCaptionCommentDescription": caption,
              **(meta or {})}
    for name, value in values.items():
        if value:
            edit.insert_ordered(image, name).text = value
    return image


def _drop_category(prop, categories: set[str]) -> None:
    for image in list(prop.iterfind(f"{M}INSPECTIONS/{M}INSPECTION/{M}IMAGES/{M}IMAGE")):
        if image.findtext(f"{M}ImageCategoryType", "").strip() in categories:
            image.getparent().remove(image)


# ------------------------------------------------- what the file carries unseen
# A-1 marks forty-four data points "Does Not Display".  They have no field on
# the page, so a model built from the printed report never created them and the
# delivered XML simply did not carry them -- thirteen of those are Required.
# Most are statements *about* the report that the report itself already
# answers: whether the sales comparison approach was developed is not something
# to ask the appraiser again, it is whether there are sales comparables.  So
# each is derived from the document, with A-1's own definition as the rule.
def _has(root, *names: str) -> bool:
    """Does the document carry a value for any of these data points?"""
    for name in names:
        for node in root.iter(f"{M}{name}"):
            if (node.text or "").strip():
                return True
    return False


def _has_role(root, role: str) -> bool:
    return any(p.get("ValuationUseType") == role for p in root.iter(f"{M}PROPERTY"))


def _derived_indicators(root) -> dict[str, str]:
    """The Boolean statements A-1 wants in the file, read off the report.

    Each key is quoted from A-1's own definition, so the rule can be checked
    against the sheet rather than taken on trust.
    """
    def yes(value: bool) -> str:
        return "true" if value else "false"

    return {
        # "the sales comparison approach will be included in the appraisal report"
        "SalesComparisonApproachIndicator": yes(
            _has_role(root, "SalesComparable")
            or _has(root, "ValueIndicatedBySalesComparisonAmount")),
        # "the cost approach will be included"
        "CostApproachIndicator": yes(_has(
            root, "ValueIndicatedByCostApproachAmount",
            "ImprovementEstimatedTotalCostAmount", "ReplacementOrReproductionCostAmount")),
        # "the income approach will be included"
        "IncomeApproachIndicator": yes(_has(
            root, "ValueIndicatedByIncomeApproachAmount", "GrossRentMultiplierFactor")
            or _has_role(root, "GrossRentMultiplierComparable")),
        # "a rent schedule will be included"
        "RentScheduleIndicator": yes(
            _has_role(root, "RentalComparable") or _has(root, "UnitIncludedInRentScheduleIndicator")),
        # "the appraisal has been prepared for a federal agency"
        "GovernmentAgencyAppraisalIndicator": yes(_has(
            root, "AgencyAppraiserIdentifierType", "AgencyCaseIdentifier")),
        # "additional intended users have been identified"
        "ValuationAdditionalIntendedUserIndicator": yes(_has(root, "ValuationIntendedUserDescription")),
        # "additional scope of work (beyond the minimum scope) has been identified"
        "ValuationAdditionalScopeOfWorkIndicator": yes(_has(root, "ValuationAdditionalScopeOfWorkDescription")),
        # "a reconsideration of value has been requested"
        "ReconsiderationOfValueIndicator": yes(_has(root, "ConsiderationRequestedIndicator")),
        # "one or more additional certifications have been identified by the appraiser"
        "AppraiserAdditionalCertificationIndicator": yes(_has(
            root, "ValuationAdditionalCertificationIncludedByType",
            "AppraiserAdditionalCertificationDescription")),
        # "one or more additional client requested value conditions are present"
        "AdditionalClientRequestedConditionsIndicator": yes(_has(
            root, "AdditionalClientRequestedConditionDescription")),
    }


def _delivery_only(root, out: "Package") -> None:
    """Fill every non-displaying data point the document can answer for itself.

    A value the appraiser already gave is never overwritten: if the file says
    the cost approach was developed, that statement stands even when the cost
    figures are still blank.
    """
    from . import uadmap

    for name, value in _derived_indicators(root).items():
        entry = uadmap.point(name)
        if not entry:                       # the map is generated; do not guess
            continue
        if _has(root, name):
            continue
        _set_leaf(root, name, entry["container"], value)


def location_of(name: str) -> str:
    return f"\\\\{IMAGES}\\{name}"


def name_of(location: str) -> str:
    return re.split(r"[\\/]", (location or "").strip().rstrip("\\/"))[-1]


def build(tree, media: Iterable[Any], media_dir: Path, *,
          fills: dict[str, str] | None = None,
          template_names: Iterable[str] = (), kind: str = "sales") -> Package:
    """The XML that ships and the images that go with it, with every fault.

    ``media`` are the case's stored images (objects with media_id, category,
    filename, caption, section, comparable, provenance); ``fills`` maps an
    image location already in the document to the media_id that replaces it;
    ``template_names`` are file names that came with a D-1 template and must
    not ship.
    """
    root = deepcopy(tree.getroot() if hasattr(tree, "getroot") else tree)
    # xsi:schemaLocation (carried in from a D-1 sample) is not permitted by the
    # UAD schema, and TOTAL's importer cannot resolve the xsi prefix: it puts
    # the root's attributes into every element's XPath and silently skips each
    # value it cannot resolve (knowledge/errors/CATALOG.md E-028).
    from .model import DROPPED_ATTRIBUTES
    for el in root.iter():
        if isinstance(el.tag, str):
            for name in [a for a in el.attrib if a in DROPPED_ATTRIBUTES]:
                del el.attrib[name]
    etree.cleanup_namespaces(root)
    out = Package(etree.ElementTree(root))
    media = list(media)
    by_id = {m.media_id: m for m in media}
    fills = dict(fills or {})
    template_names = set(template_names)

    # --- the software that produced the report (A-1: R)
    who = vendor()
    for key, name in (("vendor_name", "ValuationSoftwareVendorName"),
                      ("product_name", "ValuationSoftwareProductName")):
        if who.get(key):
            _set_leaf(root, name, "VALUATION_SOFTWARE_SYSTEM", who[key])
        else:
            out.faults.append(Fault(FATAL, "VENDOR-UNSET",
                                    f"{name} is required (A-1) and names the software "
                                    "that produced the report.",
                                    "Set it in engine/config/vendor.json."))
    # An identifier for the product may reasonably be the product's own name;
    # a version may not -- writing the product name where the file says which build
    # produced it is worse than leaving it out, so it is reported instead.
    identifier = who.get("product_identifier") or who.get("product_name", "")
    if identifier:
        _set_leaf(root, "ValuationSoftwareProductIdentifier",
                  "VALUATION_SOFTWARE_SYSTEM", identifier)
    if who.get("product_version"):
        _set_leaf(root, "ValuationSoftwareProductVersionIdentifier",
                  "VALUATION_SOFTWARE_SYSTEM", who["product_version"])
    else:
        out.faults.append(Fault(WARNING, "VENDOR-VERSION",
                                "ValuationSoftwareProductVersionIdentifier is required "
                                "(A-1) and names the build that produced the file.",
                                "Set product_version in engine/config/vendor.json."))

    # --- what A-1 requires in the file but never prints
    _delivery_only(root, out)

    # --- the PDF, by reference (B-1 p72)
    _set_leaf(root, "ObjectURL", "FOREIGN_OBJECT", f"\\\\{PDF_NAME}")
    _set_leaf(root, "MIMETypeIdentifier", "VIEW_FILES/VIEW_FILE/FOREIGN_OBJECT", "application/pdf")

    subject = bind.subject(root)
    files: dict[str, Path] = {}

    def ship(item) -> str:
        path = media_dir / item.filename
        files[item.filename] = path
        return location_of(item.filename)

    # --- the photographs the appraiser supplied
    for item in media:
        if getattr(item, "provenance", "") == "template":
            continue
        path = media_dir / item.filename
        if not path.is_file():
            out.faults.append(Fault(FATAL, "IMAGE-MISSING",
                                    "An image attached to the report is not on disk.",
                                    item.filename))
            continue
        meta = exif(path)
        caption = (item.caption or "").strip()
        if item.media_id in fills.values():
            continue                                    # handled with the fills below
        if item.category == "subject" and subject is not None:
            # B-1 Scenario 3: one file behind DwellingFront (8.000.1) and
            # PropertyPhoto (Summary 1.000.1, grid thumbnail).  It is the first
            # dwelling's front: a second building's front and a "Dwelling
            # Front" exhibit are other DwellingFront images and stay (E-163),
            # and the new one takes the old one's place, since the n-th
            # DwellingFront is the n-th dwelling's.
            _drop_category(subject, {"PropertyPhoto"})
            first = next((i for i in subject.iterfind(f"{M}INSPECTIONS/{M}INSPECTION/{M}IMAGES/{M}IMAGE")
                          if i.findtext(f"{M}ImageCategoryType", "").strip() == "DwellingFront"), None)
            loc = ship(item)
            _add_image(subject, "PropertyPhoto", loc, mime_for(item.filename), meta=meta)
            front = _add_image(subject, "DwellingFront", loc, mime_for(item.filename), meta=meta)
            if first is not None:
                first.addprevious(front)
                first.getparent().remove(first)
            continue
        if item.category == "comparable" and int(item.comparable or 0):
            _sheet, role, _t = comparables.SHEETS[kind]
            props = comparables.properties(root, role)
            n = int(item.comparable)
            if not 1 <= n <= len(props):
                out.faults.append(Fault(FATAL, "IMAGE-ORPHAN",
                                        f"A photo is filed against comparable #{n}, which "
                                        "does not exist.", item.filename))
                continue
            _drop_category(props[n - 1], {"PropertyPhoto"})
            _add_image(props[n - 1], "PropertyPhoto", ship(item), mime_for(item.filename),
                       meta=meta)
            continue
        section = bind.SECTION_NAME.get(int(item.section or 0), "")
        fixed = form.media_category({"category": item.category, "caption": caption})
        if not section and not fixed:
            continue                                    # not placed on the report
        if section and not fixed and not form.section_prints(root, section):
            # its section is not in the report (B-1: no sales contract, no
            # mitigation feature, an approach not developed), so the PDF has
            # no place for it and neither has the file (T-1057)
            out.faults.append(Fault(WARNING, "IMAGE-SECTION-OFF",
                                    f"An exhibit filed under {section} is not delivered: "
                                    "the section is not in this report.", item.filename))
            continue
        category = fixed or _category_for(section, caption)
        if not category:
            out.faults.append(Fault(FATAL, "IMAGE-CATEGORY",
                                    f"No A-1 ImageCategoryType files an image under {section}.",
                                    item.filename))
            continue
        shown = form.image_categories().get(category, ("", ""))[1]
        if category == "SalesComparableMap":
            shown = "Sales Comparison Map"               # printed by its H1, not a caption
        _add_image(subject, category, ship(item), mime_for(item.filename),
                   caption="" if shown else caption[:caption_max()], meta=meta)

    # --- the document's own image boxes, given the appraiser's photograph
    for location, media_id in fills.items():
        item = by_id.get(media_id)
        if item is None:
            continue
        loc = ship(item)
        meta = exif(media_dir / item.filename)
        for image in root.iter(f"{M}IMAGE"):
            if image.findtext(f"{M}ImageFileLocationIdentifier", "").strip() != location.strip():
                continue
            image.find(f"{M}ImageFileLocationIdentifier").text = loc
            mime = image.find(f"{M}MIMETypeIdentifier")
            if mime is None:
                mime = edit.insert_ordered(image, "MIMETypeIdentifier")
            mime.text = mime_for(item.filename)
            for name, value in meta.items():
                node = image.find(f"{M}{name}")
                if node is None:
                    node = edit.insert_ordered(image, name)
                node.text = value

    # --- what the XML now references, and whether each can ship
    referenced: dict[str, str] = {}
    for image in root.iter(f"{M}IMAGE"):
        loc = image.findtext(f"{M}ImageFileLocationIdentifier", "").strip()
        if loc:
            referenced.setdefault(name_of(loc), loc)
    for name, loc in sorted(referenced.items()):
        if name in files:
            continue
        if name in template_names:
            out.faults.append(Fault(FATAL, "SAMPLE-IMAGE",
                                    "The report still references a picture that came with "
                                    "the GSE sample. Replace it with your own photograph "
                                    "or remove that image.", name))
        else:
            out.faults.append(Fault(FATAL, "IMAGE-NOT-SUPPLIED",
                                    "The report references an image that has not been "
                                    "supplied (B-1: every IMAGE points at a file in Images).",
                                    name))

    # --- B-1 / A-1 limits
    seen: set[str] = set()
    total = 0
    allowed = image_mime_types()
    for name, path in files.items():
        if name.lower() in seen:
            out.faults.append(Fault(FATAL, "IMAGE-NAME-DUPLICATE",
                                    "Each image must have a unique file name (B-1).", name))
        seen.add(name.lower())
        if mime_for(name) not in allowed:
            out.faults.append(Fault(FATAL, "IMAGE-TYPE",
                                    "A-1 MIMETypeIdentifier does not allow this image type.",
                                    f"{name} ({mime_for(name) or 'unknown'})"))
        if len(location_of(name)) > location_max():
            out.faults.append(Fault(FATAL, "IMAGE-NAME-LENGTH",
                                    f"ImageFileLocationIdentifier is at most {location_max()} "
                                    "characters (A-1).", location_of(name)))
        if path.is_file():
            total += path.stat().st_size
    out.images = files
    out.total_image_bytes = total
    return out


def check_size(zip_bytes: int) -> list[Fault]:
    if zip_bytes > MAX_BYTES:
        return [Fault(FATAL, "PACKAGE-SIZE",
                      "The ZIP is over the 60 MB B-1 allows.",
                      f"{zip_bytes / 1024 / 1024:.1f} MB")]
    return []
