"""Canonical in-memory representation of a URAR report.

The model is a plain nested dict mirroring the MISMO tree, so it round-trips
losslessly to XML and serialises straight to JSON for the browser editor:

    {"MESSAGE": {"@MISMOReferenceModelIdentifier": "3.6.0366",
                 "DOCUMENT_SETS": {"DOCUMENT_SET": {...}}}}

Repeated containers become lists.  Attributes are stored under an "@" prefix
and xlink labels/refs are preserved verbatim so cross-references survive.
"""
from __future__ import annotations

from typing import Any

from lxml import etree

from . import xsd_order

MISMO_NS = "http://www.mismo.org/residential/2009/schemas"
XLINK_NS = "http://www.w3.org/1999/xlink"
GSE_NS = "http://www.datamodelextension.org"

NSMAP = {None: MISMO_NS, "xlink": XLINK_NS, "gse": GSE_NS}

_PREFIX = {XLINK_NS: "xlink", GSE_NS: "gse"}


XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"

# GSE's own sample files carry xsi:schemaLocation on MESSAGE, which the UAD
# schema does not permit.  Drop it on the way in so we never emit it.
DROPPED_ATTRIBUTES = {f"{{{XSI_NS}}}schemaLocation", f"{{{XSI_NS}}}noNamespaceSchemaLocation"}


def _attr_key(name: str) -> str:
    """'{ns}local' -> '@xlink:local'; plain 'local' -> '@local'."""
    if name.startswith("{"):
        uri, local = name[1:].split("}", 1)
        prefix = _PREFIX.get(uri)
        return f"@{prefix}:{local}" if prefix else f"@{local}"
    return f"@{name}"


def _attr_name(key: str) -> str:
    """Inverse of _attr_key."""
    body = key[1:]
    if ":" in body:
        prefix, local = body.split(":", 1)
        uri = next((u for u, p in _PREFIX.items() if p == prefix), None)
        if uri:
            return f"{{{uri}}}{local}"
    return body


def element_to_dict(elem: etree._Element) -> Any:
    """Convert an lxml element into the canonical dict form."""
    node: dict[str, Any] = {}
    for name, value in elem.attrib.items():
        if name not in DROPPED_ATTRIBUTES:
            node[_attr_key(name)] = value

    children = [c for c in elem if isinstance(c.tag, str)]
    if not children:
        text = (elem.text or "").strip()
        if not node:
            return text  # pure leaf: represent as the scalar itself
        if text:
            node["#text"] = text
        return node

    for child in children:
        tag = etree.QName(child).localname
        value = element_to_dict(child)
        if tag in node:
            if not isinstance(node[tag], list):
                node[tag] = [node[tag]]
            node[tag].append(value)
        else:
            node[tag] = value
    return node


def parse(source) -> dict[str, Any]:
    """Parse a MISMO XML file/bytes into the canonical model."""
    tree = source if isinstance(source, etree._ElementTree) else etree.parse(source)
    root = tree.getroot()
    return {etree.QName(root).localname: element_to_dict(root)}


def _sorted_children(parent: str, node: dict) -> list[tuple[str, Any]]:
    """Order a container's children into XSD sequence order.

    Children the schema doesn't declare keep their original relative position
    and are appended last, so hand-added extensions are never dropped.
    """
    order = xsd_order.load()
    keyed, unknown = [], []
    for tag, value in node.items():
        if tag.startswith("@") or tag == "#text":
            continue
        pos = order.position(parent, tag)
        (keyed if pos is not None else unknown).append((pos, tag, value))
    keyed.sort(key=lambda t: t[0])
    return [(tag, value) for _, tag, value in keyed + unknown]


def dict_to_element(tag: str, node: Any, path: str, spec=None) -> etree._Element:
    elem = etree.Element(f"{{{MISMO_NS}}}{tag}", nsmap=NSMAP if path == "" else None)
    if not isinstance(node, dict):
        if node not in (None, ""):
            elem.text = str(node)
        return elem

    for key, value in node.items():
        if key.startswith("@"):
            elem.set(_attr_name(key), str(value))
    if "#text" in node:
        elem.text = str(node["#text"])

    child_path = f"{path}{tag}/"
    for child_tag, value in _sorted_children(tag, node):
        for item in value if isinstance(value, list) else [value]:
            elem.append(dict_to_element(child_tag, item, child_path, spec))
    return elem


def serialize(model: dict[str, Any], spec=None, *, pretty: bool = True) -> bytes:
    """Render the canonical model back to MISMO XML bytes."""
    (tag, node), = model.items()
    root = dict_to_element(tag, node, "", spec)
    return etree.tostring(
        root,
        pretty_print=pretty,
        xml_declaration=True,
        encoding="utf-8",
        standalone=True,
    )


# --------------------------------------------------------------- navigation
DEAL_PATH = (
    "DOCUMENT_SETS/DOCUMENT_SET/DOCUMENTS/DOCUMENT/DEAL_SETS/DEAL_SET/DEALS/DEAL"
)
VALUATION_PATH = f"{DEAL_PATH}/SERVICES/SERVICE/VALUATION/VALUATION_RESPONSE"
ANALYSIS_PATH = f"{VALUATION_PATH}/VALUATION_ANALYSES/VALUATION_ANALYSIS"


def get(model: dict, path: str, default=None):
    """Walk a '/'-separated path to the first node that resolves it.

    Repeated containers are searched rather than assumed: a DEAL can carry an
    inspection SERVICE alongside the valuation SERVICE, and only one of them
    holds a VALUATION, so taking the first would lose the report.
    """
    parts = [p for p in path.split("/") if p]

    def walk(node: Any, remaining: list[str]) -> Any:
        if not remaining:
            return node
        head, tail = remaining[0], remaining[1:]
        for item in node if isinstance(node, list) else [node]:
            if isinstance(item, dict) and head in item:
                found = walk(item[head], tail)
                if found is not None:
                    return found
        return None

    found = walk(model.get("MESSAGE", model), parts)
    return default if found is None else found


def properties(model: dict) -> list[dict]:
    """Every PROPERTY block: the subject plus each comparable."""
    props = get(model, f"{ANALYSIS_PATH}/PROPERTIES/PROPERTY", [])
    return props if isinstance(props, list) else [props]


def subject(model: dict) -> dict | None:
    return next(
        (p for p in properties(model) if p.get("@ValuationUseType") == "SubjectProperty"),
        None,
    )


def comparables(model: dict) -> list[dict]:
    return [
        p for p in properties(model) if p.get("@ValuationUseType") != "SubjectProperty"
    ]
