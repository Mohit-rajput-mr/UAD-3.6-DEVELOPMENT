"""Property-type profiles: one report engine, many kinds of property.

UAD 3.6 replaced the old form numbers with data — the property's own
characteristics decide which sections the report carries.  A single-family
detached report and a co-operative report come off the same engine and differ
only in what the data says.

The profiles here are derived from Appendix D-1's eleven worked scenarios
rather than written by hand: each scenario's XML says what kind of property it
is, and its PDF says which sections that kind of property prints.  Running
``python -m uad.report.profiles`` rebuilds ``engine/spec/profiles.json`` from
the samples.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import model as model_mod

ROOT = Path(__file__).resolve().parent.parent.parent.parent
SAMPLES = ROOT / "_ref" / "usecases"
TARGET = ROOT / "engine" / "spec" / "profiles.json"

# The kinds of property the URAR covers.
SINGLE_FAMILY = "SingleFamily"
CONDOMINIUM = "Condominium"
COOPERATIVE = "Cooperative"
MANUFACTURED = "ManufacturedHome"
MULTI_UNIT = "TwoToFourUnit"
PUD = "PlannedUnitDevelopment"

# Every section heading the URAR can print, used to read a sample's PDF.
KNOWN_SECTIONS = [
    "Summary", "Assignment Information", "Subject Property", "Site",
    "Disaster Mitigation", "Energy Efficient and Green Features", "Sketch",
    "Dwelling Exterior", "Manufactured Home", "Unit Interior",
    "Functional Obsolescence", "Outbuilding", "Vehicle Storage",
    "Subject Property Amenities", "Overall Quality and Condition",
    "Highest and Best Use", "Market", "Project Information",
    "Subject Listing Information", "Sales Contract",
    "Prior Sale and Transfer History", "Sales Comparison Approach",
    "Rental Information", "Income Approach", "Cost Approach", "Reconciliation",
    "Revision History", "Supplemental Information", "Certifications",
]


@dataclass
class Profile:
    """What a given kind of property prints."""

    property_type: str
    sections: list[str] = field(default_factory=list)
    scenarios: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "property_type": self.property_type,
            "sections": self.sections,
            "scenarios": self.scenarios,
        }


# ------------------------------------------------------------- classifying
def _flag(node: Any, name: str) -> bool:
    if not isinstance(node, dict):
        return False
    value = node.get(name)
    if isinstance(value, dict):
        value = value.get("#text")
    return str(value).lower() == "true"


def classify(data: dict) -> str:
    """Which kind of property this report describes.

    The order matters: a co-operative interest is also held in a project, and a
    manufactured home may sit in a PUD, so the most specific test wins.
    """
    subject = model_mod.subject(data) or {}
    detail = subject.get("PROPERTY_DETAIL", {})
    detail = detail[0] if isinstance(detail, list) else detail

    # A property held in a project says so in PROJECT_DETAIL; that is the
    # authority, not any indicator on the property itself.
    project = subject.get("PROJECT", {})
    project = project[0] if isinstance(project, list) else project
    project_detail = project.get("PROJECT_DETAIL", {}) if isinstance(project, dict) else {}
    project_detail = (
        project_detail[0] if isinstance(project_detail, list) else project_detail
    )
    structure = project_detail.get("ProjectLegalStructureType") if project_detail else None
    if isinstance(structure, dict):
        structure = structure.get("#text")

    if structure == "Cooperative":
        return COOPERATIVE
    if structure in ("Condominium", "Condop"):
        return CONDOMINIUM

    improvements = subject.get("IMPROVEMENTS", {}).get("IMPROVEMENT", [])
    for improvement in improvements if isinstance(improvements, list) else [improvements]:
        if not isinstance(improvement, dict):
            continue
        structure = improvement.get("STRUCTURE", {})
        methods = structure.get("CONSTRUCTION_METHODS", {}).get("CONSTRUCTION_METHOD", [])
        for method in methods if isinstance(methods, list) else [methods]:
            if isinstance(method, dict):
                value = method.get("ConstructionMethodType")
                if isinstance(value, dict):
                    value = value.get("#text")
                if value == "Manufactured":
                    return MANUFACTURED

    units = detail.get("LivingUnitExcludingADUCount")
    if isinstance(units, dict):
        units = units.get("#text")
    try:
        if int(units) > 1:
            return MULTI_UNIT
    except (TypeError, ValueError):
        pass

    if _flag(detail, "PUDIndicator"):
        return PUD
    return SINGLE_FAMILY


# ---------------------------------------------------------------- learning
def _sections_in(pdf_path: Path) -> list[str]:
    """Which section tabs a reference report actually prints."""
    import pymupdf

    document = pymupdf.open(str(pdf_path))
    found: set[str] = set()
    for page in document:
        for line in page.get_text().splitlines():
            stripped = line.strip()
            if stripped in KNOWN_SECTIONS:
                found.add(stripped)
    document.close()
    return [s for s in KNOWN_SECTIONS if s in found]


def learn() -> dict[str, Profile]:
    """Build a profile per property type from the worked scenarios."""
    profiles: dict[str, Profile] = {}

    for folder in sorted(SAMPLES.iterdir()):
        if not folder.is_dir():
            continue
        xml = next(folder.glob("*.xml"), None)
        pdf = next(folder.glob("*.pdf"), None)
        if not xml or not pdf:
            continue

        data = model_mod.parse(str(xml))
        kind = classify(data)
        sections = _sections_in(pdf)

        profile = profiles.setdefault(kind, Profile(kind))
        profile.scenarios.append(folder.name)
        # A section belongs to the profile if any scenario of that kind shows it.
        for name in sections:
            if name not in profile.sections:
                profile.sections.append(name)
        profile.sections.sort(key=KNOWN_SECTIONS.index)
    return profiles


@lru_cache(maxsize=1)
def profiles() -> dict[str, dict]:
    if not TARGET.exists():
        return {}
    with open(TARGET, encoding="utf-8") as fh:
        return json.load(fh)


def sections_for(data: dict) -> list[str]:
    """The sections this report should carry, by the kind of property it is."""
    profile = profiles().get(classify(data))
    return list(profile["sections"]) if profile else []


def main() -> None:
    learned = learn()
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(
        json.dumps({k: v.as_dict() for k, v in learned.items()}, indent=1),
        encoding="utf-8",
    )
    print(f"{len(learned)} property-type profiles learned from the reference scenarios\n")
    for kind, profile in learned.items():
        print(f"  {kind:20s} {len(profile.sections):>2} sections  "
              f"from {', '.join(profile.scenarios)}")


if __name__ == "__main__":
    main()
