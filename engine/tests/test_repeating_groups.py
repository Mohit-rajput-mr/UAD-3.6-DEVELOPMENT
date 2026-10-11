"""A block taken out of, or added to, a repeating group leaves the document
valid (T-509, owner 2026-10-10, screenshot 04).

The owner's Review Master showed, on a new two-to-four unit report,

    Element 'AMENITY_CATEGORY_DETAIL': This element is not expected.
    Expected is ( AMENITIES ).

MISMO nests an amenity four wrappers deep and every wrapper must hold one of
the next (GSE subschema: PROPERTY_AMENITY > AMENITY_CATEGORIES >
AMENITY_CATEGORY > AMENITIES > AMENITY, each minOccurs 1).  Every remover
here followed the same pattern -- take the block out, and the holder with it
if it is left empty -- so removing the last amenity of a category took its
AMENITIES and left the AMENITY_CATEGORY standing without it: the editor's
"Remove this amenity" (x) on comparable #1 or #3 of a new 2-4 unit report
gave exactly that message.  The adding side had the twin fault: a block put
in with ``append`` / ``SubElement`` lands after an EXTENSION the sequence puts
last, and a holder made on the way comes with the instance its schema
requires, so the first row added beside it left an empty phantom.

The mechanisms are ``edit.remove_block`` (an ancestor left empty, or without
a child its XSD sequence requires, goes with the block; one that still holds
an answer is never discarded -- the removal is refused) and ``edit.place`` /
``edit.add_instance`` (a block goes where the XSD's sequence puts it, in place
of the empty instance a new holder came with).  They are checked here on the
editor's own routes for every repeating group it can add or remove -- on the
official 2-4 unit sample and on a new blank 2-4 unit report -- and, directly,
against every repeating group of all twelve official D-1 samples.

Run:  python -m pytest -q engine/tests/test_repeating_groups.py -p no:cacheprovider
"""
from __future__ import annotations

import sys
from collections import Counter
from copy import deepcopy
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, certifications, edit, schema, setup, templates, xsd_order  # noqa: E402
from uad.report import comparables  # noqa: E402

M = f"{{{bind.MISMO}}}"
TWO_TO_FOUR = "2_to_4_unit_appraisal_v1_4"

#: the two documents the owner works on: the official 2-4 unit sample, and a
#: new 2-4 unit report as the report setup page makes it
DOCS = {
    "2-4 sample": {"template": TWO_TO_FOUR, "blank": False},
    "new blank 2-4": {"blank": True, "setup": {"property_type": "two_to_four_unit", "units": 2,
                                               "approaches": {"rent": True, "income": True}}},
}


@pytest.fixture
def client(tmp_path):
    from app.main import app
    api.STORE = Store(tmp_path / "cases")
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


@pytest.fixture(params=list(DOCS))
def case(client, request):
    r = client.post("/api/cases", json=DOCS[request.param])
    assert r.status_code == 200, r.text
    cid = r.json()["case_id"]
    return cid, _errors(_tree(cid))


def _tree(cid: str):
    return api.store().tree(cid)


def _errors(tree) -> Counter:
    return Counter(e.message for e in schema.validate(tree))


def _valid(cid: str, before: Counter, r=None):
    """The route answered, and the case has no schema error it did not start
    with (the save guard refuses one -- a 422 is the bug, not a pass)."""
    if r is not None:
        assert r.status_code == 200, r.text
    tree = _tree(cid)
    added = _errors(tree) - before
    assert not added, list(added)[:2]
    return tree


# ------------------------------------------------------------ the owner's case
def test_the_comparable_amenities_of_the_owners_screenshot():
    """The amenity blocks of comparables #1 and #3 of a new 2-4 unit report
    (one OutdoorLiving category each) emptied the way every remover did it --
    the AMENITY, then its emptied AMENITIES -- give exactly the owner's error;
    emptied with ``remove_block`` they leave a valid document."""
    def comp_amenities(root):
        return [a for p in root.iter(f"{M}PROPERTY")
                if p.get("ValuationUseType") == "SalesComparable"
                for a in p.iter(f"{M}AMENITY")]

    tree = setup.apply(templates.load(TWO_TO_FOUR, blank=True), TWO_TO_FOUR,
                       "two_to_four_unit", 2, {})[0]
    before = _errors(tree)                # (the software stamp a case is given)

    old = deepcopy(tree)
    for am in comp_amenities(old.getroot()):
        holder = am.getparent()
        holder.remove(am)
        if not len(holder):
            holder.getparent().remove(holder)
    said = list(_errors(old) - before)
    assert said and all("AMENITY_CATEGORY_DETAIL" in m and "Expected is ( {" in m and "AMENITIES" in m
                        for m in said), said

    for am in comp_amenities(tree.getroot()):
        edit.remove_block(am)
    assert not _errors(tree) - before
    assert comp_amenities(tree.getroot()) == []


def test_every_amenity_comes_out_to_the_last_and_goes_back(client, case):
    """Every amenity -- the subject's and the comparables', the last of each
    category included -- removed with the editor's x, then one added and
    removed again: valid at every step, and no category is left standing
    without its amenities."""
    cid, before = case
    tree = _tree(cid)
    keys = [tree.getpath(a) for a in tree.getroot().iter(f"{M}AMENITY")]
    assert keys, "both documents carry amenity blocks (D-1)"
    for key in reversed(keys):              # last first: each key still names its block
        r = client.delete(f"/api/cases/{cid}/rows", params={"key": key, "tag": "AMENITY"})
        root = _valid(cid, before, r).getroot()
        assert all(c.find(f"{M}AMENITIES") is not None for c in root.iter(f"{M}AMENITY_CATEGORY"))
    root = _tree(cid).getroot()
    assert next(root.iter(f"{M}AMENITY"), None) is None
    assert next(root.iter(f"{M}AMENITY_CATEGORY"), None) is None   # each went with its last amenity

    r = client.patch(f"/api/cases/{cid}/cells/14.002",
                     json={"value": "Deck", "new": True, "data_point": "AmenityType"})
    tree = _valid(cid, before, r)
    added = list(bind.subject(tree.getroot()).iter(f"{M}AMENITY"))
    # one row: not a second, empty one beside the one the new category came with
    assert [a.findtext(f".//{M}AmenityType") for a in added] == ["Deck"]

    r = client.delete(f"/api/cases/{cid}/rows", params={"key": tree.getpath(added[0]), "tag": "AMENITY"})
    tree = _valid(cid, before, r)
    assert next(bind.subject(tree.getroot()).iter(f"{M}AMENITY"), None) is None


def test_list_values_cleared_to_the_last(client, case):
    """A list cell (the subject's views, 4.039): clearing one value takes its
    whole block out -- the last one with its SITE_VIEWS."""
    cid, before = case
    for value in ("Bay", "CityStreet"):
        _valid(cid, before, client.patch(f"/api/cases/{cid}/cells/4.039",
                                         json={"value": value, "new": True, "data_point": "ViewType"}))
    while True:
        tree = _tree(cid)
        views = list(bind.subject(tree.getroot()).iter(f"{M}SITE_VIEW"))
        if not views:
            break
        r = client.patch(f"/api/cases/{cid}/cells/4.039",
                         json={"value": "", "key": tree.getpath(views[-1]), "data_point": "ViewType"})
        _valid(cid, before, r)
        assert r.json().get("removed") is True
    assert bind.subject(_tree(cid).getroot()).find(f".//{M}SITE_VIEWS") is None


def test_flooring_comes_out_to_the_last_and_goes_back(client, case):
    cid, before = case
    tree = _tree(cid)
    unit = next(bind.subject(tree.getroot()).iter(f"{M}PROPERTY_UNIT"))
    key = tree.getpath(unit)
    _valid(cid, before, client.post(f"/api/cases/{cid}/flooring", json={"unit": key, "type": "Vinyl"}))
    while True:
        unit = _tree(cid).xpath(key)[0]
        floors = list(unit.iter(f"{M}FLOOR_COVERING"))
        if not floors:
            break
        r = client.delete(f"/api/cases/{cid}/rows",
                          params={"key": unit.getroottree().getpath(floors[-1]), "tag": "FLOOR_COVERING"})
        _valid(cid, before, r)
    _valid(cid, before, client.post(f"/api/cases/{cid}/flooring", json={"unit": key, "type": "Carpet"}))
    unit = _tree(cid).xpath(key)[0]
    assert [f.findtext(f"{M}FlooringType") for f in unit.iter(f"{M}FLOOR_COVERING")] == ["Carpet"]


def test_rooms_and_levels_come_and_go(client, case):
    cid, before = case
    tree = _tree(cid)
    unit = next(bind.subject(tree.getroot()).iter(f"{M}PROPERTY_UNIT"))
    levels = [tree.getpath(lv) for lv in unit.iter(f"{M}LEVEL")]
    assert levels, "the sample's and the blank's units describe their levels"
    if not (tree.xpath(levels[0])[0].findtext(f"{M}LevelType") or "").strip():
        # a blank level says which it is before it takes rooms (B-1 10.029)
        _valid(cid, before, client.patch(f"/api/cases/{cid}/cells/10.029", json={
            "value": "LevelOne", "key": levels[0], "data_point": "LevelType"}))
    for kind in ("Bedroom", "FullBathroom"):
        _valid(cid, before, client.post(f"/api/cases/{cid}/rooms", json={"level": levels[0], "type": kind}))
    for kind in ("FullBathroom", "Bedroom"):
        _valid(cid, before, client.delete(f"/api/cases/{cid}/rooms",
                                          params={"level": levels[0], "type": kind}))
    for key in reversed(levels):            # every level, the unit's last one included
        _valid(cid, before, client.delete(f"/api/cases/{cid}/levels", params={"level": key}))


def test_units_adus_and_outbuildings_come_and_go(client, case):
    cid, before = case

    def keys(t):
        return {u["key"] for d in t["dwellings"] + t["outbuildings"] for u in d["units"]} | \
               {d["key"] for d in t["dwellings"] + t["outbuildings"]}
    start = keys(client.get(f"/api/cases/{cid}/structure").json())
    for body in ({"add": "unit", "dwelling": 0}, {"add": "adu", "dwelling": 0},
                 {"add": "adu", "location": "outbuilding", "type": "StandaloneADU"},
                 {"add": "outbuilding", "type": "Other", "other": "Barn"}, {"add": "dwelling"}):
        _valid(cid, before, client.post(f"/api/cases/{cid}/structure", json=body))
    for _ in range(12):
        new = sorted(keys(client.get(f"/api/cases/{cid}/structure").json()) - start,
                     key=lambda k: (-k.count("/"), k))   # a unit before its building
        if not new:
            break
        _valid(cid, before, client.delete(f"/api/cases/{cid}/structure", params={"key": new[0]}))
    assert keys(client.get(f"/api/cases/{cid}/structure").json()) == start


@pytest.mark.parametrize("by", list(certifications.INDICATOR))
def test_additional_certifications_come_and_go(client, case, by):
    cid, before = case
    have = len(certifications.listed(_tree(cid).getroot(), by))
    for n, text in ((have + 1, "First added."), (have + 2, "Second added."), (have + 1, "First, edited.")):
        _valid(cid, before, client.patch(f"/api/cases/{cid}/certifications/{by}",
                                         json={"ordinal": n, "value": text}))
    while certifications.listed(_tree(cid).getroot(), by):     # every one, the last included
        _valid(cid, before, client.patch(f"/api/cases/{cid}/certifications/{by}",
                                         json={"ordinal": 1, "value": ""}))


def test_rental_comparables_and_their_pairings_come_and_go(client, case):
    cid, before = case
    r = client.post(f"/api/cases/{cid}/comparables", json={"kind": "rental"})
    _valid(cid, before, r)
    number = r.json()["added"]
    for on in (False, True):
        _valid(cid, before, client.put(f"/api/cases/{cid}/rentals/pairs",
                                       json={"comparable": number, "unit": 1, "on": on}))
        _valid(cid, before, client.put(f"/api/cases/{cid}/rentals/included", json={"unit": 2, "on": on}))
    _valid(cid, before, client.delete(f"/api/cases/{cid}/comparables/{number}", params={"kind": "rental"}))


def test_sales_comparables_are_added_copied_and_removed(client, case):
    cid, before = case
    r = client.post(f"/api/cases/{cid}/comparables", json={"kind": "sales"})
    _valid(cid, before, r)
    first = r.json()["added"]
    r = client.post(f"/api/cases/{cid}/comparables/1/copy", params={"kind": "sales"})
    _valid(cid, before, r)
    for number in sorted((first, r.json()["added"]), reverse=True):
        _valid(cid, before, client.delete(f"/api/cases/{cid}/comparables/{number}", params={"kind": "sales"}))


def _named_rows():
    out = []
    for kind in comparables.SHEETS:
        for row in comparables.rows(kind):
            named = comparables.named_row(kind, row.subject_fid or row.comp_fid,
                                          row.data_point, row.adjust_type)
            if named is not None and (kind, named.container, row.adjust_type) not in out:
                out.append((kind, named.container, row.adjust_type))
    return out


@pytest.mark.parametrize("kind,container,adjust_type", _named_rows())
def test_a_named_grid_row_is_added_renamed_and_removed(client, case, kind, container, adjust_type):
    """B-1's "[Additional Row]" / "[Other ... Feature]": named on the subject
    and every comparable at once, renamed, removed -- and it leaves no
    nameless block behind (the "Name this row" the owner saw appear)."""
    cid, before = case
    count = sum(1 for _ in _tree(cid).getroot().iter(f"{M}{container}"))
    body = {"kind": kind, "container": container, "adjust_type": adjust_type}
    r = client.put(f"/api/cases/{cid}/comparables/lineitems", json={**body, "was": "", "name": "Barn"})
    root = _valid(cid, before, r).getroot()
    rows = [n for n in root.iter(f"{M}{container}") if "Barn" in "".join(n.itertext())]
    assert rows and sum(1 for _ in root.iter(f"{M}{container}")) == count + len(rows)
    r = client.put(f"/api/cases/{cid}/comparables/lineitems", json={**body, "was": "Barn", "name": "Shed"})
    _valid(cid, before, r)
    r = client.put(f"/api/cases/{cid}/comparables/lineitems", json={**body, "was": "Shed", "name": ""})
    root = _valid(cid, before, r).getroot()
    assert sum(1 for _ in root.iter(f"{M}{container}")) == count


@pytest.mark.parametrize("field_id", ["2.001", "2.002"])
def test_parties_named_and_cleared(client, case, field_id):
    """Two borrowers (or sellers) typed into the one field, then cleared: each
    party goes, and a list left with nobody in it goes with them."""
    cid, before = case
    for value in ("Jane Doe | John Roe", "Jane Doe", ""):
        _valid(cid, before, client.patch(f"/api/cases/{cid}/fields/{field_id}", json={"value": value}))


def test_every_picture_comes_out(client):
    """The sample's photographs taken out one by one: the last of an
    inspection's takes its IMAGES with it."""
    cid = client.post("/api/cases", json=DOCS["2-4 sample"]).json()["case_id"]
    before = _errors(_tree(cid))
    tree = _tree(cid)
    keys = [tree.getpath(i) for i in bind.subject(tree.getroot()).iter(f"{M}IMAGE")]
    assert keys
    for key in reversed(keys):
        _valid(cid, before, client.delete(f"/api/cases/{cid}/images", params={"key": key}))


# ------------------------------------------------------------- the mechanisms
def test_a_block_that_holds_an_answer_is_never_discarded_to_make_room():
    """The category goes with its last amenity only because nothing in it is
    an answer.  A wrapper that still says something is kept and the removal
    refused, with nothing changed."""
    tree = templates.load(TWO_TO_FOUR)
    root = tree.getroot()
    cat = next(root.iter(f"{M}AMENITY_CATEGORY"))
    ext = edit.insert_ordered(cat, "EXTENSION")
    other = etree.SubElement(ext, f"{M}OTHER")
    etree.SubElement(other, "{http://www.datamodelextension.org}Note").text = "kept by the appraiser"
    for am in list(cat.iter(f"{M}AMENITY"))[:-1]:
        edit.remove_block(am)                      # not the last: fine
    last = next(cat.iter(f"{M}AMENITY"))
    before = etree.tostring(root)
    with pytest.raises(edit.Unremovable):
        edit.remove_block(last)
    assert etree.tostring(root) == before


def test_a_block_goes_before_the_extension_the_sequence_puts_last():
    """``append`` put a carried party after PARTIES' EXTENSION; ``place``
    puts it where the sequence does."""
    tree = templates.load(TWO_TO_FOUR)
    before = _errors(tree)
    parties = next(tree.getroot().iter(f"{M}PARTIES"))
    ext = edit.insert_ordered(parties, "EXTENSION")
    moved = edit.place(parties, deepcopy(parties.find(f"{M}PARTY")))
    assert list(parties)[-1] is ext and moved.getnext() is ext
    assert not _errors(tree) - before
    parties.append(deepcopy(moved))                     # what append did
    assert any("PARTY" in m and "not expected" in m for m in _errors(tree) - before)


def _repeats(root) -> list[etree._Element]:
    """One first and one last instance of every repeating group the document
    has (a child its parent may hold more than one of, by the XSD)."""
    seen: dict[tuple, list] = {}
    for node in root.iter():
        if not isinstance(node.tag, str) or node.getparent() is None:
            continue
        child = etree.QName(node).localname
        parent = etree.QName(node.getparent()).localname
        if not child.isupper() or xsd_order.max_occurs(parent, child) in (0, 1):
            continue
        seen.setdefault((parent, child), []).append(node)
    out = []
    for group in seen.values():
        out.append(group[0])
        if group[-1] is not group[0]:
            out.append(group[-1])
    return out


def _documents():
    for t in templates.catalogue():
        yield f"{t.key}:sample", lambda t=t: etree.parse(str(t.path))
    yield "new 2-4 unit report", lambda: setup.apply(
        templates.load(TWO_TO_FOUR, blank=True), TWO_TO_FOUR, "two_to_four_unit", 2, {})[0]


@pytest.mark.parametrize("name,load", list(_documents()), ids=[n for n, _l in _documents()])
def test_every_repeating_group_can_lose_and_gain_an_instance(name, load):
    """Each repeating group's first and last instance removed with
    ``remove_block`` adds no schema error (or is refused, untouched, where
    the schema needs it and its holder still holds an answer); a new
    instance added in schema order is never out of place."""
    base = load()
    before = _errors(base)
    paths = [base.getpath(n) for n in _repeats(base.getroot())]
    assert paths, name
    removed = refused = 0
    for path in paths:
        tree = deepcopy(base)
        node = tree.xpath(path)[0]
        shape = etree.tostring(tree)
        try:
            edit.remove_block(node)
        except edit.Unremovable:
            assert etree.tostring(tree) == shape, f"{name}: a refused removal changed {path}"
            refused += 1
        else:
            removed += 1
            added = _errors(tree) - before
            assert not added, f"{name}: removing {path} -> {list(added)[:2]}"

        # and back: a fresh instance of the same group, where the XSD puts it
        # (up to the number the schema allows: Condo1's two SERVICEs are all)
        tree = deepcopy(base)
        node = tree.xpath(path)[0]
        tag, holder = etree.QName(node).localname, node.getparent()
        most = xsd_order.max_occurs(etree.QName(holder).localname, tag)
        if most != xsd_order.UNBOUNDED and len(holder.findall(f"{M}{tag}")) >= most:
            continue
        edit.insert_ordered(holder, tag)
        misplaced = [m for m in _errors(tree) - before if "This element is not expected" in m]
        assert not misplaced, f"{name}: adding beside {path} -> {misplaced[:2]}"
    assert removed, f"{name}: nothing could be removed ({refused} refused)"
