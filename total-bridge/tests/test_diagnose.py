"""The before-import diagnostics, checked against the official D-1 samples.

A check that faults a published sample is a broken check, and a check never
seen to fire is untested: each check here runs on every sample (no false
finding) and on a mutated copy (it fires).

    python -m pytest tests/test_diagnose.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "engine"))

from bridge import diagnose                  # noqa: E402
from uad.spec.paths import specs_root        # noqa: E402


def _samples() -> dict[str, Path]:
    seen: dict[str, Path] = {}
    for p in sorted(specs_root().rglob("*_Appraisal_v1.*.xml")):
        seen.setdefault(p.name.split("_Appraisal_")[0], p)
    return seen


SAMPLES = _samples()


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_samples_state_every_switch_totals_writer_reads(name):
    # conditionally required switches may be absent (info); a required one may not
    unstated = [d for d in diagnose.before(SAMPLES[name])
                if "does not state" in d.message and d.severity != "info"]
    assert unstated == [], [d.message for d in unstated]


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_every_sample_is_described(name):
    info = [d for d in diagnose.before(SAMPLES[name]) if d.message.startswith("package is ")]
    assert len(info) == 1 and "no legacy form" not in info[0].message or name in ("Condo2", "MH2")


def test_an_unstated_switch_is_reported(tmp_path):
    root = etree.parse(str(SAMPLES["SF1"])).getroot()
    gone = [e for e in root.iter() if isinstance(e.tag, str) and etree.QName(e).localname == "CostApproachIndicator"]
    assert gone, "SF1 states CostApproachIndicator"
    for e in gone:
        e.getparent().remove(e)
    path = tmp_path / "sf1-no-cost.xml"
    path.write_bytes(etree.tostring(root))
    hits = [d for d in diagnose.before(path) if d.data_point == "CostApproachIndicator"]
    assert len(hits) == 1
    assert hits[0].field == "CHECK_COST_APPROACH_ENABLE" and "CHECK_COST_APPROACH_DISABLE=X" in hits[0].message
