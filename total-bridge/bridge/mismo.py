"""Reading values out of a UAD 3.6 MISMO file, by Report Field ID.

The map in ``data/uad36_map.json`` is generated from the published Appendix A-1
delivery specification: for each Report Field ID it records where in the
document that value lives.  Shipping the generated map is what makes this
application standalone -- it needs no other software to understand a 3.6 file.

Scoping matters more than the paths do.  Almost every field in the comparison
grid has the same path; what distinguishes the subject's value from the third
comparable's is *which* PROPERTY the path is evaluated against.  A reader that
ignores this returns the subject's answer for every column, which looks
plausible and is wrong.
"""
from __future__ import annotations

import json
from pathlib import Path

import re

from lxml import etree

MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
NS = {"m": MISMO_NS}
DATA = Path(__file__).resolve().parent.parent / "data" / "uad36_map.json"

SUBJECT = "SubjectProperty"
SALES_COMPARABLE = "SalesComparable"


def load_map(path: Path | None = None) -> dict:
    src = path or DATA
    if not src.exists():
        raise SystemExit(
            f"field map missing at {src}.\n"
            "It is generated from the published Appendix A-1 specification; "
            "run tools/make_map.py to produce it.")
    payload = json.loads(src.read_text(encoding="utf-8"))
    # The map grew a second half (photograph categories) after the first
    # release; a bare mapping of field ids is still accepted so an older file
    # keeps working.
    return payload if "fields" in payload else {"fields": payload,
                                                "image_categories": {}}


_PRECISION = re.compile(r"[+±]?(\d+)\.(\d+)")


def _format(raw: str, format_type: str, details: str) -> str:
    """Print a stored value the way A-1 says the report prints it.

    A-1 writes a numeric format as +I.D -- digits before the point are the
    width, digits after are the precision.  +9.2 prints 121.25, +9.0 prints
    491,000.  Thousands separators are what the form shows, so they go in.
    """
    kind = (format_type or "").lower()
    if kind in ("string", "", "text"):
        return raw
    if kind in ("boolean", "bool"):
        return {"true": "Yes", "false": "No"}.get(raw.strip().lower(), raw)
    if kind in ("date",):
        parts = raw.split("-")
        if len(parts) == 3 and len(parts[0]) == 4:
            return f"{parts[1]}/{parts[2]}/{parts[0]}"
        return raw
    # A-1's numeric format (+9.2) is how the *report prints* a value, not how a
    # form expects to receive one.  A box that formats its own contents on blur
    # can reject a pre-formatted string, so a number is handed over the way an
    # appraiser would type it and TOTAL is left to present it.  Only a trailing
    # all-zero fraction is dropped, because "650000.00" is not typed by anyone.
    text = raw.strip()
    if "." in text:
        whole, _, frac = text.partition(".")
        if frac and not frac.strip("0"):
            return whole
    return text


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


class Case:
    """One UAD 3.6 MISMO document."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.tree = etree.parse(str(self.path))
        self.root = self.tree.getroot()
        payload = load_map()
        self.map = payload["fields"]
        self.categories = payload.get("image_categories", {})

    # ----------------------------------------------------------- properties
    def properties(self, use: str) -> list[etree._Element]:
        """The PROPERTY blocks of one role, in the order the report numbers them."""
        found = [p for p in self.root.iter(f"{{{MISMO_NS}}}PROPERTY")
                 if p.get("ValuationUseType") == use]

        def ordinal(prop):
            for node in prop.iter():
                if _local(node.tag) == "PropertyOrdinalNumber":
                    try:
                        return int((node.text or "0").strip())
                    except ValueError:
                        return 0
            return 0

        return sorted(found, key=ordinal)

    @property
    def subject(self):
        found = self.properties(SUBJECT)
        return found[0] if found else None

    @property
    def comparables(self) -> list[etree._Element]:
        return self.properties(SALES_COMPARABLE)

    def column(self, n: int):
        """The PROPERTY a grid column is about: 0 is the subject, 1..N a comparable."""
        if n == 0:
            return self.subject
        comps = self.comparables
        return comps[n - 1] if 0 < n <= len(comps) else None

    # --------------------------------------------------------------- values
    def value(self, field_id: str, column: int | None = None) -> str:
        """The value of one Report Field ID, in one grid column when given."""
        entry = self.map.get(field_id)
        if not entry:
            return ""
        scope = self.root if column is None else self.column(column)
        if scope is None:
            return ""
        for point in entry.get("points", []):
            text = self._read_point(scope, point, scoped=column is not None)
            if text:
                return text
        return ""

    def _read_point(self, scope, point: dict, *, scoped: bool) -> str:
        """One data point, read where A-1 says it lives.

        The element name alone is not enough.  ``FirstName`` appears in every
        party in the file, and reading the first one filled the appraiser's
        name with the borrower's; ``AddressLineText`` appears in every address,
        and filled the appraiser's company address with the subject's street.
        So the candidates are narrowed first to the party the point belongs to
        -- A-1 names it in the Additional Context -- and then to those whose
        ancestors match the tail of A-1's own path.
        """
        name = point.get("mismo")
        if not name:
            return ""
        attribute = point.get("attribute") or ""
        for node in self._candidates(scope, name, point):
            if attribute:
                got = node.get(attribute)
                if got:
                    return got.strip()
                continue
            text = (node.text or "").strip()
            if text:
                return text
        return ""

    def _candidates(self, scope, name: str, point: dict) -> list:
        """The elements this point could be, best-scoped first."""
        found = list(scope.iter(f"{{{MISMO_NS}}}{name}"))
        if not found:
            return found
        # The checks below run even when the file holds only one element of
        # this name.  A single comment in the document is still only *that*
        # comment: treating it as "the only candidate, so it must be the one"
        # is what put the assignment's paragraph into every other box.
        category = point.get("category") or ""
        if not category and name == "ValuationCommentText":
            # Which box a comment belongs in is the category beside it.  Where
            # that is not known, no comment is better than the wrong one: the
            # first paragraph in the file was otherwise read back into Site
            # Influence, View, Site Features and Amenities alike.
            return []
        if category:
            # Every commentary box writes ValuationCommentText into a
            # VALUATION_COMMENTARY; the category beside it is what says which
            # box it is.  Without this the first comment in the file was read
            # back into every commentary on the form -- the same paragraph
            # under Site Influence, View, Site Features and Amenities.
            inside = [n for n in found if self._commentary(n) == category]
            return inside

        role = point.get("party_role") or ""
        if role:
            inside = [n for n in found if self._party_role(n) == role]
            if inside:
                return inside
            if any(self._party_role(n) for n in found):
                return []          # it belongs to a party this file lacks

        if len(found) < 2:
            return found
        segments = [s for s in (point.get("xpath") or "").strip("/").split("/") if s]
        for start in range(len(segments)):
            tail = segments[start:]
            if len(tail) < 2:
                break
            on_path = [n for n in found if self._matches(n, tail[:-1])]
            if on_path:
                return on_path
        return found

    @staticmethod
    def _commentary(node) -> str:
        """The category of the commentary block this element sits in."""
        cur = node.getparent()
        while cur is not None:
            if _local(cur.tag) == "VALUATION_COMMENTARY":
                for kind in cur.iter(f"{{{MISMO_NS}}}ValuationAnalysisCategoryType"):
                    text = (kind.text or "").strip()
                    if text:
                        return text
                return ""
            cur = cur.getparent()
        return ""

    @staticmethod
    def _party_role(node) -> str:
        """The role of the PARTY this element sits in, if it sits in one."""
        cur = node.getparent()
        while cur is not None:
            if _local(cur.tag) == "PARTY":
                for kind in cur.iter(f"{{{MISMO_NS}}}PartyRoleType"):
                    text = (kind.text or "").strip()
                    if text:
                        return text
                return ""
            cur = cur.getparent()
        return ""

    @staticmethod
    def _matches(node, segments: list) -> bool:
        """Does this element sit at the end of that run of container names?"""
        cur = node.getparent()
        for want in reversed(segments):
            if cur is None or _local(cur.tag) != want:
                return False
            cur = cur.getparent()
        return True

    # ------------------------------------------------------------- display
    def entry(self, field_id: str) -> dict:
        return self.map.get(field_id) or {}

    def is_enumerated(self, field_id: str) -> bool:
        return bool(self.entry(field_id).get("enum"))

    def display(self, field_id: str, column: int | None = None) -> str:
        """The value as the form expects to receive it.

        A document says ``SettledSale`` and ``650000``; the form offers
        "Settled Sale" in a pick list and shows "$650,000" in a box.  Typing
        the document's own wording into a pick list matches nothing and leaves
        the field empty, which is the quiet failure this exists to prevent.
        """
        entry = self.entry(field_id)
        joined = self._joined(entry, column)
        if joined:
            return joined
        raw = self.value(field_id, column)
        if not raw:
            return ""

        options = entry.get("enum") or {}
        if options:
            # An exact code, else a case-insensitive match, else leave it be:
            # a value the standard does not list is the appraiser's own.
            if raw in options:
                return options[raw]
            for code, shown in options.items():
                if code.lower() == raw.lower():
                    return shown
            return raw

        point = (entry.get("points") or [{}])[0]
        return _format(raw, point.get("format_type", ""),
                       point.get("format_details", ""))

    #: A name and an address reach the form as one box each, so the parts are
    #: put back together in the order they are written in: "Mickaelle Petit",
    #: "2605 Francis Lewis Blvd, Suite 102, Flushing, NY 11358".  Reading only
    #: the first part that had a value is what put "Mickaelle" in the
    #: appraiser's name box and left the city and state off every address.
    NAME_PARTS = ("FirstName", "MiddleName", "LastName", "SuffixName")
    ADDRESS_PARTS = ("AddressLineText", "AddressUnitIdentifier",
                     "CityName", "StateCode", "PostalCode")

    def _joined(self, entry: dict, column: int | None) -> str:
        """A multi-part value as one line, where the form shows one box."""
        names = [p.get("mismo") for p in entry.get("points", [])]
        for group, comma in ((self.NAME_PARTS, False), (self.ADDRESS_PARTS, True)):
            if len(set(names) & set(group)) < 2:
                continue
            scope = self.root if column is None else self.column(column)
            if scope is None:
                return ""
            got = []
            for part in group:
                point = next((p for p in entry["points"] if p.get("mismo") == part), None)
                if point is None:
                    continue
                text = self._read_point(scope, point, scoped=column is not None)
                if text:
                    got.append(text)
            if not got:
                return ""
            if not comma:
                return " ".join(got)
            # "street, city, STATE ZIP": the state and the postal code belong
            # together, the rest are separated by commas.
            tail = " ".join(got[-2:]) if len(got) >= 3 else ""
            head = got[:-2] if tail else got
            return ", ".join([*head, tail]) if tail else ", ".join(head)
        return ""

    # -------------------------------------------------------------- summary
    def describe(self) -> dict:
        subject = self.subject
        address = ""
        if subject is not None:
            parts = []
            for want in ("AddressLineText", "CityName", "StateCode", "PostalCode"):
                for node in subject.iter(f"{{{MISMO_NS}}}{want}"):
                    if (node.text or "").strip():
                        parts.append(node.text.strip())
                        break
            address = ", ".join(parts)
        return {"file": self.path.name,
                "address": address,
                "comparables": len(self.comparables),
                "fields_in_map": len(self.map)}
