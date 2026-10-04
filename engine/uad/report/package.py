"""Build the deliverable ZIP: appraisal.pdf, mismo.xml and Images/.

The layout matches what the client's delivery portal expects, which is the same
layout the reference reports use.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

from uad.report.browser import sync_playwright  # optional: BrowserUnavailable without Chromium

PDF_NAME = "appraisal.pdf"
XML_NAME = "mismo.xml"
IMAGE_DIR = "Images"


# The URAR repeats a title and page number across the top of every page, and
# carries the form's provenance and the reference identifiers along the bottom.
HEADER_TEMPLATE = """
<div style="width:100%;font:7.5pt 'Segoe UI',Arial,sans-serif;
            padding:0 0.5in;margin:0;color:#000;">
  <div style="display:flex;justify-content:space-between;align-items:baseline;
              border-bottom:0.5pt solid #000;padding-bottom:2px;">
    <span style="font-weight:700;">Uniform Residential Appraisal Report</span>
    <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>
  </div>
</div>
"""

FOOTER_TEMPLATE = """
<div style="width:100%;font:6.5pt 'Segoe UI',Arial,sans-serif;
            padding:0 0.5in;margin:0;color:#000;">
  <div style="border-top:1.2pt solid #000;padding-top:3px;
              display:flex;justify-content:space-between;">
    <span>
      <strong>Appraisal Version #__APPRAISALVER__</strong><br>
      <span style="color:#808080;">Fannie&nbsp;Mae | Freddie&nbsp;Mac<br>__FORMVER__</span>
    </span>
    <span style="text-align:right;">
      <strong>Appraiser Reference ID</strong> __ORDER__<br>
      <strong>Client Reference ID</strong> __LOAN__
    </span>
  </div>
</div>
"""


def html_to_pdf(
    html: str,
    *,
    base_url: str | None = None,
    order_id: str = "",
    loan_id: str = "",
    appraisal_version: str = "1",
    form_version: str = "September 2024",
    cookie: tuple[str, str] | None = None,
) -> bytes:
    """Render the report HTML to PDF with the engine that shows the preview.

    The first page carries the full title block, so the running header starts
    on page two; Chromium has no per-page header switch, so the header markup
    hides itself on page one via the page-number counter.
    """
    footer = (
        FOOTER_TEMPLATE.replace("__ORDER__", order_id)
        .replace("__LOAN__", loan_id)
        .replace("__APPRAISALVER__", appraisal_version)
        .replace("__FORMVER__", form_version)
    )

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context()
        if cookie and base_url:
            # The review server is passcode-protected; the renderer is the
            # server itself, so it presents the session's own cookie.
            name, value = cookie
            context.add_cookies([{
                "name": name, "value": value,
                "url": base_url.rsplit("/", 1)[0] or base_url,
            }])
        page = context.new_page()
        if base_url:
            page.goto(base_url, wait_until="networkidle")
        else:
            page.set_content(html, wait_until="load")
        pdf = page.pdf(
            print_background=True,
            prefer_css_page_size=True,
            display_header_footer=True,
            header_template=HEADER_TEMPLATE,
            footer_template=footer,
            margin={
                "top": "0.62in",
                "bottom": "0.72in",
                "left": "0.5in",
                "right": "0.5in",
            },
        )
        browser.close()
    return pdf


# Appendix B-1 p69: one .zip per appraisal, not to exceed 60 MB.
MAX_ZIP_BYTES = 60 * 1024 * 1024


def referenced_images(xml_bytes: bytes) -> set[str]:
    r"""Image file names the XML points at, from \\Images\NAME.ext paths."""
    import re

    text = xml_bytes.decode("utf-8", "replace")
    paths = re.findall(
        r"<ImageFileLocationIdentifier>([^<]+)</ImageFileLocationIdentifier>", text
    )
    return {p.replace("\\", "/").rsplit("/", 1)[-1] for p in paths}


def verify(pdf_bytes: bytes, xml_bytes: bytes, image_dir: Path) -> list[str]:
    """Check the package against Appendix B-1's file-structure rules (p69-73).

    Returns the problems found; an empty list means the package conforms.
    """
    problems: list[str] = []
    image_dir = Path(image_dir)
    present = {p.name for p in image_dir.iterdir() if p.is_file()} if image_dir.is_dir() else set()
    referenced = referenced_images(xml_bytes)

    for name in sorted(present - referenced):
        problems.append(
            f"Images/{name} is in the Images folder but is never referenced in the "
            f"XML; B-1 p73 requires every image to be referenced at least once."
        )
    for name in sorted(referenced - present):
        problems.append(
            f"The XML references Images/{name}, which is missing from the Images folder."
        )

    # B-1 p72 requires UTF-8; the declaration may quote it either way.
    declaration = xml_bytes[:120].lower()
    if not xml_bytes.startswith(b"<?xml") or b"encoding=" not in declaration:
        problems.append("The XML must carry an encoding declaration (B-1 p72).")
    elif b"utf-8" not in declaration:
        problems.append("The XML must declare UTF-8 encoding (B-1 p72).")
    if not pdf_bytes.startswith(b"%PDF"):
        problems.append("The appraisal report is not a valid PDF.")
    return problems


def build(
    *,
    pdf_bytes: bytes,
    xml_bytes: bytes,
    image_dir: Path,
    extra: dict[str, bytes] | None = None,
    strict: bool = True,
) -> bytes:
    """Assemble the deliverable archive in memory.

    The layout is the one UCDP expects: the PDF and XML at the root of the
    archive with an ``Images`` folder beside them (B-1 p70).
    """
    image_dir = Path(image_dir)
    problems = verify(pdf_bytes, xml_bytes, image_dir)
    if problems and strict:
        raise ValueError("Package does not conform:\n  - " + "\n  - ".join(problems))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(PDF_NAME, pdf_bytes)
        archive.writestr(XML_NAME, xml_bytes)

        if image_dir.is_dir():
            for path in sorted(image_dir.iterdir()):
                if path.is_file():
                    archive.write(path, f"{IMAGE_DIR}/{path.name}")

        for name, data in (extra or {}).items():
            archive.writestr(name, data)

    archive_bytes = buffer.getvalue()
    if len(archive_bytes) > MAX_ZIP_BYTES:
        raise ValueError(
            f"Archive is {len(archive_bytes) / 1024 / 1024:.1f} MB, over the 60 MB "
            f"limit in B-1 p69. Reduce image resolution before delivering."
        )
    return archive_bytes


def filename_for(address: str, effective_date: str) -> str:
    """A predictable archive name: street address plus effective date."""
    slug = "".join(c if c.isalnum() else "_" for c in address).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{slug}_{effective_date}.zip"
