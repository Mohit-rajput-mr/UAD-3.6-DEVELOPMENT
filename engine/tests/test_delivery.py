"""The UCDP package against Appendix B-1 pp 56-61 and 69-73.

Run on the official D-1 samples first: a delivery check that faults a
published sample's own image wiring is a broken check.
"""
from __future__ import annotations

import base64
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from uad import bind, delivery, schema, templates  # noqa: E402

M = f"{{{bind.MISMO}}}"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")


@dataclass
class Item:
    media_id: str
    category: str
    filename: str
    caption: str = ""
    section: int = 0
    comparable: int = 0
    provenance: str = "appraiser"


@pytest.fixture(autouse=True)
def vendor(monkeypatch, tmp_path):
    (tmp_path / "vendor.json").write_text(json.dumps(
        {"vendor_name": "Test Vendor", "product_name": "Test Product"}))
    monkeypatch.setattr(delivery, "CONFIG", tmp_path)


def _sample(key="sf1_appraisal_v1_4"):
    tpl = templates.get(key)
    return tpl, etree.parse(str(tpl.path))


def test_limits_come_from_a1():
    assert "image/jpeg" in delivery.image_mime_types()
    assert "image/png" in delivery.image_mime_types()
    assert delivery.location_max() == 50
    assert delivery.caption_max() == 100


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_a_published_sample_ships_with_its_own_images(key):
    """With every referenced image supplied, a sample raises no image fault
    and still validates once the PDF reference and vendor are written."""
    tpl, tree = _sample(key)
    folder = tpl.path.parent / "Images"
    items = []
    refs = {delivery.name_of(i.findtext(f"{M}ImageFileLocationIdentifier", ""))
            for i in tree.getroot().iter(f"{M}IMAGE")}
    for n, name in enumerate(sorted(refs)):
        items.append(Item(f"m{n}", "other", name))
    built = delivery.build(tree, [], folder, template_names=set())
    missing = {f.detail for f in built.faults if f.code == "IMAGE-NOT-SUPPLIED"}
    on_disk = {p.name for p in folder.iterdir()} if folder.is_dir() else set()
    assert missing <= refs - on_disk or missing == refs, missing
    assert not [f for f in built.faults if f.code == "VENDOR-UNSET"]
    assert schema.validate(built.tree) == [], key


def test_the_pdf_reference_names_the_pdf_that_ships():
    _tpl, tree = _sample()
    built = delivery.build(tree, [], Path("."))
    url = built.tree.getroot().find(f".//{M}FOREIGN_OBJECT/{M}ObjectURL").text
    assert url == "\\\\appraisal.pdf"      # B-1: \\ is the root of the ZIP


def test_sample_vendor_is_replaced():
    _tpl, tree = _sample()
    built = delivery.build(tree, [], Path("."))
    root = built.tree.getroot()
    assert root.findtext(f".//{M}ValuationSoftwareVendorName") == "Test Vendor"
    assert root.findtext(f".//{M}ValuationSoftwareProductName") == "Test Product"
    assert len(list(root.iter(f"{M}VALUATION_SOFTWARE_SYSTEM"))) == 1


def test_vendor_must_be_configured(monkeypatch, tmp_path):
    monkeypatch.setattr(delivery, "CONFIG", tmp_path / "none")
    _tpl, tree = _sample()
    assert any(f.code == "VENDOR-UNSET" for f in delivery.build(tree, [], Path(".")).fatal)


def test_appraiser_photos_become_image_containers(tmp_path):
    """B-1: every image in Images is referenced by an IMAGE in the XML, with
    the category its place on the report calls for."""
    _tpl, tree = _sample()
    for name in ("front.png", "comp2.png", "swale.png"):
        (tmp_path / name).write_bytes(PNG)
    media = [Item("a", "subject", "front.png", section=8),
             Item("b", "comparable", "comp2.png", section=22, comparable=2),
             Item("c", "other", "swale.png", caption="Drainage Swale", section=4)]
    built = delivery.build(tree, media, tmp_path)
    root = built.tree.getroot()
    images = {(i.findtext(f"{M}ImageCategoryType"), delivery.name_of(i.findtext(f"{M}ImageFileLocationIdentifier")),
               i.findtext(f"{M}ImageCaptionCommentDescription"))
              for i in root.iter(f"{M}IMAGE")}
    assert ("PropertyPhoto", "front.png", None) in images
    assert ("DwellingFront", "front.png", None) in images
    assert ("SiteExhibit", "swale.png", "Drainage Swale") in images
    assert ("PropertyPhoto", "comp2.png", None) in images
    assert set(built.images) == {"front.png", "comp2.png", "swale.png"}
    assert schema.validate(built.tree) == []
    # the sample pictures the new photos replaced are no longer referenced
    names = {n for _c, n, _k in images}
    assert "SF1_SubjectProperty.png" not in names and "SF1_Comp2.png" not in names


def test_sample_pictures_still_referenced_are_fatal(tmp_path):
    _tpl, tree = _sample()
    built = delivery.build(tree, [], tmp_path, template_names={"SF1_Garage.png"})
    assert any(f.code == "SAMPLE-IMAGE" and f.detail == "SF1_Garage.png" for f in built.fatal)


def test_a_replacement_photo_takes_the_documents_own_image_box(tmp_path):
    _tpl, tree = _sample()
    (tmp_path / "street.jpg").write_bytes(PNG)
    media = [Item("s", "other", "street.jpg", caption="Street", section=4)]
    built = delivery.build(tree, media, tmp_path,
                           fills={"\\\\Images\\SF1_PropertyAccess.png": "s"})
    access = [i for i in built.tree.getroot().iter(f"{M}IMAGE")
              if i.findtext(f"{M}ImageCategoryType") == "PropertyAccess"]
    assert access and delivery.name_of(access[0].findtext(f"{M}ImageFileLocationIdentifier")) == "street.jpg"
    assert access[0].findtext(f"{M}MIMETypeIdentifier") == "image/jpeg"


def test_limits_are_enforced(tmp_path):
    _tpl, tree = _sample()
    long_name = "x" * 45 + ".png"
    for name in (long_name, "plan.pdf"):
        (tmp_path / name).write_bytes(PNG)
    media = [Item("a", "other", long_name, section=4), Item("b", "other", "plan.pdf", section=4)]
    codes = {f.code for f in delivery.build(tree, media, tmp_path).fatal}
    assert {"IMAGE-NAME-LENGTH", "IMAGE-TYPE"} <= codes
    assert delivery.check_size(delivery.MAX_BYTES + 1)
