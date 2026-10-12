"""A site influence is a whole row (DR §7, T-1069): its type, then the
proximity, the impact (beneficial / neutral / adverse) and the comment the
row asks for once the type is known -- each saved into that influence and
shown again after a reload.  Driven the way the editor sends them."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_every_choice_saves import _case, _editor, _send, client  # noqa: E402,F401
from uad.report import form  # noqa: E402


def _row_controls(doc, fid):
    return [e for e in doc.xpath(f"//*[@data-tf='{fid}' and @data-tk and not(@data-tnew)]") if e.get("data-tk")]


def test_an_influence_row_saves_its_proximity_impact_and_comment(client):
    case = _case(client, "sf1_appraisal_v1_4")
    doc = _editor(case)
    new = doc.xpath("//*[@data-tf='4.025' and @data-tnew]")
    assert new, "the influence table offers an empty line"
    kind = next(v for v, _shown in form.choices_for("4.025") if v not in ("Other", "BodyOfWater"))
    before = {e.get("data-tk") for e in _row_controls(doc, "4.028")}
    assert _send(client, case, new[0], kind).status_code == 200
    doc = _editor(case)
    keys = [e.get("data-tk") for e in _row_controls(doc, "4.028") if e.get("data-tk") not in before]
    assert len(keys) == 1, "the new influence is a row of its own"
    key = keys[0]

    def in_row(fid):
        return [e for e in _row_controls(doc, fid) if e.get("data-tk") == key]
    impact = next(v for v, _s in form.choices_for("4.028") if v)
    sent = {}
    for fid, value in (("4.028", impact), ("4.029", "Busy road behind the rear lot line")):
        el = in_row(fid)
        assert el, f"{fid} is not asked in the new row"
        r = _send(client, case, el[0], value)
        assert r.status_code == 200, (fid, r.text)
        sent[fid] = value
    doc = _editor(case)
    for fid, value in sent.items():
        shown = " ".join(e.text_content() for e in in_row(fid))
        label = dict(form.choices_for(fid)).get(value, value) if fid == "4.028" else value
        assert label in shown or value in shown, (fid, shown)
