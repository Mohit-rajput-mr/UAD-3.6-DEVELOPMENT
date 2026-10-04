"""Detection checked against the twelve official D-1 samples.

The oracle is independent of the code under test: each sample's name says what
the GSEs built it as (SF, Condo, Coop, MH, 2- to 4-unit), and the two samples
with no legacy form are ones the GSE mapping itself lists as atypical -- Condo2
is a site condominium appraised by desktop, MH2 a manufactured home with an
additional construction method.

    python -m pytest tests/test_detect.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))

from bridge import detect                    # noqa: E402
from uad.spec.paths import specs_root        # noqa: E402

EXPECTED = {
    "SF1": ["1004 (70)"], "SF2": ["1004 (70)"], "SF3": ["1004 (70)"], "SF4": ["1004 (70)"],
    "SF5": ["1004 (70)"],
    "Condo1": ["1073 Hybrid (465H)"],
    "Condo2": [],                            # site condominium, desktop: atypical
    "Coop1": ["2090"],
    "MH1": ["1004C (70B)"],
    "MH2": [],                               # manufactured + site built: atypical
    "2- to 4-unit": ["1025 (72)"], "2- to 4-unit_Scenario_2": ["1025 (72)"],
}


def _samples() -> dict[str, Path]:
    seen: dict[str, Path] = {}
    for p in sorted(specs_root().rglob("*_Appraisal_v1.*.xml")):
        seen.setdefault(p.name.split("_Appraisal_")[0], p)
    return seen


SAMPLES = _samples()


def test_all_twelve_samples_present():
    assert set(SAMPLES) == set(EXPECTED)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_legacy_form_of_each_sample(name):
    found = detect.drivers_from_xml(SAMPLES[name])
    assert detect.legacy(found)["forms"] == EXPECTED[name], found.as_text()


def test_every_driver_word_resolves_to_an_enumeration():
    for d in detect.drivers():
        for word, enum in d["enumerations"].items():
            assert enum, f"{d['label']}: {word!r} has no A-1 enumeration"


def test_no_legacy_form_names_its_nearest_forms():
    lg = detect.legacy(detect.drivers_from_xml(SAMPLES["MH2"]))
    assert lg["nearest"] and "Construction Method" in lg["nearest"][0]["differs"]


def test_a_highrise_unit_is_not_a_manufactured_home():
    # Coop1: no construction method (it "does not apply" to a high-rise)
    lg = detect.legacy(detect.drivers_from_xml(SAMPLES["Coop1"]))
    assert lg["forms"] == ["2090"] and lg["atypical"] is None
