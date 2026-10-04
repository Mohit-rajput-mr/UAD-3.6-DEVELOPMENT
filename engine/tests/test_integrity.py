"""The integrity checks, validated against the published samples first.

A check that faults one of the GSEs' own documents is a broken check, not a
finding, so every rule here is run across all twelve D-1 scenarios before it is
allowed to block anybody's export.
"""
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import integrity, templates  # noqa: E402


class FakeMedia:
    def __init__(self, filename, comparable=0, comp_key="",
                 provenance="appraiser"):
        self.filename = filename
        self.comparable = comparable
        self.comp_key = comp_key
        self.provenance = provenance


ALL = [t.key for t in templates.catalogue()]


@pytest.mark.parametrize("key", ALL)
def test_no_published_sample_is_faulted(key):
    """The twelve official scenarios must come back clean."""
    tree = etree.parse(str(templates.get(key).path))
    fatal = [f for f in integrity.check_consistency(tree, [])
             if f.severity == integrity.FATAL]
    assert not fatal, [f"{f.code}: {f.message} {f.detail}" for f in fatal]


@pytest.mark.parametrize("key", ALL)
def test_a_published_sample_agrees_with_its_own_rendering(key):
    from uad.report import flow

    tree = etree.parse(str(templates.get(key).path))
    html = flow.build(tree, screen=False)
    fatal = [f for f in integrity.check_consistency(tree, [], html)
             if f.severity == integrity.FATAL]
    assert not fatal, [f"{f.code}: {f.message} {f.detail}" for f in fatal]


# ----------------------------------------------------- the checks do detect
def test_a_template_image_is_refused():
    found = integrity.check_assets([FakeMedia("gse.jpg", provenance="template")])
    assert [f.code for f in found] == ["SAMPLE-ASSET"]
    assert found[0].severity == integrity.FATAL


def test_the_appraisers_own_image_is_not_refused():
    assert integrity.check_assets([FakeMedia("mine.jpg")]) == []


def test_a_photo_of_a_deleted_comparable_is_caught():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    found = integrity.check_consistency(
        tree, [FakeMedia("ghost.jpg", comparable=1, comp_key="PROPERTY_GONE")])
    assert "ORPHAN-PHOTO" in [f.code for f in found]


def test_a_photo_numbered_past_the_last_comparable_is_caught():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    found = integrity.check_consistency(tree, [FakeMedia("x.jpg", comparable=99)])
    assert "ORPHAN-PHOTO" in [f.code for f in found]


def test_a_photo_on_the_wrong_comparable_is_caught():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    root = tree.getroot()
    from uad.report import comparables
    labels = comparables.labels(root, "SalesComparable")
    found = integrity.check_consistency(
        tree, [FakeMedia("swap.jpg", comparable=1, comp_key=labels[1])])
    assert "PHOTO-MISNUMBERED" in [f.code for f in found]


def test_an_address_the_report_does_not_print_is_caught():
    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    found = integrity.check_consistency(tree, [], "<html>nothing here</html>")
    assert "ADDRESS-MISMATCH" in [f.code for f in found]


# ------------------------------------------------------------------- package
GOOD = ["appraisal.pdf", "mismo.xml", "manifest.json", "Images/front.jpg"]


def test_a_well_formed_package_passes():
    media = [FakeMedia("front.jpg")]
    assert [f for f in integrity.check_package(GOOD, media)
            if f.severity == integrity.FATAL] == []


@pytest.mark.parametrize("stray", [
    "editor.json", "cases.db", "mismo.xml.bak", "build.log",
    "__pycache__/x.pyc", ".DS_Store", "engine/app/api.py",
])
def test_working_files_never_ship(stray):
    found = integrity.check_package(GOOD + [stray], [FakeMedia("front.jpg")])
    assert "STRAY-FILE" in [f.code for f in found], stray


def test_a_missing_deliverable_is_fatal():
    found = integrity.check_package(["mismo.xml"], [])
    assert "MISSING-FILE" in [f.code for f in found]


def test_an_image_nobody_referenced_is_fatal():
    found = integrity.check_package(GOOD + ["Images/stale.jpg"],
                                    [FakeMedia("front.jpg")])
    assert "UNKNOWN-IMAGE" in [f.code for f in found]
