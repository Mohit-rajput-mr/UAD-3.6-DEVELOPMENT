"""Golden-sample regression: the shape of every scenario, held still.

The harness asks whether a build is *correct*.  This asks whether it is the
*same* -- a structural fingerprint of each of the twelve D-1 scenarios, stored
beside this file, so that a change which quietly drops a grid row or a whole
section is caught by a diff rather than by somebody noticing months later.

The fingerprint is deliberately structural, not visual: counts and names, the
things that should only move when someone means to move them.  Pixel fidelity
is a separate question and `tests/span_diff.py` answers it.

When a change is intended, regenerate and read the diff before committing it:

    UAD_GOLDEN_UPDATE=1 python -m pytest tests/test_golden.py -q
"""
import json
import os
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import compliance, templates  # noqa: E402
from uad.report import comparables, urar  # noqa: E402

BASELINE = Path(__file__).resolve().parent / "golden_baseline.json"
UPDATING = bool(os.environ.get("UAD_GOLDEN_UPDATE"))
ALL = [t.key for t in templates.catalogue()]


def fingerprint(key: str) -> dict:
    """What this scenario is made of, in numbers that should not drift."""
    tree = etree.parse(str(templates.get(key).path))
    sections = urar.build(tree)
    findings = compliance.evaluate(tree)
    out = {
        "sections": [s.number for s in sections],
        "section_count": len(sections),
        "fatal": sum(1 for f in findings
                     if f.status == compliance.FINDING
                     and f.severity == compliance.FATAL),
        "warning": sum(1 for f in findings
                       if f.status == compliance.FINDING
                       and f.severity == compliance.WARNING),
        "review": sum(1 for f in findings if f.status == compliance.REVIEW),
    }
    for kind in comparables.SHEETS:
        grids = comparables.build(tree, kind)
        out[f"{kind}_blocks"] = len(grids)
        out[f"{kind}_comparables"] = sum(len(g.comparables) for g in grids)
        out[f"{kind}_rows"] = [len(g.rows) for g in grids]
    return out


@pytest.fixture(scope="session")
def baseline() -> dict:
    if UPDATING or not BASELINE.exists():
        built = {key: fingerprint(key) for key in ALL}
        BASELINE.write_text(json.dumps(built, indent=1, sort_keys=True) + "\n",
                            encoding="utf-8")
        return built
    return json.loads(BASELINE.read_text(encoding="utf-8"))


@pytest.mark.parametrize("key", ALL)
def test_the_scenario_still_has_the_shape_it_had(key, baseline):
    if key not in baseline:
        pytest.skip(f"{key} is not in the baseline yet")
    now, was = fingerprint(key), baseline[key]
    drifted = {k: (was.get(k), now.get(k))
               for k in set(was) | set(now) if was.get(k) != now.get(k)}
    assert not drifted, (
        f"{key} changed shape: {drifted}. If that was intended, regenerate "
        "with UAD_GOLDEN_UPDATE=1 and read the diff.")


def test_the_baseline_covers_every_scenario(baseline):
    assert set(baseline) >= set(ALL), (
        f"no baseline for {sorted(set(ALL) - set(baseline))}")


# ------------------------------------------------------------------- the PDF
# The deliverable has to be a first-generation PDF: real text in real embedded
# fonts, not a picture of a report.  Chromium will silently turn a CFF web font
# into unnamed Type3 glyphs, which still *looks* right and is no longer text.
def test_the_pdf_is_text_not_a_picture(tmp_path):
    import pymupdf

    from uad.report import flow

    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    out = tmp_path / "appraisal.pdf"
    flow.to_pdf(flow.build(tree, screen=False), out)

    doc = pymupdf.open(out)
    assert len(doc) > 1
    page = doc[0]
    assert len(page.get_text().strip()) > 500, (
        "the first page carries almost no extractable text")
    assert not page.get_images(full=True), (
        "the first page contains an image -- the report was rasterised")

    kinds = {f[2] for f in page.get_fonts(full=True)}
    assert "Type3" not in kinds, (
        f"Chromium emitted Type3 glyphs instead of an embedded font: {kinds}")
    names = {f[3] for f in page.get_fonts(full=True)}
    assert any("Myriad" in n for n in names), (
        f"the report's own typeface is not embedded: {names}")


def test_the_summary_display_lines_match_the_sample_width(tmp_path):
    """MyriadPro-Black is not available, so the two Summary display lines are
    Bold tracked out to the width the sample sets them at.  The tracking is
    computed from what our Bold renders, so if the font build changes the
    figure behind it goes stale -- this is what notices."""
    import pymupdf

    from uad.report import flow, fonts

    tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
    out = tmp_path / "summary.pdf"
    flow.to_pdf(flow.build(tree, screen=False), out)

    spans = {}
    for block in pymupdf.open(out)[0].get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for span in line["spans"]:
                spans[span["text"].strip()] = span["bbox"][2] - span["bbox"][0]

    for code, sub in fonts.BLACK_SUBSTITUTE.items():
        drawn = spans.get(sub.text.strip())
        if drawn is None:
            continue
        assert abs(drawn - sub.target_pt) < 1.0, (
            f"{code} renders {drawn:.2f}pt against the sample's "
            f"{sub.target_pt:.2f}pt; the Bold width behind its tracking "
            f"({sub.bold_pt:.2f}pt) no longer matches what is drawn")
