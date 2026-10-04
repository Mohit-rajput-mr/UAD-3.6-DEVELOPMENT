import pathlib

p = pathlib.Path("engine/uad/templates.py")
s = p.read_text(encoding="utf-8")

old_const = '''# Values the appraiser supplies and a new file must not inherit.  Identity,
# money, dates, addresses, narrative and identifiers are cleared; structural
# and enumerated choices are kept, because they are what shapes the form.
CLEARED_SUFFIXES = (
    "Amount", "Date", "Identifier", "Description", "Comment", "Name", "Text",
    "Count", "Measure", "Percent", "Year", "Number", "URL", "Value",
)
KEPT_ELEMENTS = {
    # structural choices that define which sections and grids appear
    "PropertyValuationMethodType", "ConstructionMethodType", "AttachmentType",
    "ProjectLegalStructureType", "LandOwnedInCommonIndicator",
    "LivingUnitExcludingADUCount", "AccessoryDwellingUnitTotalCount",
    "PropertyStructureDesignType", "ValuationUseType", "DocumentType",
    "DocumentFormIssuingEntityNameType",
    "DocumentFormIssuingEntityVersionIdentifier", "AboutVersionIdentifier",
    "ProjectDwellingUnitCount", "AccessoryDwellingUnitIndicator",
}'''

new_const = '''@lru_cache(maxsize=1)
def kept_elements() -> frozenset[str]:
    """Elements a new file inherits, because they decide its shape.

    These are the determining data points -- the same ones that classify a
    sample into a property type -- and nothing else.  Which sections, grids and
    subsections a report has follows from them, so a case that dropped them
    would open as the wrong form.
    """
    return frozenset(dp for _fid, dp in DETERMINANT_FIELDS.values())


@lru_cache(maxsize=1)
def supplied_elements() -> frozenset[str]:
    """Every element the appraiser supplies, read from A-1.

    A new report must inherit none of them.  The set is *derived*: an element
    is appraiser-supplied exactly when Appendix A-1 binds it to a Report Field
    ID, which is the definition A-1 itself uses.  It was previously a list of
    name suffixes written out by hand, and a hand-written list is wrong in the
    way lists are -- ``StateCode`` and ``PostalCode`` end in neither "Name" nor
    "Text" nor "Identifier", so the sample's state and ZIP survived into every
    blank case and printed on the title line of somebody else's report.
    """
    from . import bind
    names = set()
    for fields in bind.page_model().values():
        for pf in fields:
            for dp in pf.binding.data_points:
                if isinstance(dp, dict) and dp.get("mismo") and not dp.get("attribute"):
                    names.add(dp["mismo"])
    return frozenset(names) - kept_elements()'''

assert old_const in s, "constants"
s = s.replace(old_const, new_const)

old_clear = '''    for node in list(root.iter()):
        if not isinstance(node.tag, str) or len(node):
            continue
        local = etree.QName(node).localname
        if local in KEPT_ELEMENTS or not (node.text or "").strip():
            continue
        if local.endswith(CLEARED_SUFFIXES) or local.endswith("Indicator"):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)
                removed += 1'''

new_clear = '''    supplied = supplied_elements()
    for node in list(root.iter()):
        if not isinstance(node.tag, str) or len(node):
            continue
        local = etree.QName(node).localname
        if local not in supplied or not (node.text or "").strip():
            continue
        parent = node.getparent()
        if parent is not None:
            parent.remove(node)
            removed += 1'''

assert old_clear in s, "clear body"
s = s.replace(old_clear, new_clear)

p.write_text(s, encoding="utf-8")
print("clear() now derives the appraiser-supplied set from A-1")
