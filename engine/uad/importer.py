"""Bring a UAD 3.6 appraisal in: the MISMO XML and every picture that goes with it.

The case *is* its MISMO document (see ``CLAUDE.md``), so importing is not a
field-by-field copy into a form: the imported document, once normalised,
becomes the case, and the form, the comparable grids, the exhibits, the PDF
and the delivery XML are all drawn from it -- every value lands in the control
that shows it, lists are already on their value, boxes already ticked, every
comparable (four, six, ten) already in its column, and every value stays
editable exactly like one typed in.

What arrives is a *bundle*: an ``.xml`` alone, the B-1 delivery ``.zip``
(XML + Images/), or an XML together with loose image files.  The steps:

1. **open**  find the XML in whatever was sent, and index every image file.
2. **parse**  one parse, huge files allowed, entities off (no network, no XXE).
3. **normalise** (A-1 and the XSD decide, never the file's author):
   * a MISMO document in another namespace or none is moved into the GSE one;
   * each value is put in the form A-1 gives its data point -- "purchase" or
     "Purchase " for Purchase, "Y" for true, "3/4/26" for 2026-03-04,
     "$1,250.00" for 1250 -- and anything that cannot be read is reported,
     not silently changed;
   * elements the GSE subschema does not know are taken out, kept in the
     report with their values, so the document validates;
   * children are put back in XSD order.
4. **pictures**  every IMAGE is given its file: from the bundle (by name,
   case-insensitive, wherever it sits in the zip), from an http(s) URL, from a
   ``data:`` URI, or from base64 content some producers embed inside the IMAGE
   -- decoded, written to Images/, and the IMAGE pointed at it the way B-1
   packages it (``\\Images\\name``).  A picture that cannot be found is
   reported and its box stays, empty, to be filled by hand.  Pictures the
   bundle carries that no IMAGE names are kept with the case, unplaced.
5. **report**  what was imported, what was normalised, what was dropped,
   which pictures were placed / missing, the schema and compliance findings.

Nothing is written to a case until all of this has succeeded (see
``app/api.py`` ``import_appraisal``): a failed import leaves no trace.
"""
from __future__ import annotations

import base64
import binascii
import concurrent.futures
import io
import json
import mimetypes
import re
import urllib.request
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path, PurePosixPath

from lxml import etree

from . import bind, entry, xsd_order

MISMO = bind.MISMO
M = f"{{{MISMO}}}"
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
               ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff",
               ".tiff": "image/tiff", ".webp": "image/webp", ".pdf": "application/pdf"}
MAGIC = ((b"\xff\xd8\xff", ".jpg"), (b"\x89PNG", ".png"), (b"GIF8", ".gif"), (b"BM", ".bmp"),
         (b"II*\x00", ".tif"), (b"MM\x00*", ".tif"), (b"RIFF", ".webp"), (b"%PDF", ".pdf"))
MAX_IMAGE = 15 * 1024 * 1024          # B-1: 60 MB package; one picture well under
FETCH_TIMEOUT = 15


class ImportError_(ValueError):
    """The bundle cannot be imported at all (no XML, not MISMO, unreadable)."""


@dataclass
class Picture:
    name: str                    # file name in Images/
    data: bytes
    location: str                # ImageFileLocationIdentifier as written back
    category: str = ""
    caption: str = ""
    owner: str = ""              # SubjectProperty / SalesComparable / ...
    comparable: int = 0          # column number when it is a comparable's photo
    source: str = ""             # bundle / url / data-uri / embedded


@dataclass
class Report:
    xml_name: str = ""
    property_type: str = ""
    values: int = 0                              # leaf values in the document
    on_report: int = 0                           # of those, fields the report shows
    not_displayed: int = 0                       # A-1 data the report does not print
    comparables: dict = field(default_factory=dict)
    normalised: list = field(default_factory=list)      # (path, from, to)
    invalid: list = field(default_factory=list)          # (path, value, why)
    dropped: list = field(default_factory=list)          # (path, text) not in the subschema
    pictures_placed: list = field(default_factory=list)
    pictures_missing: list = field(default_factory=list)
    pictures_unreferenced: list = field(default_factory=list)
    documents: list = field(default_factory=list)        # PDFs no IMAGE names
    schema_errors: list = field(default_factory=list)
    compliance: dict = field(default_factory=dict)
    seconds: float = 0.0

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        for key in ("normalised", "invalid", "dropped"):
            d[f"{key}_count"] = len(d[key])
            d[key] = d[key][:300]
        return d


# ------------------------------------------------------------------ 1. open
def open_bundle(files: list[tuple[str, bytes]]) -> tuple[str, bytes, dict[str, tuple[str, bytes]]]:
    """(xml name, xml bytes, images by lower-case file name) from what was sent."""
    xmls: list[tuple[str, bytes]] = []
    found: list[tuple[str, str, bytes]] = []
    assets: dict[str, tuple[str, bytes]] = {}

    def take(name: str, data: bytes) -> None:
        base = PurePosixPath(name.replace("\\", "/")).name
        low = base.lower()
        if not base or base.startswith(("._", "~$")) or "__MACOSX" in name:
            return
        if low.endswith(".xml"):
            xmls.append((name.replace("\\", "/"), data))
        elif low.endswith(".zip"):
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if not info.is_dir() and info.file_size <= 200 * 1024 * 1024:
                            # inside a zip of zips, a file's place includes the zip it came in
                            take(f"{name.replace(chr(92), '/')}/{info.filename}", zf.read(info))
            except zipfile.BadZipFile as exc:
                raise ImportError_(f"{base} is not a readable zip: {exc}") from exc
        elif Path(low).suffix in IMAGE_TYPES or _sniff(data):
            found.append((name.replace("\\", "/"), base, data))

    for name, data in files:
        take(name, data)
    if not xmls:
        raise ImportError_("No UAD 3.6 XML file was found in what was imported.")
    # the MISMO appraisal among several XML files: the one with a MESSAGE
    xmls.sort(key=lambda x: (b"<MESSAGE" not in x[1][:4096] and b":MESSAGE" not in x[1][:4096], -len(x[1])))
    chosen = xmls[0][0]
    home = str(PurePosixPath(chosen).parent)
    # a zip of several appraisals: the pictures beside the chosen one
    near = [f for f in found if len(xmls) == 1 or home in ("", ".")
            or f[0].startswith(home + "/")]
    for _path_, base, data in (near or found):
        assets.setdefault(base.lower(), (base, data))
    return PurePosixPath(chosen).name, xmls[0][1], assets


def _sniff(data: bytes) -> str:
    for magic, ext in MAGIC:
        if data[:len(magic)] == magic:
            if ext == ".webp" and data[8:12] != b"WEBP":
                continue
            return ext
    return ""


# ----------------------------------------------------------------- 2. parse
def parse(data: bytes) -> etree._ElementTree:
    parser = etree.XMLParser(huge_tree=True, resolve_entities=False, no_network=True,
                             remove_comments=False, recover=False)
    try:
        root = etree.fromstring(data, parser)
    except etree.XMLSyntaxError as exc:
        raise ImportError_(f"The XML could not be read: {exc}") from exc
    if etree.QName(root).localname != "MESSAGE":
        raise ImportError_(f"This is not a MISMO appraisal (its root is <{etree.QName(root).localname}>, "
                           "a UAD 3.6 file starts with <MESSAGE>).")
    return root.getroottree()


# -------------------------------------------------------------- 3. normalise
@lru_cache(maxsize=1)
def _points() -> dict[str, list[dict]]:
    """A-1 data points by MISMO name (several fields share a name)."""
    data = json.loads((bind.SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]
    out: dict[str, list[dict]] = {}
    for entry_ in data.values():
        for dp in entry_.get("data_points") or []:
            if dp.get("mismo") and not dp.get("attribute"):
                out.setdefault(dp["mismo"], []).append(dp)
    return out


def _point_for(node: etree._Element) -> dict | None:
    """The A-1 data point this element is: its name, then its container path."""
    name = etree.QName(node).localname
    points = _points().get(name)
    if not points:
        return None
    if len(points) == 1:
        return points[0]
    parent = etree.QName(node.getparent()).localname if node.getparent() is not None else ""
    near = [dp for dp in points if bind._tail(dp.get("xpath", ""))[-1:] == [parent]]
    return (near or points)[0]


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def _enum(dp_list: list[dict], value: str) -> str | None:
    """The A-1 value a list answer means ("purchase", "Deed in Lieu", "deed_in_lieu")."""
    options = []
    for dp in dp_list:
        for e in dp.get("enumerations") or []:
            if e.get("value"):
                options.append((e["value"], e.get("display") or ""))
    if not options:
        return None
    values = {v for v, _ in options}
    if value in values:
        return value
    want = _squash(value)
    for v, shown in options:
        if _squash(v) == want or (shown and _squash(shown) == want):
            return v
    return None


def _move_namespace(root: etree._Element, report: Report) -> None:
    """A MISMO file in another MISMO namespace (or none) is read as the GSE one."""
    moved = 0
    for node in root.iter():
        if not isinstance(node.tag, str):
            continue
        q = etree.QName(node)
        if q.namespace == MISMO:
            continue
        if q.namespace in (None, "") or "mismo.org" in (q.namespace or ""):
            node.tag = f"{M}{q.localname}"
            moved += 1
    if moved:
        etree.cleanup_namespaces(root, top_nsmap={None: MISMO})
        report.normalised.append(("(document)", f"{moved} elements in another namespace",
                                  "moved into the UAD 3.6 namespace"))


def _path(node: etree._Element) -> str:
    """A readable address: PROPERTY[2]/SITE/SITE_UTILITIES/SITE_UTILITY[3]/..."""
    parts = []
    cur = node
    while cur is not None and isinstance(cur.tag, str):
        name = etree.QName(cur).localname
        parent = cur.getparent()
        if parent is not None:
            same = [c for c in parent if isinstance(c.tag, str) and etree.QName(c).localname == name]
            if len(same) > 1:
                name += f"[{same.index(cur) + 1}]"
            if name == "PROPERTY" and cur.get("ValuationUseType"):
                name += f"({cur.get('ValuationUseType')})"
        parts.append(name)
        cur = parent
    parts = [p for p in reversed(parts) if not p.startswith(("MESSAGE", "DOCUMENT_SETS", "DOCUMENT_SET",
                                                               "DOCUMENTS", "DEAL_SETS", "DEAL_SET", "DEALS"))]
    return "/".join(parts)[-180:]


def normalise(tree: etree._ElementTree, report: Report) -> None:
    root = tree.getroot()
    _move_namespace(root, report)
    order = xsd_order.load()
    # elements the GSE subschema does not accept where they are
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or node is root:
            continue
        parent = node.getparent()
        if parent is None or etree.QName(parent).localname == "EXTENSION" or \
                any(etree.QName(a).localname == "EXTENSION" for a in parent.iterancestors()):
            continue
        name, pname = etree.QName(node).localname, etree.QName(parent).localname
        if pname == "IMAGE":
            continue                     # embedded picture content: the picture step reads it
        known = order.table.get(pname)
        if known is not None and name not in known and name != "EXTENSION":
            text = " ".join(node.itertext()).strip()
            if not _is_embedded_image(node):
                report.dropped.append((_path(node), text[:200]))
            parent.remove(node)
    # values in A-1's form
    for node in root.iter():
        if not isinstance(node.tag, str) or len(node):
            continue
        raw = node.text or ""
        value = raw.strip()
        if value != raw and value:
            node.text = value
        if not value:
            continue
        dp = _point_for(node)
        if dp is None:
            continue
        kind = (dp.get("format_type") or "").strip()
        fixed = value
        if kind == "Boolean" and value not in ("true", "false"):
            low = value.casefold()
            fixed = ("true" if low in ("t", "y", "yes", "1", "x", "true")
                     else "false" if low in ("f", "n", "no", "0", "false") else None)
        elif kind in ("Amount", "Numeric", "Percent") and not re.match(r"^-?\d+(\.\d+)?$", value):
            try:
                fixed, _unit = entry.normalize({**dp, "format_type": "Numeric" if kind == "Percent" else kind},
                                               value, "")
            except ValueError:
                fixed = None
        elif kind == "Date" and not re.match(r"^\d{4}(-\d{2}(-\d{2}(T[\d:.]+(Z|[+-]\d{2}:\d{2})?)?)?)?$", value):
            try:
                fixed, _unit = entry.normalize(dp, value, "")
            except ValueError:
                fixed = None
        if fixed is None:
            report.invalid.append((_path(node), value, f"not a {kind.lower()} value"))
            continue
        if fixed != value:
            node.text = fixed
            report.normalised.append((_path(node), value, fixed))
    # children back in XSD order (a stable sort keeps repeats in their order)
    for node in root.iter():
        if not isinstance(node.tag, str) or len(node) < 2:
            continue
        rank = order.table.get(etree.QName(node).localname)
        if not rank:
            continue
        kids = list(node)
        ordered = sorted(kids, key=lambda k: rank.get(etree.QName(k).localname, len(rank))
                         if isinstance(k.tag, str) else -1)
        if ordered != kids:
            for k in kids:
                node.remove(k)
            node.extend(ordered)


ENUM_ERROR = re.compile(r"Element '(?:\{[^}]*\})?(\w+)': \[facet 'enumeration'\] The value '([^']*)' "
                        r"is not an element of the set \{([^}]*)\}")


LENGTH_ERROR = re.compile(r"Element '(?:\{[^}]*\})?(\w+)'.*exceeds the allowed maximum length of '(\d+)'")


def repair_enumerations(tree: etree._ElementTree, report: Report) -> None:
    """A list value the schema rejects, matched to the value it meant.

    The XSD holds every value an element may take (A-1 lists only the ones a
    given report field uses), so the schema's own complaint names the set:
    "purchase", "Deed in Lieu" and "deed_in_lieu" all become DeedInLieu /
    Purchase; anything still unmatched is reported and left for the appraiser."""
    from . import schema
    for err in schema.validate(tree):
        long_ = LENGTH_ERROR.search(err.message)
        if long_:
            # kept in full -- an appraiser's words are never cut silently
            for node in (tree.getroot().xpath(err.path) if err.path else []):
                report.invalid.append((_path(node), f"{len(node.text or '')} characters",
                                       f"longer than UAD 3.6 allows ({long_.group(2)}): kept in full, "
                                       "shorten it before delivery"))
            continue
        m = ENUM_ERROR.search(err.message)
        if not m:
            continue
        name, value = m.group(1), m.group(2)
        allowed = [a.strip().strip("'") for a in m.group(3).split(",")]
        want = _squash(value)
        hit = next((a for a in allowed if _squash(a) == want), None)
        if hit is None:
            # A-1 display labels ("Appraisal Management Company")
            for dp in _points().get(name, []):
                for e in dp.get("enumerations") or []:
                    if e.get("display") and _squash(e["display"]) == want and e.get("value") in allowed:
                        hit = e["value"]
        nodes = tree.getroot().xpath(err.path) if err.path else []
        for node in nodes:
            if (node.text or "").strip() != value:
                continue
            if hit is None:
                report.invalid.append((_path(node), value, "not one of the values UAD 3.6 allows"))
            else:
                node.text = hit
                report.normalised.append((_path(node), value, hit))


# ---------------------------------------------------------------- 4. pictures
EMBEDDED = re.compile(r"^[A-Za-z0-9+/=\s]{200,}$")


def _is_embedded_image(node: etree._Element) -> bool:
    return any(EMBEDDED.match((t or "").strip() or "-") for t in node.itertext())


def _decode(text: str) -> bytes | None:
    text = (text or "").strip()
    if text.startswith("data:"):
        text = text.split(",", 1)[1] if "," in text else ""
    try:
        data = base64.b64decode(re.sub(r"\s+", "", text), validate=True)
    except (binascii.Error, ValueError):
        return None
    return data if _sniff(data) else None


def _fetch(url: str) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "UAD36-FormFiller-import/1.0"})
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as r:
            data = r.read(MAX_IMAGE + 1)
    except Exception:
        return None
    return data if data and len(data) <= MAX_IMAGE and _sniff(data) else None


def _owner(image: etree._Element) -> tuple[str, etree._Element | None]:
    for a in image.iterancestors():
        if etree.QName(a).localname == "PROPERTY":
            return a.get("ValuationUseType") or "", a
    return "", None


def pictures(tree: etree._ElementTree, assets: dict[str, tuple[str, bytes]],
             report: Report, *, fetch: bool = True) -> list[Picture]:
    """Give every IMAGE its file.  Returns the pictures to write to Images/."""
    root = tree.getroot()
    used: set[str] = set()
    taken_names: set[str] = set()
    out: list[Picture] = []
    todo_urls: list[tuple[etree._Element, str]] = []
    comp_columns: dict[str, int] = {}
    counts: Counter = Counter()
    for prop in root.iter(f"{M}PROPERTY"):
        use = prop.get("ValuationUseType") or ""
        counts[use] += 1
        comp_columns[prop.getroottree().getpath(prop)] = counts[use]

    def unique(name: str) -> str:
        stem, suffix = Path(name).stem or "image", Path(name).suffix or ".jpg"
        name = re.sub(r"[^\w.\- ]", "_", f"{stem}{suffix}")[:50]      # B-1: 50 characters
        base, n = name, 1
        while name.lower() in taken_names:
            name = f"{Path(base).stem[:44]}-{n}{Path(base).suffix}"
            n += 1
        taken_names.add(name.lower())
        return name

    def place(image, name: str, data: bytes, source: str) -> None:
        ext = Path(name).suffix.lower() or _sniff(data)
        if ext not in IMAGE_TYPES:
            ext = _sniff(data) or ".jpg"
            name = f"{Path(name).stem}{ext}"
        final = unique(name)
        loc_node = image.find(f"{M}ImageFileLocationIdentifier")
        if loc_node is None:
            from . import edit
            loc_node = edit.insert_ordered(image, "ImageFileLocationIdentifier")
        # B-1 packages an image as ``\\Images\name`` -- two leading
        # backslashes.  Writing one turned every picture of an imported file
        # into a path the delivery package does not use, so a report that
        # came in from another vendor went back out with all 42 of its image
        # locations rewritten.  One helper builds this, in delivery.
        from . import delivery
        loc_node.text = delivery.location_of(final)
        mime = image.find(f"{M}MIMETypeIdentifier")
        if mime is None:
            from . import edit
            mime = edit.insert_ordered(image, "MIMETypeIdentifier")
        mime.text = IMAGE_TYPES.get(Path(final).suffix.lower(), "image/jpeg")
        use, prop = _owner(image)
        column = comp_columns.get(prop.getroottree().getpath(prop), 0) if prop is not None and use != "SubjectProperty" else 0
        out.append(Picture(final, data, loc_node.text, image.findtext(f"{M}ImageCategoryType") or "",
                           image.findtext(f"{M}ImageCaptionCommentDescription") or "", use, column, source))
        report.pictures_placed.append({"name": final, "category": out[-1].category, "owner": use,
                                       "comparable": column, "source": source})

    for image in root.iter(f"{M}IMAGE"):
        loc = (image.findtext(f"{M}ImageFileLocationIdentifier") or "").strip()
        # 1. content embedded in the IMAGE (removed from the document either way)
        embedded = None
        for child in list(image):
            if isinstance(child.tag, str) and etree.QName(child).localname not in xsd_order.load().children("IMAGE"):
                embedded = embedded or _decode("".join(child.itertext()))
                image.remove(child)
        if loc.startswith("data:"):
            embedded = embedded or _decode(loc)
        stem = re.split(r"[\\/]", loc.rstrip("\\/"))[-1] if loc and not loc.startswith("data:") else ""
        if embedded is not None:
            place(image, stem or f"{image.findtext(f'{M}ImageCategoryType') or 'Image'}{_sniff(embedded)}",
                  embedded, "embedded")
            continue
        # 2. a file in the bundle, by name
        if stem and stem.lower() in assets:
            name, data = assets[stem.lower()]
            used.add(stem.lower())
            place(image, name, data, "bundle")
            continue
        # 3. a URL
        if re.match(r"^https?://", loc, re.I):
            todo_urls.append((image, loc))
            continue
        report.pictures_missing.append({"location": loc, "category": image.findtext(f"{M}ImageCategoryType") or "",
                                        "reason": "not in the bundle" if loc else "no file named"})

    if todo_urls and fetch:
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            got = list(pool.map(lambda iu: _fetch(iu[1]), todo_urls))
        for (image, url), data in zip(todo_urls, got):
            if data is None:
                report.pictures_missing.append({"location": url, "reason": "could not be downloaded"})
                continue
            name = PurePosixPath(url.split("?")[0]).name or "image"
            place(image, name, data, "url")
    elif todo_urls:
        report.pictures_missing.extend({"location": u, "reason": "downloads disabled"} for _i, u in todo_urls)

    # the previous report's PDF, named by FOREIGN_OBJECT/ObjectURL (B-1 p72):
    # the report is drawn again from the data, so that file is not a picture
    for url in root.iter(f"{M}ObjectURL"):
        low = re.split(r"[\\/]", (url.text or "").strip())[-1].lower()
        if low in assets:
            used.add(low)
            report.normalised.append(("ObjectURL", assets[low][0], "previous report PDF: redrawn from the data"))
    for low, (name, _data) in assets.items():
        if low in used:
            continue
        if low.endswith(".pdf"):
            report.documents.append(name)        # the previous report or an addendum PDF
        else:
            report.pictures_unreferenced.append(name)
    return out


# ------------------------------------------------------------------ 5. count
def count(tree: etree._ElementTree, report: Report) -> None:
    """How much of the document the report shows, and the comparables it has."""
    from app import autofill                      # the field each element is (report order)
    root = tree.getroot()
    for node in root.iter():
        if not isinstance(node.tag, str) or len(node) or not (node.text or "").strip():
            continue
        report.values += 1
        try:
            fid = autofill._field_of(node)
        except Exception:                          # noqa: BLE001
            fid = ""
        if fid:
            report.on_report += 1
        else:
            report.not_displayed += 1
    uses = Counter(p.get("ValuationUseType") or "" for p in root.iter(f"{M}PROPERTY"))
    report.comparables = {k: v for k, v in uses.items() if k and k != "SubjectProperty"}


# ------------------------------------------------------- the portable file
# One XML that carries its pictures.  The GSE subschema gives an IMAGE only a
# file location, but every MISMO container ends in EXTENSION/OTHER, which the
# XSD opens to any element of another namespace (processContents="lax").  So
# the picture travels inside its own IMAGE and the file still validates
# against the UAD 3.6 subschema; a receiver that does not know the extension
# simply ignores it.  UCDP delivery is still the B-1 zip (XML + Images/),
# built from the same document with the extensions left out.
PORTABLE = "urn:uad36:portable:1"
P = f"{{{PORTABLE}}}"


def _portable(root: etree._Element, local: str) -> list[etree._Element]:
    """Every portable-extension element of this name.  Files exported before
    2026-10-04 used an older ``urn:<name>:uad36:portable:1`` namespace; any
    namespace of that form is read, so those files still import."""
    return [n for n in root.iter() if isinstance(n.tag, str)
            and etree.QName(n).localname == local
            and (etree.QName(n).namespace or "").endswith("uad36:portable:1")]


def embed(tree: etree._ElementTree, images: dict[str, Path], state: dict | None = None) -> dict:
    """Put every picture an IMAGE names inside that IMAGE; editor state at the top."""
    import hashlib
    root = tree.getroot()
    from . import edit
    done, missing = 0, []
    for image in root.iter(f"{M}IMAGE"):
        loc = (image.findtext(f"{M}ImageFileLocationIdentifier") or "").strip()
        name = re.split(r"[\\/]", loc.rstrip("\\/"))[-1] if loc else ""
        path = images.get(name)
        if path is None or not Path(path).is_file():
            if name:
                missing.append(name)
            continue
        data = Path(path).read_bytes()
        ext = image.find(f"{M}EXTENSION")
        if ext is None:
            ext = edit.insert_ordered(image, "EXTENSION")
        other = ext.find(f"{M}OTHER")
        if other is None:
            other = etree.SubElement(ext, f"{M}OTHER")
        for old in [n for n in _portable(other, "EmbeddedFile") if n.getparent() is other]:
            other.remove(old)
        node = etree.SubElement(other, f"{P}EmbeddedFile", nsmap={"uad": PORTABLE})
        node.set("FileName", name)
        node.set("MIMEType", IMAGE_TYPES.get(Path(name).suffix.lower(), "application/octet-stream"))
        node.set("SHA256", hashlib.sha256(data).hexdigest())
        node.text = base64.b64encode(data).decode("ascii")
        done += 1
    if state:
        ext = root.find(f"{M}EXTENSION")
        if ext is None:
            ext = edit.insert_ordered(root, "EXTENSION")
        other = ext.find(f"{M}OTHER")
        if other is None:
            other = etree.SubElement(ext, f"{M}OTHER")
        node = etree.SubElement(other, f"{P}EditorState", nsmap={"uad": PORTABLE})
        node.text = json.dumps(state)
    return {"embedded": done, "missing": missing}


def take_embedded(tree: etree._ElementTree, report: Report) -> tuple[dict[str, bytes], dict]:
    """The pictures and editor state a portable file carries, removed from it."""
    import hashlib
    root = tree.getroot()
    files: dict[str, bytes] = {}
    for node in _portable(root, "EmbeddedFile"):
        name = node.get("FileName") or "image"
        try:
            data = base64.b64decode(re.sub(r"\s+", "", node.text or ""), validate=True)
        except (binascii.Error, ValueError):
            report.invalid.append((name, "embedded picture", "its base64 content is damaged"))
            data = b""
        if data and node.get("SHA256") and hashlib.sha256(data).hexdigest() != node.get("SHA256"):
            report.invalid.append((name, "embedded picture", "its checksum does not match: damaged in transit"))
            data = b""
        if data:
            files[name.lower()] = (name, data)
        _prune(node)
    state = {}
    for node in _portable(root, "EditorState"):
        try:
            state = json.loads(node.text or "{}")
        except ValueError:
            state = {}
        _prune(node)
    return files, state


def _prune(node: etree._Element) -> None:
    """Remove an element and any EXTENSION / OTHER it leaves empty."""
    parent = node.getparent()
    parent.remove(node)
    while parent is not None and etree.QName(parent).localname in ("OTHER", "EXTENSION") and not len(parent):
        up = parent.getparent()
        up.remove(parent)
        parent = up
