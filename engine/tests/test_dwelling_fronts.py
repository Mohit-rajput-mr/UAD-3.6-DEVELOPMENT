"""Each dwelling's own front photo, and a further one as an exhibit (E-167).

A-1 lists DwellingFront twice: the large photo atop Dwelling Exterior
(1400.0619, 8.000.1, no caption) and an exhibit captioned "Dwelling Front"
(1400.0638, 8.062.1).  Neither is linked to a dwelling, so the n-th is the
n-th dwelling's: D-1 2-4 prints 2-4_Dwelling2Front atop Building 2 (we
printed Building 1's there), and D-1 SF1 prints SF1_DwellingFront among its
exhibits (we dropped it).

Run:  python -m pytest -q engine/tests/test_dwelling_fronts.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from types import SimpleNamespace

from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, delivery, schema, templates
from uad.report import form

KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _dwelling_exterior(key):
    t = templates.get(key)
    tree = etree.parse(str(t.path))
    ctx = form.Ctx(tree.getroot(), None, t.path.parent, [])
    title = next(e["title"] for pg in form.form()["pages"] for e in pg["elements"]
                 if e["kind"] == "tab" and e["title"].startswith("Dwelling Exterior"))
    return tree, list(form.section_instances(ctx, title))


def _file(src: str, tree, folder: Path) -> str:
    """Which of the document's image files a data URI is."""
    for im in form._images(form.Ctx(tree.getroot(), None, folder, [])):
        if im["path"] is not None and form._data_uri(im["path"]) == src:
            return im["path"].name
    return ""


def test_dwellingfront_is_an_exhibit_category_too():
    assert form.image_categories()["DwellingFront"] == ("Dwelling Exterior", "Dwelling Front")


def test_each_building_shows_its_own_front():
    tree, copies = _dwelling_exterior("2_to_4_unit_appraisal_v1_4")
    folder = templates.get("2_to_4_unit_appraisal_v1_4").path.parent
    tops = [_file(form._photo_for(c, "Dwelling Exterior")[0], tree, folder) for c, _p in copies]
    assert tops == ["2-4_Dwelling1Front.png", "2-4_Dwelling2Front.png"]
    for c, _p in copies:                                   # neither is also an exhibit
        assert not any(e["category"] == "DwellingFront" for e in form._exhibits(c, "Dwelling Exterior"))


def test_a_second_front_of_one_dwelling_is_its_exhibit():
    tree, ((ctx, _p),) = _dwelling_exterior("sf1_appraisal_v1_4")
    folder = templates.get("sf1_appraisal_v1_4").path.parent
    assert _file(form._photo_for(ctx, "Dwelling Exterior")[0], tree, folder) == "SF1_SubjectProperty.png"
    fronts = [e for e in form._exhibits(ctx, "Dwelling Exterior") if e["category"] == "DwellingFront"]
    assert [(e["title"], _file(e["src"], tree, folder)) for e in fronts] == [
        ("Dwelling Front", "SF1_DwellingFront.png")]


def test_only_sf1_has_a_dwelling_front_exhibit():
    """D-1: SF1 prints "Dwelling Front" in its exhibits; no other sample does."""
    have = set()
    for key in KEYS:
        _tree, copies = _dwelling_exterior(key)
        if any(e["category"] == "DwellingFront" for c, _p in copies for e in form._exhibits(c, "Dwelling Exterior")):
            have.add(key)
    assert have == {"sf1_appraisal_v1_4"}


def test_the_appraisers_photo_replaces_only_the_first_buildings_front(tmp_path):
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (60, 40), "white").save(buf, "PNG")
    (tmp_path / "front.png").write_bytes(buf.getvalue())
    item = SimpleNamespace(media_id="m1", category="subject", filename="front.png", caption="",
                           section=0, comparable=0, provenance="")
    tree = etree.parse(str(templates.get("2_to_4_unit_appraisal_v1_4").path))
    out = delivery.build(tree, [item], tmp_path)
    subject = bind.subject(out.tree.getroot())
    fronts = [(i.findtext("{*}ImageFileLocationIdentifier") or "").split("\\")[-1]
              for i in subject.iter("{*}IMAGE") if i.findtext("{*}ImageCategoryType") == "DwellingFront"]
    assert fronts == ["front.png", "2-4_Dwelling2Front.png"]          # building 2 keeps its own
    assert schema.validate(out.tree) == []
