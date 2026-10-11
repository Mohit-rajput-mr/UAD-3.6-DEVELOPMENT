"""The Market section's search results counted from an MLS export (T-1075).

Run:  python -m pytest -q engine/tests/test_market_search.py
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, schema, templates
from uad.market_search import MarketSearchError, count

METRICS = ("17.005", "17.006", "17.007", "17.008", "17.009", "17.010",
           "17.011", "17.012", "17.013", "17.014", "17.015")


def _sf1_search() -> str:
    """A search shaped like the one D-1 SF1 reports: two active listings,
    one pending, 35 sales in the 24 months to 2019-09-20, and two rows that
    do not count (a sale before the window, a withdrawn listing)."""
    rows = ["MLS #,Status,List Price,Sold Price,DOM,Close Date",
            "1,Active,\"$435,000\",,10,",
            "2,ACT,445000,,12,",
            "3,Pending,450000,,30,",
            "4,Sold,410000,380000,20,2017-08-01",
            "5,Withdrawn,470000,,90,"]
    prices = [400000] + [450000] * 16 + [499000] + [550000] * 16 + [597000]
    for n, price in enumerate(prices):
        rows.append(f"{10 + n},Closed,{price},{price},25,{(n % 12) + 1}/15/2018")
    return "\n".join(rows)


def test_the_d1_sf1_figures_are_what_its_search_counts():
    root = etree.parse(str(templates.get("sf1_appraisal_v1_4").path)).getroot()
    held = {f: bind.read(root, bind.binding_for(f))[0] for f in METRICS}
    m = count(_sf1_search(), date(2019, 9, 20), lookback_months=24)
    assert m.fields() == held
    assert len(m.skipped) == 2                  # the old sale and the withdrawn listing, each named
    assert any("2017-08-01" in s for s in m.skipped) and any("Withdrawn" in s for s in m.skipped)


def test_a_median_of_an_even_count_is_the_mean_of_the_middle_two():
    m = count("Status,List Price,DOM\nActive,100000,3\nActive,300000,4\nActive,200000,9\nActive,500000,10",
              date(2020, 1, 1))
    assert (m.fields()["17.008"], m.fields()["17.006"]) == ("250000", "7")   # 6.5 days -> 7


def test_headers_are_read_as_mls_systems_name_them():
    m = count("Standard Status,Current Price,Close Price,CDOM,Sold Date\n"
              "Closed,300000,295000,40,2019-12-01\nActive Under Contract,310000,,5,",
              date(2020, 1, 1))
    assert (m.pending, m.sold_prices) == (1, [295000.0])


def test_a_file_that_cannot_be_told_apart_is_refused():
    with pytest.raises(MarketSearchError, match="listing status"):
        count("Address,Price\n1 Main St,100000", date(2020, 1, 1))
    with pytest.raises(MarketSearchError, match="sold price or close date"):
        count("Status,List Price\nSold,100000", date(2020, 1, 1))


@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from app import api
    from app.cases import Store
    monkeypatch.setenv("URAR_CLIENT_LAYOUT", "1")
    from app.main import app
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    monkeypatch.setattr(api, "RENDERER", None)
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        yield c
    store.conn.close()


def test_seen_first_then_written(client):
    from app import api
    cid = client.post("/api/cases", json={"template": "sf1_appraisal_v1_4", "blank": False,
                                          "name": "Market"}).json()["case_id"]
    st = api.store()
    before = etree.tostring(st.tree(cid))
    search = "Status,List Price,Sold Price,DOM,Close Date\nActive,500000,,8,\nSold,480000,470000,30,2019-06-01"
    r = client.post(f"/api/cases/{cid}/market/search", content=search)
    assert r.status_code == 200
    body = r.json()
    assert body["lookback_months"] == 24                       # the report's own answer (17.011)
    by = {f["field_id"]: f for f in body["figures"]}
    assert (by["17.005"]["current"], by["17.005"]["counted"]) == ("2", "1")
    assert etree.tostring(st.tree(cid)) == before              # nothing written yet
    r = client.post(f"/api/cases/{cid}/market/search?apply=true", content=search)
    assert r.status_code == 200 and r.json()["relayout"] and len(r.json()["written"]) == len(body["figures"])
    root = st.tree(cid).getroot()
    assert bind.read(root, bind.binding_for("17.005")) == ["1"]
    assert bind.read(root, bind.binding_for("17.014")) == ["470000"]
    assert not schema.validate(st.tree(cid))
    assert client.post(f"/api/cases/{cid}/market/search", content="nothing useful").status_code == 422
