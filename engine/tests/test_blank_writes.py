"""Fields the owner's section test found refused on a blank report now save.

B1  Sales Contract: after "Is there a sales contract? = Yes", the price, date,
    sale type and non-arm's-length comment were refused ("SALES_CONTRACT is
    not expected"): the writer took a plural name for a repeat and added a
    second SALES_CONTRACT the subschema does not allow (E-079).
B8  Alternate Physical Address: ADDITIONAL_ADDRESS is typed ADDRESS, so its
    children had no schema order (E-080).
B9  Date of Signature: the wrong arcrole for SIGNATORY -> ROLE, and a third
    SIGNATORY added beside the blank's orphaned one (E-081).

Every write must answer 200, read back, and add no schema error -- on a blank
of every one of the 12 templates.

Run:  python -m pytest -q engine/tests/test_blank_writes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import schema, templates  # noqa: E402

WRITES = [
    ("20.000", "true"),
    ("20.004", "425000"),
    ("20.005", "2026-03-04"),
    ("20.006", "ShortSale"),
    ("20.003", "Seller is the borrower's employer."),
    ("3.001", "12 Oak Ave, Springfield, IL 62701"),
    ("29.066", "2026-03-04"),
]


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.main import app
    api.STORE = Store(tmp_path_factory.mktemp("cases"))
    api.RENDERER = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_writes_save_on_every_blank(client, template):
    cid = client.post("/api/cases", json={"template": template, "blank": True, "name": "w"}).json()["case_id"]
    before = len(schema.validate(api.store().tree(cid)))
    bad = []
    for fid, value in WRITES:
        r = client.patch(f"/api/cases/{cid}/fields/{fid}", json={"value": value})
        if r.status_code != 200:
            bad.append(f"{fid}: {r.status_code} {r.text[:160]}")
    assert not bad, bad
    assert len(schema.validate(api.store().tree(cid))) <= before
    fields = {f["field_id"]: f for s in client.get(f"/api/cases/{cid}/fields").json()["sections"]
              for f in s["fields"]}
    assert "425,000" in str(fields["20.004"].get("value")), fields["20.004"]
    assert "Oak Ave" in str(fields["3.001"].get("value")), fields["3.001"]


def test_every_yes_no_answer_reads_as_answered(client):
    """B7: an indicator B-1 prints nothing for ("<<Does Not Display>>") still
    reads "Yes" in the editor, and no choice is labelled with a print marker."""
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": True,
                                          "name": "yn"}).json()["case_id"]
    fields = [f for s in client.get(f"/api/cases/{cid}/fields").json()["sections"] for f in s["fields"]
              if {o["value"] for o in f["options"]} == {"true", "false"}]
    assert len(fields) > 30, len(fields)
    markers, written = [], set()
    for f in fields:
        markers += [f"{f['field_id']}: {o['label']}" for o in f["options"] if o["label"].startswith("<<")]
        if client.patch(f"/api/cases/{cid}/fields/{f['field_id']}", json={"value": "true"}).status_code == 200:
            written.add((f["field_id"], f["ordinal"]))   # a gated one is not this test's subject
    blank = [g["field_id"] for s in client.get(f"/api/cases/{cid}/fields").json()["sections"]
             for g in s["fields"] if (g["field_id"], g["ordinal"]) in written
             and g["edit_value"] == "true" and not g["value"]]
    assert written
    assert not markers, markers
    assert not blank, blank
