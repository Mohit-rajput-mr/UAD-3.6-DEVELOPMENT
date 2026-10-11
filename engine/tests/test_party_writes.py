"""A party's field written through the fields route lands on that party (T-014).

The client's own role (2.011 "Client/[Party Role Type]": Attorney, Lender,
AMC ...) is written into a second ROLE of the client's PARTY.  On a report
with no client yet, ``PATCH /fields/2.011`` found no party, wrote nothing and
answered 200 -- while H-1 UAD1543 stays Fatal until that role exists.  The
editor's own control goes through ``/client-role``, which creates the party;
the fields route is the same API for every other client and must not answer
200 for a value it dropped.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import bind, compliance, edit  # noqa: E402

M = f"{{{bind.MISMO}}}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def _client_roles(root) -> list[list[str]]:
    return [roles for roles in ([(r.text or "").strip() for r in p.iter(f"{M}PartyRoleType")]
                                for p in root.iter(f"{M}PARTY")) if "Client" in roles]


@pytest.mark.parametrize("role", ["Attorney", "Lender", "ManagementCompany"])
def test_the_clients_role_is_saved_on_a_report_with_no_client_yet(client, role):
    cid = client.post("/api/cases", json={"name": "party"}).json()["case_id"]
    assert not _client_roles(api.store().tree(cid).getroot())
    r = client.patch(f"/api/cases/{cid}/fields/2.011", json={"value": role})
    assert r.status_code == 200 and r.json()["written"]["new"] == role
    root = api.store().tree(cid).getroot()
    assert _client_roles(root) == [["Client", role]]
    assert edit.read_client_role(root) == role
    assert "UAD1543" not in {f.message_id for f in compliance.evaluate(root)
                             if f.status == compliance.FINDING}


def test_a_second_role_goes_to_the_client_already_there(client):
    cid = client.post("/api/cases", json={"name": "party"}).json()["case_id"]
    assert client.patch(f"/api/cases/{cid}/fields/2.012", json={"value": "Acme Lending"}).status_code == 200
    for role in ("Lender", "Attorney"):
        assert client.patch(f"/api/cases/{cid}/fields/2.011", json={"value": role}).status_code == 200
    assert _client_roles(api.store().tree(cid).getroot()) == [["Client", "Attorney"]]
