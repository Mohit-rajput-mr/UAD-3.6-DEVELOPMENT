"""Which Report Field IDs a document actually answers.

Reading a value back says what it is, never where it came from: a field the
appraiser typed and a field an import wrote are the same element with the same
text.  So when a file is brought in, the fields it answered are recorded
against the case, and the editor marks exactly those.

The set is taken from the page model rather than from the XML, because that is
the question being asked -- not "which elements carry text" but "which places
on the report now have an answer".  The two differ: one element can answer
several fields (an address is six data points behind one control), and the
Summary answers nothing of its own while showing a dozen fields from
elsewhere.
"""
from __future__ import annotations

from lxml import etree

from . import bind
from .report import comparables


def answered(root: etree._Element) -> set[str]:
    """Every Report Field ID the document has a value for."""
    found: set[str] = set()
    for fields in bind.page_model().values():
        for pf in fields:
            try:
                groups = bind.read_groups(root, pf.binding, ordinal=pf.ordinal)
            except Exception:
                continue
            if any(value and str(value).strip()
                   for group in groups for _name, value in group):
                found.add(pf.field_id)
    return found


def answered_in_grids(root: etree._Element) -> set[str]:
    """The comparable grids' own field IDs, which the page model does not hold.

    A grid cell belongs to a property rather than to the subject, so it is read
    through the grid with that property as its scope; asking the page model for
    22.01.17 gets the subject's address every time.
    """
    found: set[str] = set()
    for kind in comparables.SHEETS:
        try:
            grids = comparables.build(root, kind, every_row=True)
        except Exception:
            continue
        for grid in grids:
            for row in grid.rows:
                if row.heading:
                    continue
                if str(getattr(row, "subject", "") or "").strip() and row.subject_fid:
                    found.add(row.subject_fid)
                if row.comp_fid and any(str(cell.text or "").strip() for cell in row.cells):
                    found.add(row.comp_fid)
                if row.adjust_fid and any(str(cell.adjustment or "").strip()
                                          for cell in row.cells):
                    found.add(row.adjust_fid)
    return found


def summary_shadow(fields: set[str]) -> set[str]:
    """The Summary lines that redisplay an answered field.

    The Summary holds no values of its own -- B-1 chapter 01 makes every line
    of it a redisplay -- so nothing there is ever "filled".  It still has to
    show as imported: a page that stays blank while the rest of the report
    turns green reads as a page the import missed.
    """
    from .report import form

    shadow: set[str] = set()
    for fid, source in form.summary_sources().items():
        if any(s in fields for s in (source.get("sources") or ())):
            shadow.add(fid)
    return shadow


def imported_fields(root: etree._Element) -> list[str]:
    """Everything an import answered, for the editor to mark."""
    fields = answered(root) | answered_in_grids(root)
    return sorted(fields | summary_shadow(fields))
