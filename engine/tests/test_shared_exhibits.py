"""One picture filed under several categories prints once, under every
category's header (T-127; B-1 p59, Image Data, Scenario 1).

D-1 MH1 prints "Site Influence - Water Frontage - View - Lake Virginia" over
the waterfront photo, which the XML files three times -- WaterFrontage,
SiteInfluence, View "Lake Virginia" -- all pointing at MH1_Waterfront.png.
The report printed three boxes with the bare category names.

Run:  python -m pytest -q engine/tests/test_shared_exhibits.py
"""
from __future__ import annotations

import html as H
import re
import sys
from functools import lru_cache
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import templates
from uad.report import form

ROOT = Path(__file__).resolve().parents[2] / "specs" / "official"
KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _titles(key: str, edit: bool = False) -> list[str]:
    tpl = templates.get(key)
    tree = etree.parse(str(tpl.path))
    page = form.galley_html(form.build(tree, folder=tpl.path.parent, edit=edit), edit=edit)
    return [re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()
            for m in re.finditer(r"<figure class='ex[^']*'><div class='cap'>(.*?)</div>", page)]


@pytest.mark.parametrize("key, printed, gone", [
    ("mh1_appraisal_v1_4", ["Site Influence - Water Frontage - View - Lake Virginia",
                            "Site Influence - View - Power Lines"], ["View - Lake Virginia"]),
    ("mh2_appraisal_v1_4", ["Property Access (Street Scene) - Site Influence - View"],
     ["Property Access (Street Scene)"]),
    ("condo2_appraisal_v1_4", ["Site Influence - View - Golf Course"], ["View - Golf Course"]),
    ("sf2_appraisal_v1_4", ["Property Access (Street Scene) - View"], ["Property Access (Street Scene)"]),
    ("sf4_appraisal_v1_4", ["Property Access (Street Scene)", "Site Influence - View - Residential"],
     ["View - Residential"]),
    ("2_to_4_unit_scenario_2_appraisal_v1_2",
     ["Property Access (Street Scene) - Site Influence - Busy Roadway, Residential - View - Residential"],
     ["Property Access (Street Scene)", "Map of Rental Comparables", "Map of GRM Comparables"]),
    # photos titled by what they are of
    ("mh2_appraisal_v1_4", ["Level 1 - Kitchen - Living Room"], ["Level 1 - Kitchen", "Level 1 - Living Room"]),
    ("sf1_appraisal_v1_4", ["Driveway - Garage"], ["Driveway", "Garage"]),
    ("sf3_appraisal_v1_4", ["Deck - Deck 1 and Deck 2"], ["Deck - Deck 1 and Deck 2 - Deck 1 and Deck 2"]),
    # one map of every comparable prints once, in the Sales Comparison Approach (B-1 Scenario 2)
    ("condo2_appraisal_v1_4", [], ["Map of Rental Comparables"]),
])
def test_as_d1_prints_it(key, printed, gone):
    titles = _titles(key)
    for t in printed:
        assert titles.count(t) == 1, (t, titles)
    for t in gone:
        assert t not in titles, (t, titles)


def test_the_headers_follow_b1s_exhibit_table():
    fids = form.image_fids()
    assert fids["NonResidentialUse"] < fids["PropertyAccess"] < fids["SiteInfluence"] \
        < fids["PermanentWaterfrontFeature"] < fids["WaterFrontage"] < fids["View"]


def test_the_editor_keeps_a_box_per_image():
    """Each IMAGE keeps its own category, caption and remove in the editor."""
    titles = _titles("mh1_appraisal_v1_4", edit=True)
    assert "Site Influence - Water Frontage - View - Lake Virginia" not in titles


def _norm(text: str) -> str:
    # D-1 sets apostrophes curly ("Retailer’s Invoice"); the words are what is compared
    return re.sub(r"\s+", " ", text.replace("\u2019", "'").replace("\u2013", "-")).strip()


@lru_cache(maxsize=16)
def _d1_lines(key: str) -> str:
    import pymupdf
    if key.startswith("2_to_4_unit_scenario"):
        pattern = "2-to4-unit_Scenario_2_Appraisal*.pdf"
    elif key.startswith("2_to_4"):
        pattern = "2-to4-unit_Appraisal*.pdf"
    else:
        pattern = key.split("_")[0].replace("condo", "Condo").replace("coop", "Coop").upper() \
            if key.startswith(("sf", "mh")) else key.split("_")[0].capitalize()
        pattern += "_Appraisal*.pdf"
    hits = sorted(ROOT.rglob(pattern))
    if not hits:
        pytest.skip(f"D-1 PDF for {key} not in specs/official")
    doc = pymupdf.open(str(hits[0]))
    return " | " + " ".join(_norm(line) + " |" for page in doc
                              for line in page.get_text().splitlines() if line.strip())


@pytest.mark.parametrize("key", KEYS)
def test_every_exhibit_title_is_one_d1_prints(key):
    """Each title over a picture stands as its own line (or wrapped lines)
    in the official PDF."""
    lines = _d1_lines(key)
    missing = [t for t in _titles(key)
               if not re.search(r"\| " + re.sub(r"\\ ", r"[ |]+", re.escape(_norm(t))) + r" \|", lines)]
    assert not missing, missing
