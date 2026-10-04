"""Conformance against a real UAD 3.6 report produced by authenticated software.

Every other test in this suite measures us against the specification or against
the twelve Appendix D-1 samples.  Those are written by the people who wrote the
standard, which makes them necessary and not sufficient: they exercise the
standard as documented, not the standard as shipped.

``_work/reference/urar_18_north`` is a delivery package for 18 North St,
Bedford Hills -- MISMO XML, the PDF and forty-two images -- exported by
certified UAD 3.6 software from a real assignment.  It is the only artefact in
this project that says what the standard looks like in practice, so it is the
one that decides whether we can read what the industry actually produces.

Three things it has already caught, each of which had passed every other test:

* imported images came back out as ``\\Images\\name`` where B-1 packages them
  as ``\\\\Images\\name``, so a report that arrived from another vendor left
  with all forty-two of its image locations rewritten;
* the editor offered eight of the thirteen party roles A-1 defines, and could
  not file an image as a Sales Comparable Map at all, because enumerations
  reached a field only from the one A-1 row written against it;
* forty-four data points A-1 marks "Does Not Display" -- thirteen of them
  Required -- were absent from the field model, so the delivered XML did not
  carry them.

If this file is not on disk the tests skip rather than fail: it is real client
data, not a fixture that can be regenerated.
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api                                            # noqa: E402
from app.cases import Store                                    # noqa: E402
from uad import schema, uadmap                                 # noqa: E402

REFERENCE = Path(__file__).resolve().parents[2] / "_work" / "reference" / "urar_18_north"
MISMO = REFERENCE / "mismo.xml"
PACKAGE = REFERENCE / "package.zip"

needs_reference = pytest.mark.skipif(
    not MISMO.exists(), reason=f"authenticated reference not on disk ({REFERENCE})")


def values(source) -> collections.Counter:
    """Every value the document carries, as (data point, text) with counts."""
    root = etree.fromstring(source) if isinstance(source, bytes) else source.getroot()
    found: collections.Counter = collections.Counter()
    for node in root.iter():
        if isinstance(node.tag, str) and (node.text or "").strip():
            found[(etree.QName(node).localname, node.text.strip())] += 1
    return found


@pytest.fixture
def imported(tmp_path, monkeypatch):
    """The reference package, brought in through the route the editor uses."""
    from fastapi.testclient import TestClient

    from app.main import app

    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    with TestClient(app) as client:
        __import__("app.access").access.sign_in(client)
        sent = PACKAGE if PACKAGE.exists() else MISMO
        reply = client.post("/api/import",
                            files={"files": (sent.name, sent.read_bytes(),
                                             "application/zip" if sent.suffix == ".zip"
                                             else "text/xml")})
        assert reply.status_code == 200, reply.text[:400]
        body = reply.json()
        yield client, body["case"]["case_id"], body["report"], store
    store.conn.close()


@needs_reference
def test_a_real_uad36_file_validates_against_the_subschema():
    """If the GSE subschema faults a file certified software produced, the
    check is wrong -- the same rule this project applies to the D-1 samples."""
    errors = schema.validate(MISMO.read_bytes())
    assert errors == [], [str(e) for e in errors[:5]]


@needs_reference
def test_every_value_in_a_real_file_survives_import_and_export(imported):
    """XML in, XML out, value for value.

    Not 'most of it' and not 'the ones we have a field for': a document that
    loses a value on the way through is a document an appraiser cannot be
    handed back.
    """
    client, case_id, _report, _store = imported
    before = values(MISMO.read_bytes())
    after = values(client.get(f"/api/cases/{case_id}/mismo.xml").content)

    lost, gained = before - after, after - before
    assert not lost, sorted(f"{n}={v!r}" for (n, v) in lost)[:20]
    assert not gained, sorted(f"{n}={v!r}" for (n, v) in gained)[:20]


@needs_reference
def test_every_picture_in_a_real_package_is_placed(imported):
    """Forty-two images, each named by an IMAGE block, each filed where the
    report shows it.  A picture the import cannot find is a hole in the PDF."""
    _client, case_id, report, store = imported
    if not PACKAGE.exists():
        pytest.skip("only the XML is on disk; the images ship in the package")
    named = sum(count for (name, _value), count in values(MISMO.read_bytes()).items()
                if name == "ImageFileLocationIdentifier")
    assert not report["pictures_missing"], report["pictures_missing"]
    assert len(report["pictures_placed"]) == named
    media = store.media(case_id)
    assert len(media) == named

    # A-1 gives each ImageCategoryType a Report Location, so a picture knows
    # which section's exhibits it belongs under.  Arriving with no section at
    # all left it with nowhere on the page to appear.  The ones that keep 0
    # belong to a comparable or to the report as a whole, not to a section.
    placed = [m for m in media if m.section]
    loose = [m for m in media if not m.section]
    assert len(placed) >= 35, f"only {len(placed)} of {len(media)} pictures know their section"
    assert all(m.category in ("comparable", "subject", "map") for m in loose), (
        [(m.category, m.filename) for m in loose])


@needs_reference
def test_the_file_arrives_clean(imported):
    """No schema error and no fatal finding on a file the industry shipped."""
    _client, _case_id, report, _store = imported
    assert report["schema_errors"] == [], report["schema_errors"][:5]
    assert report["compliance"]["fatal"] == 0
    assert report["compliance"]["schema"] == 0


@needs_reference
def test_the_comparables_are_read_as_comparables(imported):
    """Four properties, told apart by @ValuationUseType, each with its own
    address, price and adjustments -- the heart of the report."""
    client, case_id, report, _store = imported
    assert report["comparables"] == {"SalesComparable": 4}, report["comparables"]

    grid = client.get(f"/api/cases/{case_id}/comparables", params={"kind": "sales"}).json()
    assert len(grid["comparables"]) == 4
    rows = [r for r in grid["rows"] if not r.get("heading")]
    filled = sum(1 for r in rows for c in r["cells"] if str(c.get("value", "")).strip())
    assert filled > 200, f"only {filled} comparable cells carry a value"
    adjustments = sum(1 for r in rows for c in r["cells"]
                      if str(c.get("adjustment", "")).strip())
    assert adjustments >= 39, f"only {adjustments} adjustments were read"


@needs_reference
def test_the_canonical_map_knows_every_data_point_a_real_file_uses():
    """A data point the map has never heard of is one nothing in the
    application can place, validate or deliver."""
    used = {name for name, _value in values(MISMO.read_bytes())}
    unknown = sorted(n for n in used if not uadmap.known(n))
    assert unknown == [], unknown


@needs_reference
def test_every_enumerated_value_a_real_file_uses_is_one_we_offer():
    """If certified software wrote it, our list has to contain it.

    A value the editor cannot offer is a value the appraiser cannot choose,
    and one the round-trip can only preserve by accident.

    Only a data point A-1 formats as Enumerated has a closed list.  Where the
    format is String, any values A-1 prints beside it are examples -- the cost
    guides listed against Data Source Name are suggestions, not the only names
    a source may have -- and the real file duly carries "OneKey MLS".
    """
    missing = []
    for (name, value), _count in values(MISMO.read_bytes()).items():
        kind, _details = uadmap.format_of(name)
        if kind.casefold() != "enumerated":
            continue
        allowed = uadmap.options(name)
        if allowed and value not in allowed:
            missing.append(f"{name}={value}")
    assert missing == [], sorted(missing)


@needs_reference
def test_the_statements_we_derive_match_what_the_real_file_states(imported):
    """A-1's non-displaying indicators say whether each approach was
    developed, whether a rent schedule is included, whether the work was for a
    federal agency.  Nothing on the page asks the appraiser any of it, because
    the report already answers it: the sales comparison approach was developed
    if there are sales comparables.

    The reference file states all ten itself, so it can say whether reading
    them off the document gives the same answers a certified product gave.
    """
    from uad import delivery

    _client, case_id, _report, store = imported
    package = delivery.build(store.tree(case_id), store.media(case_id),
                             store.media_dir(case_id))
    ours = package.tree.getroot()
    real = etree.parse(str(MISMO)).getroot()

    def stated(root, name):
        for node in root.iter("{*}" + name):
            if (node.text or "").strip():
                return node.text.strip()
        return None

    differ = {name: (stated(real, name), stated(ours, name))
              for name in delivery._derived_indicators(ours)
              if stated(real, name) != stated(ours, name)}
    assert differ == {}, differ
    assert schema.validate(package.tree) == []


@needs_reference
def test_the_required_delivery_only_data_points_are_known():
    """A-1 marks these Required and never prints them, so a model built from
    the printed page cannot see them; the map has to."""
    required = [n for n in uadmap.delivery_only() if uadmap.is_required(n)]
    assert len(required) >= 13, required
    for name in ("SalesComparisonApproachIndicator", "CostApproachIndicator",
                 "LatitudeIdentifier", "ValuationSoftwareProductName"):
        assert uadmap.known(name)
        assert not uadmap.displays(name), f"{name} is delivery-only"
