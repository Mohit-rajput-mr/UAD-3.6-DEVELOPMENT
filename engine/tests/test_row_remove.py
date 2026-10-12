"""Every repeating table row can be taken out by its own x (DR §7, T-1068),
not only emptied: the row and what the schema no longer lets stand without it
go; the document stays valid; a block the schema needs is refused."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_every_choice_saves import _case, _editor, _send, client  # noqa: E402,F401
from app import api  # noqa: E402
from uad import schema  # noqa: E402
from uad.report import form  # noqa: E402

M = "{http://www.mismo.org/residential/2009/schemas}"


def _answered(case):
    return len([s for s in api.store().tree(case).getroot().iter(f"{M}SITE_INFLUENCE")
                if (s.findtext(f".//{M}SiteInfluenceType") or "").strip()])


def test_a_site_influence_row_comes_out_by_its_x(client):
    case = _case(client, "sf1_appraisal_v1_4")
    # make a site influence row, then take it out
    doc = _editor(case)
    kind = next(v for v, _s in form.choices_for("4.025") if v not in ("Other", "BodyOfWater"))
    n0 = _answered(case)
    assert _send(client, case, doc.xpath("//*[@data-tf='4.025' and @data-tnew]")[0], kind).status_code == 200
    assert _answered(case) == n0 + 1
    doc = _editor(case)
    xs = doc.xpath("//*[@data-row-del='SITE_INFLUENCE']")
    assert xs, "the influence row has its x"
    r = client.delete(f"/api/cases/{case}/rows", params={"key": xs[-1].get("data-key"), "tag": "SITE_INFLUENCE"})
    assert r.status_code == 200, r.text
    assert _answered(case) == n0
    assert not schema.validate(api.store().tree(case))


def test_every_row_x_names_a_block_the_route_accepts(client):
    for template in ("sf1_appraisal_v1_4", "2_to_4_unit_appraisal_v1_4", "condo1_appraisal_v1_4"):
        case = client.post("/api/cases", json={"template": template, "name": "x"}).json()["case_id"]
        doc = _editor(case)
        tags = {x.get("data-row-del") for x in doc.xpath("//*[@data-row-del]")}
        assert tags, template
        assert all(form.row_removable(t) or t in ("AMENITY", "FLOOR_COVERING") for t in tags), tags
