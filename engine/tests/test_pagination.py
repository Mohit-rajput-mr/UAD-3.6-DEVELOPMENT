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
sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def test_the_editor_keeps_a_tabs_placeholders_as_controls():
    """In the editor the same slots are the unit's own fields, named where they
    stand ("Unit Interior: Outbuilding Type"), so they can still be typed."""
    tpl = templates.get("mh1_appraisal_v1_4")
    blocks = form.build(_tree("mh1_appraisal_v1_4"), folder=tpl.path.parent, edit=True)
    named = [b for b in blocks if {"10.000", "10.001", "10.002"} & set(b.fids)]
    assert len(named) == 3 and all("data-fid" in b.html for b in named)
    assert all(_text(b).startswith("Unit Interior:") for b in named)


def _vehicle_storage(key, tree=None, edit=False):
    blocks = [b for b in form.build(tree if tree is not None else _tree(key),
                                    folder=templates.get(key).path.parent, edit=edit)
              if b.section == "Vehicle Storage"]
    return " ".join(re.sub(r"<[^>]+>", " ", form.galley_html(blocks, edit)).split())


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_vehicle_storage_prints_no_storage_type_above_its_table(key):
    """B-1 p228: 13.000 displays "None" only when CarStorageType is "None";
    every D-1 sample sets the table straight under the tab."""
    assert _vehicle_storage(key).startswith("Vehicle Storage Storage Number of Parking Spaces")


def test_no_vehicle_storage_prints_none_alone():
    """B-1 p228 / Figure 13-1: "None", and neither the detail table nor the
    Apparent Defects subsection."""
    tree = _tree("sf1_appraisal_v1_4")
    subj = form.subject(form.Ctx(tree.getroot()))
    stores = list(subj.iter(f"{M}CAR_STORAGE"))
    for e in stores[1:]:
        e.getparent().remove(e)
    for c in list(stores[0]):
        stores[0].remove(c)
    detail = etree.SubElement(stores[0], f"{M}CAR_STORAGE_DETAIL")
    etree.SubElement(detail, f"{M}CarStorageType").text = "None"
    assert _vehicle_storage("sf1_appraisal_v1_4", tree) == "Vehicle Storage None"
    assert "Number of Parking Spaces" in _vehicle_storage("sf1_appraisal_v1_4", tree, edit=True)


STRUCTURE = ("Dwelling Exterior", "Unit Interior", "Outbuilding", "Manufactured Home",
             "Functional Obsolescence", "Vehicle Storage")


def _structure_order(key):
    return [b.section for b in _blocks(key) if b.kind == "tab" and b.visible
            and b.section.split(" - ")[0] in STRUCTURE]


def test_an_adu_in_an_outbuilding_follows_its_outbuilding():
    """B-1 p377: "Outbuilding ... - Unit Interior (repeat Unit Interior for
    each ADU ... in Outbuilding)"; p30; D-1 SF3."""
    assert _structure_order("sf3_appraisal_v1_4") == [
        "Dwelling Exterior", "Unit Interior - Primary Dwelling", "Functional Obsolescence",
        "Outbuilding - Standalone ADU", "Unit Interior - Standalone ADU - Cottage", "Vehicle Storage"]


def test_an_adu_in_the_dwelling_stays_with_the_dwelling():
    assert _structure_order("sf4_appraisal_v1_4") == [
        "Dwelling Exterior", "Unit Interior - Primary Dwelling", "Unit Interior - ADU",
        "Functional Obsolescence", "Vehicle Storage"]


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


def _heading_gaps(doc, start, heads=None):
    """{(heading, next line): distance between their tops} -- section tabs
    (white text) when ``heads`` is None, else the named headings."""
    out = {}
    for i in range(start, doc.page_count):
        ls = []
        for b in doc[i].get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                t = " ".join(s["text"] for s in ln["spans"]).strip()
                w = all(s["color"] == 0xffffff for s in ln["spans"] if s["text"].strip())
                if t:
                    ls.append((ln["bbox"][1], ln["bbox"][0], t, w))
        ls.sort()
        for n, (y, x, t, w) in enumerate(ls):
            hit = (t in heads) if heads else (w and "(continued)" not in t)
            nxt = next((r for r in ls[n + 1:] if r[0] > y + 3), None)
            # (a sales grid's white group rows sit 13-14 pt over their row:
            # those are not section tabs)
            if hit and x < 60 and nxt and (heads or nxt[0] - y > 18) and nxt[0] - y < 45:
                out.setdefault((t, nxt[2]), nxt[0] - y)
    return out


@needs_browser
def test_tabs_and_headings_sit_where_d1_sets_them(tmp_path):
    """T-1150, against SF1's official PDF, heading by heading (same heading,
    same line under it): a section tab's first row 24.4 pt under it (it was
    27.0), an H1 straight under a tab 28.1 pt (38.5), a contact H2's first
    row 15.3 pt (18.0)."""
    import statistics
    from harness import report_start
    pymupdf = pytest.importorskip("pymupdf")
    ours = _rendered("sf1_appraisal_v1_4", tmp_path)
    tpl = templates.get("sf1_appraisal_v1_4")
    gse, start = pymupdf.open(tpl.pdf), report_start(tpl.pdf)
    for heads, least in ((None, 10), (("Client/Lender", "Appraisal Management Company",
                                      "Significant Real Property Appraisal Assistance"), 1)):
        a, b = _heading_gaps(ours, 0, heads), _heading_gaps(gse, start, heads)
        both = [abs(a[k] - b[k]) for k in a.keys() & b.keys()]
        assert len(both) >= least and statistics.median(both) < 0.6, sorted(
            (k, round(a[k], 1), round(b[k], 1)) for k in a.keys() & b.keys())
    assert abs(a.get(("Client/Lender", "Company Name"), 0) - 15.3) < 0.6
