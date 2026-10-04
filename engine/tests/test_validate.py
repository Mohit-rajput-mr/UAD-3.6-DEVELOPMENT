"""The validator must pass reports that are known to be good.

A validator that flags correct work is worse than none, so this pins its
precision against the official GSE use cases.  The one expected finding is a
genuine omission in the reference files themselves, not a validator defect.
"""
from __future__ import annotations

import glob
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))

from uad import model, spec_loader, validate  # noqa: E402

# Every published reference report should validate clean.  Any entry here is a
# genuine omission in the reference file itself, not a validator defect.
KNOWN_OMISSIONS: dict[str, set[str]] = {}


def _gse_reports() -> list[str]:
    return sorted(glob.glob(str(ROOT / "_ref/usecases/*_Appraisal/*.xml")))


@pytest.mark.parametrize("path", _gse_reports(), ids=lambda p: os.path.basename(p))
def test_reference_reports_have_no_unexpected_fatals(path):
    report = validate.run(model.parse(path), spec=spec_loader.load())
    stem = os.path.basename(path).split("_v1.")[0]
    allowed = KNOWN_OMISSIONS.get(stem, set())
    unexpected = [f for f in report.fatal if f.rule_id not in allowed]
    assert not unexpected, "\n".join(f.message for f in unexpected[:5])


def test_validator_detects_a_removed_required_field():
    """Deleting a required data point must produce a fatal finding."""
    data = model.parse(_gse_reports()[0])
    address = model.get(data, f"{model.ANALYSIS_PATH}/PROPERTIES/PROPERTY")
    subject = address[0] if isinstance(address, list) else address
    subject["ADDRESS"].pop("CityName", None)

    report = validate.run(data, spec=spec_loader.load())
    assert any(f.data_point == "CityName" for f in report.fatal)
