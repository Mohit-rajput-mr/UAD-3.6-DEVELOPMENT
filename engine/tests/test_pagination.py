"""Page breaks against the D-1 samples and Appendix E.

The page planner (``flow.plan``) decides where every page ends.  Each rule
here was read off the twelve official PDFs and, where Appendix E states it,
from the Style Guide:

* a full-page image (sketch, floor plan, map, property boundaries) opens a
  page, and what leads to it goes with it (E p31; every such image in D-1);
* the Scope of Work opens a page with its own text, no tab (E p79/p85);
* Certifications opens a page (D-1, 12 of 12);
* a heading keeps with the headings under it and their first line;
* a grid under a page's lone section tab is split there, never moved on.

And two content rules that moved page counts:

* SketchExistsIndicator "true" with no sketch IMAGE still prints the sketch
  space (B-1 p162-163; D-1 SF1 p5, SF5 p4);
* LandComparableMap prints in the Cost Approach when that section prints
  (A-1 gives it two homes; D-1 MH1 p25).
"""
import re
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates  # noqa: E402
from uad.report import browser, flow, form  # noqa: E402

needs_browser = pytest.mark.skipif(not browser.AVAILABLE, reason=browser.MESSAGE)
M = "{http://www.mismo.org/residential/2009/schemas}"


def _tree(key: str):
    return etree.parse(str(templates.get(key).path))


def _text(b) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", b.html).split())


def _blocks(key: str, tree=None):
    tpl = templates.get(key)
    return form.build(tree if tree is not None else _tree(key), folder=tpl.path.parent)


# ---------------------------------------------------------------- the content
@pytest.mark.parametrize("key", ["sf1_appraisal_v1_4", "sf5_appraisal_v1_2"])
def test_a_sketch_that_exists_has_its_space(key):
    """B-1 p163: an integrated sketch needs no separate IMAGE, and the space is
    still the report's -- D-1 SF1 p5 and SF5 p4 print the 7.002 box."""
    blocks = [b for b in _blocks(key) if b.visible and b.section == "Sketch"]
    boxes = [b for b in blocks if b.kind == "exhibits"]
    assert len(boxes) == 1, [_text(b) for b in blocks]
    assert "ex full" in boxes[0].html
    assert "This is where the Sketch image would display." in _text(boxes[0])
    assert _text(boxes[0]).startswith("Sketch")


def test_no_sketch_prints_no_sketch_space():
    tree = _tree("sf1_appraisal_v1_4")
    for e in tree.iter(f"{M}SketchExistsIndicator"):
        e.text = "false"
    blocks = [b for b in _blocks("sf1_appraisal_v1_4", tree) if b.section == "Sketch"]
    assert not [b for b in blocks if b.visible and b.kind == "exhibits"]
    # B-1 p162 / Figure 7-1: the section always displays, and says so
    galley = " ".join(re.sub(r"<[^>]+>", " ", form.galley_html(blocks)).split())
    assert galley == "Sketch Sketch or Floor Plan Not Available", galley


def test_a_sketch_that_exists_keeps_measurement_standard():
    blocks = [b for b in _blocks("sf1_appraisal_v1_4") if b.section == "Sketch"]
    galley = " ".join(re.sub(r"<[^>]+>", " ", form.galley_html(blocks)).split())
    assert galley.startswith("Sketch Measurement Standard ANSI Sketch"), galley
    assert "Not Available" not in galley


def test_a_sketch_image_is_not_doubled():
    """A sample that carries its sketch (SF3) prints that one, no extra space."""
    blocks = [b for b in _blocks("sf3_appraisal_v1_4") if b.visible and b.section == "Sketch"]
    assert len([b for b in blocks if b.kind == "exhibits"]) == 1


@pytest.mark.parametrize("key,caption", [("sf3_appraisal_v1_4", "Sketch"),
                                         ("condo1_appraisal_v1_4", "Floor Plan")])
def test_the_sketch_caption_prints_once(key, caption):
    """The 7.002 table is the picture's frame; its caption is on the frame
    (D-1 SF3 p6, Condo1 p5), not also a row above it."""
    blocks = [b for b in _blocks(key) if b.section == "Sketch"]
    galley = " ".join(re.sub(r"<[^>]+>", " ", form.galley_html(blocks)).split())
    body = galley.split(" ", 1)[1]                       # past the tab
    assert body.count(caption) == 1, galley


def test_a_tabs_own_placeholders_do_not_print_in_the_section_before():
    """C-1 p14 sets 10.000-10.002 ([Outbuilding Type] - [Structure Identifier]
    - [Unit Identifier]) on the Unit Interior tab; read as the section before,
    MH1 printed "Rec Room/Garage" under Manufactured Home."""
    for key in ("mh1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4"):
        blocks = [b for b in _blocks(key) if b.visible]
        assert not [b for b in blocks if {"10.000", "10.001", "10.002"} & set(b.fids)], key
    tabs = [b.section for b in _blocks("2_to_4_unit_appraisal_v1_4") if b.kind == "tab"]
    assert "Unit Interior - Building 2 - Unit 2" in tabs


def test_the_land_comparables_map_prints_in_the_cost_approach():
    blocks = [b for b in _blocks("mh1_appraisal_v1_4") if b.visible]
    homes = [b.section for b in blocks if "Map of Land Comparables" in _text(b)]
    assert homes == ["Cost Approach"], homes


def test_the_land_comparables_map_falls_back_to_site():
    """Without a Cost Approach the map's other A-1 home, Site Exhibits, holds it."""
    ctx = form.Ctx(_tree("sf1_appraisal_v1_4").getroot())
    assert form.section_shown(ctx, "Cost Approach") is False
    assert form.image_section(ctx, "LandComparableMap", "Site") == "Site"
    assert form.image_sections() == {"LandComparableMap": ["Site", "Cost Approach"]}


def test_the_scope_of_work_and_the_certifications_open_pages():
    blocks = [b for b in _blocks("sf1_appraisal_v1_4") if b.visible]
    scope = next(b for b in blocks if _text(b).startswith("This appraisal report is subject to"))
    assert scope.new_page and scope.kind != "tab"
    cert = next(b for b in blocks if b.kind == "tab" and b.section == "Certifications")
    assert cert.new_page


def test_the_market_value_footnote_is_set_as_fn():
    """Appendix E p80: the Definition of Market Value's footnote sets as FN, 8/10."""
    blocks = [b for b in _blocks("sf1_appraisal_v1_4") if b.visible]
    notes = [b for b in blocks if _text(b).startswith("*Adjustments to the comparables")]
    assert len(notes) == 1 and "txc kp fn" in notes[0].html
    assert not [b for b in blocks if " fn'" in b.html and b is not notes[0]]
    css = form.stylesheet(embed_fonts=False)
    assert re.search(r"\.txc\.kp\.fn\{font-size:8pt;[^}]*line-height:10pt\}", css)


# ---------------------------------------------------------------- the planner
def _b(n, kind, height, section="S", *, group=0, html="", newpage=False, rows=None, lead=0.0):
    return {"n": n, "kind": kind, "group": group, "section": section, "newpage": newpage,
            "height": height, "lead": lead, "cols": [], "rows": rows or [], "head": "",
            "html": html, "outer": f"<div class='blk {kind}'>"}


def _tab(n, section):
    return _b(n, "tab", 20.0, section, group=3)


FULL = "<figure class=\"ex full\"><div class=\"cap\"><b>Sketch</b></div></figure>"
PHOTO = "<figure class=\"ex\"><div class=\"cap\"><b>Photo</b></div></figure>"


def _where(pages, needle: str) -> int:
    return next(i for i, p in enumerate(pages) if any(needle in pc.html for pc in p.pieces))


def test_a_full_page_image_opens_a_page_with_its_lead_in():
    """MH1 p6: the page before ends at 211 pt, and the Sketch still opens a page."""
    blocks = [_tab(0, "Site"), _b(1, "text", 100.0, "Site", html="site text"),
              _tab(2, "Sketch"), _b(3, "text", 20.0, "Sketch", html="Measurement Standard"),
              _b(4, "exhibits", 560.0, "Sketch", html=FULL),
              _tab(5, "Dwelling Exterior"), _b(6, "text", 40.0, "Dwelling Exterior", html="dwelling")]
    pages = flow.plan(blocks)
    assert _where(pages, "site text") == 0
    assert _where(pages, "Measurement Standard") == _where(pages, "ex full") == 1
    first = pages[1].pieces[0].html
    assert "Sketch" in first and "(continued)" not in first
    assert _where(pages, "dwelling") == 1          # what follows may share the page


def test_a_full_page_image_under_its_heading_carries_a_continued_tab():
    """MH1 p22 / Co-op1 p14: "Sales Comparison Approach (continued)", the
    "Sales Comparison Map" H1, then the map."""
    blocks = [_tab(0, "SCA"), _b(1, "text", 100.0, "SCA", html="grid"),
              _b(2, "h1", 20.0, "SCA", group=2, html="Sales Comparison Map"),
              _b(3, "exhibits", 560.0, "SCA", html=FULL)]
    pages = flow.plan(blocks)
    assert len(pages) == 2
    assert "(continued)" in pages[1].pieces[0].html
    assert "Sales Comparison Map" in pages[1].pieces[1].html


def test_photos_still_share_the_page():
    blocks = [_tab(0, "Site"), _b(1, "text", 100.0, "Site", html="site text"),
              _b(2, "h1", 20.0, "Site", group=2, html="Site Exhibits"),
              _b(3, "exhibits", 200.0, "Site", html=PHOTO)]
    assert len(flow.plan(blocks)) == 1


def test_a_section_opening_with_text_opens_its_page_without_a_tab():
    blocks = [_tab(0, "Reconciliation"), _b(1, "text", 100.0, "Reconciliation", html="recon"),
              _b(2, "static", 700.0, "Scope", html="This appraisal report is subject", newpage=True),
              _b(3, "static", 300.0, "Scope", html="more scope")]
    pages = flow.plan(blocks)
    assert pages[1].pieces[0].html.count("This appraisal report is subject") == 1
    assert not any("tabblk" in p.html for p in pages[1].pieces)
    # where the text runs on, there is no section to call "(continued)"
    assert not any("(continued)" in p.html for pg in pages[2:] for p in pg.pieces)


def test_a_tab_keeps_with_its_heading_and_first_line():
    """The Certifications tab was left alone at a page foot, its H1 carried over."""
    blocks = [_tab(0, "A"), _b(1, "text", 790.0, "A", html="filler"),
              _tab(2, "Certifications"),
              _b(3, "h1", 20.0, "Certifications", group=2, html="Appraiser Certifications"),
              _b(4, "static", 40.0, "Certifications", html="The Appraiser certifies")]
    pages = flow.plan(blocks)
    assert _where(pages, "Appraiser Certifications") == _where(pages, "The Appraiser certifies") == 1
    assert "(continued)" not in pages[1].pieces[0].html      # the tab itself moved


def test_a_grid_under_a_lone_tab_is_split_not_moved():
    rows = [{"html": f"<tr><td>r{k}</td></tr>", "height": 20.0, "sub": False} for k in range(60)]
    grid = _b(1, "grid", 1000.0, "SCA", rows=rows)
    grid.update({"tableOpen": "<table class='grid'>", "headHeight": 10.0, "contHeadHeight": 10.0})
    blocks = [_tab(0, "SCA"), grid]
    blocks[0]["newpage"] = True
    pages = flow.plan([_b(9, "text", 300.0, "Before", html="before")] + blocks)
    tab_page = _where(pages, "SCA</span>")
    assert any("r0<" in p.html for p in pages[tab_page].pieces), "the tab was left alone"


# ---------------------------------------------------------------- end to end
def _rendered(key: str, tmp_path):
    pymupdf = pytest.importorskip("pymupdf")
    tpl = templates.get(key)
    html = flow.build(_tree(key), folder=tpl.path.parent, screen=False, diagnostics={})
    out = tmp_path / f"{key}.pdf"
    flow.to_pdf(html, out)
    return pymupdf.open(out)


def _first_line(page) -> str:
    lines = []
    for b in page.get_text("dict")["blocks"]:
        for ln in b.get("lines", []):
            y = ln["bbox"][1]
            t = " ".join(s["text"] for s in ln["spans"]).strip()
            if t and 50 < y < page.rect.height - 85:
                lines.append((y, t))
    return min(lines)[1] if lines else ""


@needs_browser
@pytest.mark.parametrize("key,pages", [("sf1_appraisal_v1_4", 21), ("sf2_appraisal_v1_4", 22)])
def test_page_counts_match_the_official_samples(key, pages, tmp_path):
    doc = _rendered(key, tmp_path)
    assert doc.page_count == pages
    heads = [_first_line(p) for p in doc]
    for opener in ("Sketch", "Certifications"):
        assert opener in heads, f"{opener} does not head a page"
    assert any(h.startswith("This appraisal report is subject to") for h in heads)
