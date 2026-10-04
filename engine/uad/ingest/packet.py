"""Split a merged appraisal packet PDF into its constituent documents.

Appraisers receive one concatenated PDF: engagement letter, contract of sale,
the subject's MLS sheet, data-vendor property reports, a 1004MC market study
and an MLS sheet per comparable.  Each document runs across several pages, and
key fields (close date, close price) sit on continuation pages, so anything
that parses page-by-page will silently miss them.

We classify each page, then group runs of pages into documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pymupdf

from .mls import _HEADER


class DocType(str, Enum):
    ORDER = "order"                 # engagement letter / assignment conditions
    CONTRACT = "contract"           # scanned contract of sale
    MLS_LISTING = "mls_listing"     # OneKey listing sheet
    PROPERTY_REPORT = "property_report"   # ATTOM/assessor record
    MARKET_STUDY = "market_study"   # 1004MC + CMA
    SEARCH_RESULTS = "search_results"     # agent one-line search output
    UNKNOWN = "unknown"


@dataclass
class Document:
    doc_type: DocType
    first_page: int                 # 1-based, inclusive
    last_page: int                  # 1-based, inclusive
    title: str | None
    text: str

    @property
    def pages(self) -> range:
        return range(self.first_page, self.last_page + 1)

    def __repr__(self) -> str:
        span = (
            f"p{self.first_page}"
            if self.first_page == self.last_page
            else f"p{self.first_page}-{self.last_page}"
        )
        return f"<{self.doc_type.value} {span} {self.title or ''!r}>"


_PROPERTY_REPORT = re.compile(r"^\s*Property Report on\s+(?P<addr>.+?)\s*$", re.M)
# A heading like "Nassau 1004MC", never the phrase buried in instruction prose,
# and never the "Nassau CMA Report" footer repeated on every CMA page.
_MARKET_STUDY = re.compile(r"^[^\n]{0,40}\b1004MC\b[^\n]{0,20}$|^\s*Inventory Analysis\s*$", re.M)
_SEARCH_RESULTS = re.compile(r"Agent Single Line\s*-\s*Residential")
_ORDER = re.compile(r"Order Information|Client Instructions|engagement letter", re.I)


def _starts_document(text: str) -> tuple[DocType, str | None] | None:
    """Does this page begin a new document?  Returns its type and title."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    head = lines[0] if lines else ""

    if m := _PROPERTY_REPORT.search(text):
        return DocType.PROPERTY_REPORT, m.group("addr")
    if _HEADER.match(head) and "MLS#:" in text:
        return DocType.MLS_LISTING, head
    if _SEARCH_RESULTS.search(text):
        return DocType.SEARCH_RESULTS, None
    if _MARKET_STUDY.search(text):
        return DocType.MARKET_STUDY, None
    if _ORDER.search(text):
        return DocType.ORDER, None
    return None


def split(pdf_path: str | Path) -> list[Document]:
    """Classify and group every page of the packet."""
    doc = pymupdf.open(str(pdf_path))
    pages = [page.get_text() for page in doc]
    doc.close()

    starts: list[tuple[int, DocType, str | None]] = []
    for i, text in enumerate(pages):
        if found := _starts_document(text):
            starts.append((i, *found))

    if not starts:
        return []

    documents: list[Document] = []

    # Anything before the first recognised marker is the order package; pages
    # with no text layer inside that run are the scanned contract.
    if starts[0][0] > 0:
        documents.append(
            Document(DocType.ORDER, 1, starts[0][0], None, "\n".join(pages[: starts[0][0]]))
        )

    for idx, (page_no, doc_type, title) in enumerate(starts):
        end = starts[idx + 1][0] if idx + 1 < len(starts) else len(pages)
        documents.append(
            Document(
                doc_type=doc_type,
                first_page=page_no + 1,
                last_page=end,
                title=title,
                text="\n".join(pages[page_no:end]),
            )
        )

    return _mark_contract_pages(_merge_runs(documents, pages), pages)


def _merge_runs(documents: list[Document], pages: list[str]) -> list[Document]:
    """Fold consecutive documents of the same type into one.

    Multi-page documents repeat their heading or footer on every page, which
    would otherwise start a fresh document each time.  Listings and property
    reports are kept separate even when adjacent, since each describes a
    different property.
    """
    distinct = {DocType.MLS_LISTING, DocType.PROPERTY_REPORT}
    merged: list[Document] = []
    for document in documents:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.doc_type is document.doc_type
            and document.doc_type not in distinct
            and document.first_page == previous.last_page + 1
        ):
            merged[-1] = Document(
                doc_type=previous.doc_type,
                first_page=previous.first_page,
                last_page=document.last_page,
                title=previous.title or document.title,
                text="\n".join(pages[previous.first_page - 1 : document.last_page]),
            )
        else:
            merged.append(document)
    return merged


def _mark_contract_pages(documents: list[Document], pages: list[str]) -> list[Document]:
    """Split a trailing run of image-only pages off the order package.

    The contract of sale is scanned, so it carries no text layer.  Leaving it
    inside the order document would be harmless, but calling it out lets the
    caller route those pages to OCR.
    """
    out: list[Document] = []
    for document in documents:
        if document.doc_type is not DocType.ORDER:
            out.append(document)
            continue

        span = list(document.pages)
        blank = [p for p in span if len(pages[p - 1].strip()) < 32]
        if len(blank) < 3:
            out.append(document)
            continue

        first_blank = blank[0]
        if first_blank > document.first_page:
            out.append(
                Document(
                    DocType.ORDER,
                    document.first_page,
                    first_blank - 1,
                    document.title,
                    "\n".join(pages[document.first_page - 1 : first_blank - 1]),
                )
            )
        out.append(
            Document(
                DocType.CONTRACT,
                first_blank,
                document.last_page,
                "scanned contract of sale",
                "\n".join(pages[first_blank - 1 : document.last_page]),
            )
        )
    return out
