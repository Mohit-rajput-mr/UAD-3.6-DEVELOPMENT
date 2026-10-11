"""What a section B-1 leaves out of this report is left out of the delivered
file too (T-1205): HOA dues typed before a house turned out not to be in a PUD
shipped H-1 UAD1575 as a fatal finding while the Review Master only listed it.

Validated against the twelve D-1 samples first: none loses a value.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, delivery, edit, optional_sections, templates  # noqa: E402
from uad.report import form  # noqa: E402

SAMPLES = [t.key for t in templates.catalogue()]


@pytest.mark.parametrize("key", SAMPLES)
def test_no_official_sample_loses_a_value(key):
    root = templates.load(key).getroot()
    assert delivery.hidden_values(root) == []


def _hidden_only_point(root):
    """A field of a section this report leaves out whose data point no shown
    section asks for."""
    ctx = form.Ctx(root)
    off = [n for _i, n in bind.SECTIONS if form.section_shown(ctx, n) is False]
    number = {str(i): n for i, n in bind.SECTIONS}
    keep = {dp["mismo"] for fid, e in form._fields().items() if number.get(fid.split(".")[0]) not in off
            for dp in e.get("data_points") or [] if dp.get("mismo")}
    for name in off:
        if name in form.switch_sections():
            continue
        for fid, dp in optional_sections._points(name):
            if dp["mismo"] not in keep and not bind.is_commentary(dp) and "PROPERTIES/PROPERTY/" in dp.get("xpath", "") \
                    and (dp.get("format_type") or "").lower() in ("string", "amount", "count", ""):
                return name, fid, dp
    return None


@pytest.mark.parametrize("key", ["2_to_4_unit_appraisal_v1_4", "sf1_appraisal_v1_4"])
def test_a_value_left_in_a_hidden_section_is_not_delivered(key):
    tree = templates.load(key, blank=True)
    found = _hidden_only_point(tree.getroot())
    assert found, "no hidden-only field on this sample"
    section, fid, dp = found
    value = "7" if (dp.get("format_type") or "").lower() in ("amount", "count") else "Left behind"
    edit.write(tree, fid, value, data_point=dp["mismo"])
    M = f"{{{bind.MISMO}}}"
    assert value in [e.text for e in tree.getroot().iter(f"{M}{dp['mismo']}")], (section, fid)
    shipped = delivery.as_delivered(tree)
    assert value not in [e.text for e in shipped.getroot().iter(f"{M}{dp['mismo']}")], (section, fid)
    # the editor's copy keeps it: the section comes back with it if the report changes again
    assert value in [e.text for e in tree.getroot().iter(f"{M}{dp['mismo']}")]
