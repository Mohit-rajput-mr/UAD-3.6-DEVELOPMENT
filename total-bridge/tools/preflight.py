"""Check a portable UAD 3.6 package against the TOTAL import profile, before TOTAL.

Whoever generates the package -- the platform, an AI, another program -- runs
this and fixes every error before the file goes near WinTOTAL.  Each finding
names its profile rule (knowledge/total/IMPORT_PROFILE.md) and CATALOG entry,
where in the file it is, and what to change.  Nothing here repairs the file.

    python tools/preflight.py PACKAGE.xml [...]        exit 1 when any error
    python tools/preflight.py --json out.json PACKAGE.xml

Severity: error (TOTAL will lose or change something, or the value moves),
warning (TOTAL's form or delivery will differ from the file), info (the Import
Module handles it on the way in).  Validated against the twelve D-1 samples
(knowledge/total/preflight/): a check that faults a published sample is either
a rule the sample itself breaks -- stated per check -- or a broken check.

Checks that need what TOTAL validates beyond UAD (P12, P13) are learned from
measured round trips, not typed here; see `templates/` and the e2e results.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

XL = "{http://www.w3.org/1999/xlink}"
XSI = "{http://www.w3.org/2001/XMLSchema-instance}"
AMOUNT = re.compile(r"^-?\d+(\.\d+)?$")


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _kids(e, name):
    return [c for c in e if _local(c.tag) == name]


def _text(e, name) -> str:
    for c in e.iter():
        if _local(c.tag) == name and (c.text or "").strip():
            return c.text.strip()
    return ""


def _where(e) -> str:
    parts, node = [], e
    while node is not None and isinstance(node.tag, str):
        name = _local(node.tag)
        if name == "PROPERTY":
            role = node.get("ValuationUseType") or "Property"
            street = _text(node.find("{*}ADDRESS"), "AddressLineText") if node.find("{*}ADDRESS") is not None else ""
            parts.append(f"{role}({street})" if street and role != "SubjectProperty" else role)
            break
        parts.append(name)
        node = node.getparent()
    return "/".join(reversed(parts[:4]))


class Findings(list):
    def add(self, severity, rule, catalog, where, message, fix):
        self.append({"severity": severity, "rule": rule, "catalog": catalog, "where": where,
                     "message": message, "fix": fix})


# ------------------------------------------------------------------ checks
def check_schema_location(root, out: Findings):
    """P1: TOTAL's importer cannot resolve xsi: and skips values beneath it."""
    for e in root.iter():
        if isinstance(e.tag, str) and any(k.startswith(XSI) for k in e.attrib):
            out.add("info", "P1", "E-028", _where(e), "xsi: attribute present (TOTAL skips values under it)",
                    "remove xsi:schemaLocation -- the Import Module strips it on the way in")


def check_links(root, out: Findings):
    """P2: every xlink:from / xlink:to names a label that exists."""
    labels = {e.get(XL + "label") for e in root.iter() if isinstance(e.tag, str) and e.get(XL + "label")}
    for e in root.iter():
        if not isinstance(e.tag, str):
            continue
        for attr in ("from", "to"):
            v = e.get(XL + attr)
            if v and v not in labels:
                out.add("error", "P2", "E-003", _where(e), f"xlink:{attr}='{v}' names no element in the file",
                        "remove the relationship, or add the element it points at (a leftover of a blanked "
                        "sample makes TOTAL build a signature block or role that does not exist)")


def check_empty(root, out: Findings):
    """P3: containers holding no value at all become empty rows in TOTAL."""
    for e in root.iter():
        if not isinstance(e.tag, str) or len(e) == 0:
            continue
        name = _local(e.tag)
        if name in ("EXTENSION", "OTHER"):
            continue
        has_value = any(isinstance(d.tag, str) and len(d) == 0 and (d.text or "").strip() for d in e.iter())
        has_attr = any(k != XL + "label" for d in e.iter() if isinstance(d.tag, str) for k in d.attrib)
        if not has_value and not has_attr:
            out.add("warning", "P3", "E-004/E-023", _where(e), f"{name} holds no value",
                    "drop the empty container (TOTAL creates an empty row for it)")


def check_adjustments(root, out: Findings):
    """P3 typeless rows; value integrity: rows sum to the net, adjusted = a price + net (E-038)."""
    for prop in root.iter("{*}PROPERTY"):
        role = prop.get("ValuationUseType") or ""
        comp = prop.find("{*}COMPARABLE")
        if comp is None:
            continue
        total, rows = 0.0, 0
        for adj in comp.iter("{*}COMPARABLE_ADJUSTMENT"):
            kind, amount = _text(adj, "ComparableAdjustmentType"), _text(adj, "ComparableAdjustmentAmount")
            if role == "SubjectProperty":
                # the subject describes custom comparison rows without an
                # amount (SF1 does) -- amounts belong to comparables only
                continue
            # a row that describes the comparable without adjusting it is fine
            # (SF1: "Below Grade Exterior Access: Walk Out", no amount -- equal
            # to the subject, E-017); a row with no type, or a type and nothing
            # else, is the leftover TOTAL mis-assigns the next amount to (E-021)
            described = any(_local(c.tag) not in ("ComparableAdjustmentType", "ComparableAdjustmentAmount")
                            and len(c) == 0 and (c.text or "").strip() for c in adj.iter())
            if not kind or (not amount and not described):
                out.add("error", "P3", "E-021", _where(adj),
                        "adjustment row without a type" if not kind else f"{kind} row with neither amount nor description",
                        "drop the row, or give it ComparableAdjustmentType plus an amount or its description")
                continue
            if not amount:
                continue
            if AMOUNT.match(amount):
                total += float(amount)
                rows += 1
        detail = comp.find("{*}COMPARABLE_DETAIL")
        if detail is None or role != "SalesComparable":
            continue
        net = _text(detail, "SalePriceNetTotalAdjustmentAmount")
        if net and AMOUNT.match(net) and rows and abs(float(net) - total) > 0.5:
            out.add("error", "P23", "E-038", _where(detail),
                    f"net adjustment {net} but the {rows} adjustment rows sum to {total:g}",
                    "TOTAL recomputes the net from the rows: make the net the sum of the rows "
                    "(or correct the rows) -- otherwise the adjusted price moves in TOTAL")
        adjusted = _text(detail, "AdjustedSalesPriceAmount")
        if adjusted and net and AMOUNT.match(adjusted) and AMOUNT.match(net):
            prices = {float(e.text) for e in prop.iter()
                      if _local(e.tag) in ("OwnershipTransferTransactionAmount", "FinalListPriceAmount",
                                           "SalesContractAmount") and AMOUNT.match((e.text or "").strip())}
            if prices and not any(abs(p + float(net) - float(adjusted)) <= 0.5 for p in prices):
                out.add("error", "P23", "E-038", _where(detail),
                        f"adjusted price {adjusted} is no price of this comparable plus the net {net} "
                        f"(prices: {', '.join(f'{p:g}' for p in sorted(prices))})",
                        "adjusted sales price = the sale (or list) price + the net adjustment")


def check_utilities(root, out: Findings):
    """P4: every SITE_UTILITY with type and ownership; no repeated row.

    Two rows of one type are legitimate when they differ (SF3/SF4: public
    electricity *and* non-public solar); the same type, ownership and source
    twice is the duplicate an engine write made (E-024)."""
    for prop in root.iter("{*}PROPERTY"):
        seen = Counter()
        for u in prop.iter("{*}SITE_UTILITY"):
            kind = _text(u, "UtilityType")
            own = _text(u, "SiteUtilityOwnershipType")
            if not kind or not own:
                out.add("error", "P4", "E-004", _where(u), f"utility without {'type' if not kind else 'ownership'}",
                        "each SITE_UTILITY has UtilityType and SiteUtilityOwnershipType "
                        "(TOTAL reads a missing ownership as private and makes an 'Other' row)")
            if kind:
                source = (_text(u, "ElectricitySourceType") or _text(u, "WaterSourceType")
                          or _text(u, "SewerSystemType") or _text(u, "GasSourceType"))
                seen[(kind, own, source)] += 1
        for (kind, own, source), n in seen.items():
            if n > 1:
                out.add("error", "P4", "E-024", _where(prop),
                        f"{n} identical SITE_UTILITY rows ({kind}, {own or 'no ownership'}, {source or 'no source'})",
                        "one row per distinct utility")


def check_grm_sales(root, out: Findings):
    """P8: a GRM comparable's price and date in one SALES_HISTORY."""
    for prop in root.iter("{*}PROPERTY"):
        if prop.get("ValuationUseType") != "GrossRentMultiplierComparable":
            continue
        hist = list(prop.iter("{*}SALES_HISTORY"))
        amount_only = [h for h in hist if _text(h, "OwnershipTransferTransactionAmount") and not _text(h, "OwnershipTransferDate")]
        date_only = [h for h in hist if _text(h, "OwnershipTransferDate") and not _text(h, "OwnershipTransferTransactionAmount")]
        if amount_only and date_only:
            out.add("error", "P8", "E-015", _where(prop), "sale price and sale date in separate SALES_HISTORY records",
                    "one SALES_HISTORY holding both OwnershipTransferTransactionAmount and OwnershipTransferDate")


def _picture_bytes(image, beside: Path) -> bytes | None:
    for e in image.iter():
        if _local(e.tag) == "EmbeddedFile" and (e.text or "").strip():
            try:
                return base64.b64decode(re.sub(r"\s+", "", e.text))
            except Exception:
                return None
    loc = _text(image, "ImageFileLocationIdentifier").replace("\\", "/").rsplit("/", 1)[-1]
    f = beside / loc if loc else None
    return f.read_bytes() if f and f.exists() else None


def check_pictures(root, out: Findings, path: Path):
    """Every picture has its file; P22: the subject photo is building 1's front
    photo, one front photo per building (E-039)."""
    beside = path.parent / "Images"
    subject = next((p for p in root.iter("{*}PROPERTY") if p.get("ValuationUseType") == "SubjectProperty"), None)
    for image in root.iter("{*}IMAGE"):
        if not _text(image, "ImageFileLocationIdentifier"):
            out.add("error", "P11", "E-019", _where(image), "picture without ImageFileLocationIdentifier",
                    "name the picture's file (\\\\Images\\\\<name>)")
        elif _picture_bytes(image, beside) is None:
            out.add("error", "P11", "E-019", _where(image),
                    f"picture {_text(image, 'ImageFileLocationIdentifier')} is neither embedded nor beside the file",
                    "embed it (portable) or put it in Images\\ next to the file")
    # P27: TOTAL files a defect's picture as an exhibit of the building or
    # unit, and its field validation then requires a description ("Exterior
    # exhibit description is required when an exterior exhibit category is not
    # provided or the category is Apparent Defects ...").  The picture's own
    # caption is that description; build it from the defect record (component,
    # location, what was seen), never invent it.  The official 2-4 unit sample
    # breaks this (its roof-defect pictures carry no caption): a TOTAL rule, not
    # a UAD one.
    for defect in root.iter("{*}DEFECT"):
        for image in defect.iter("{*}IMAGE"):
            if not _text(image, "ImageCaptionCommentDescription"):
                out.add("error", "P27", "E-044", _where(image),
                        f"defect picture {_text(image, 'ImageFileLocationIdentifier')} has no caption: "
                        "TOTAL's field validation requires the exhibit description",
                        "caption it from its defect record (component and what was observed)")
    if subject is None:
        return
    photos = [i for i in subject.iter("{*}IMAGE") if _text(i, "ImageCategoryType") == "PropertyPhoto"]
    fronts = [i for i in subject.iter("{*}IMAGE") if _text(i, "ImageCategoryType") == "DwellingFront"]
    buildings = [imp for imp in subject.iter("{*}IMPROVEMENT")
                 if (_text(imp, "ImprovementType") or "Dwelling") == "Dwelling" and imp.find(".//{*}STRUCTURE") is not None]
    if photos and fronts:
        a, b = _picture_bytes(photos[0], beside), _picture_bytes(fronts[0], beside)
        if a is not None and b is not None and hashlib.sha256(a).digest() != hashlib.sha256(b).digest():
            out.add("warning", "P22", "E-039", _where(photos[0]),
                    f"subject photo {_text(photos[0], 'ImageFileLocationIdentifier')} is not building 1's front "
                    f"photo {_text(fronts[0], 'ImageFileLocationIdentifier')}",
                    "TOTAL delivers building 1's front photo as the subject photo: use the same picture for both, "
                    "or accept that this subject photo will not be delivered")
    if buildings and fronts and len(fronts) != len(buildings):
        out.add("warning", "P22", "E-039", _where(subject),
                f"{len(fronts)} DwellingFront picture(s) for {len(buildings)} building(s)",
                "one DwellingFront per building, in building order (TOTAL files the n-th as building n's front)")


CHECKS = [check_schema_location, check_links, check_empty, check_adjustments, check_utilities, check_grm_sales]


def run(path: Path) -> Findings:
    out = Findings()
    root = etree.parse(str(path), etree.XMLParser(huge_tree=True)).getroot()
    for check in CHECKS:
        check(root, out)
    check_pictures(root, out, path)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("files", nargs="+")
    ap.add_argument("--json", help="write every finding here")
    ap.add_argument("--quiet", action="store_true", help="counts only")
    a = ap.parse_args(argv)
    report, errors = {}, 0
    for f in a.files:
        found = run(Path(f))
        report[f] = found
        c = Counter(x["severity"] for x in found)
        errors += c["error"]
        print(f"{f}: {c['error']} error(s), {c['warning']} warning(s), {c['info']} info")
        if not a.quiet:
            for x in found:
                if x["severity"] != "info":
                    print(f"   {x['severity']:<7} {x['rule']:<4} {x['where'][:60]:<60} {x['message']}")
    if a.json:
        Path(a.json).write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
