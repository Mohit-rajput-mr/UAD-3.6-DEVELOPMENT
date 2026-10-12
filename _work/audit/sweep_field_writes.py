"""Write every field of a new report through PATCH /fields; 200 must mean saved.

    python _work/audit/sweep_field_writes.py          (~6 min, no browser)

Each field gets a fresh new report and a value of its A-1 format (the last
enumeration of a list, "true" for a Yes/No, a number, a date, text), then the
stored mismo.xml is compared before and after.  Reported per field:

* 200 and the document changed           -- saved;
* 200 and the value was already there    -- nothing to do;
* 4xx                                    -- refused with a reason (a gate first);
* 200 and the document did NOT change    -- a silent drop: a bug (E-342).

A fresh report per field matters: on one report, writing 3.012 "Cooperative"
reshapes it and the writes after it look lost (380 false alarms).
2026-10-11 (epic-brahmagupta, T-014): 996 saved, 151 refused, 0 silent.
"""
from __future__ import annotations

import collections
import sys
import tempfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[2] / "engine"
sys.path.insert(0, str(ENGINE))

from fastapi.testclient import TestClient  # noqa: E402

from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from app.main import app  # noqa: E402
from uad import bind, edit  # noqa: E402

TYPED = {"String": "Test Value", "Amount": "1234", "Date": "2026-03-04", "Count": "3",
         "Percent": "5", "Numeric": "3", "Year": "1990", "Integer": "3"}


def value_for(binding) -> str | None:
    try:
        dp = edit.choose_data_point(binding)
    except KeyError:
        return None
    kind = (dp.get("format_type") or "String").strip()
    if kind.casefold() == "enumerated":
        options = [o["value"] for o in (dp.get("enumerations") or []) if o.get("value")]
        return options[-1] if options else None
    if kind.casefold() == "boolean":
        return "true"
    return TYPED.get(kind, "3")


def main() -> int:
    api.STORE = Store(Path(tempfile.mkdtemp()) / "cases")
    api.RENDERER = None
    stats: collections.Counter = collections.Counter()
    silent = []
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        seen: set[str] = set()
        for section in bind.page_model().values():
            for pf in section:
                if pf.field_id in seen or pf.field_id.startswith("1."):
                    continue                  # the Summary redisplays; never edited
                seen.add(pf.field_id)
                value = value_for(pf.binding)
                if value is None:
                    stats["no value to try"] += 1
                    continue
                case = c.post("/api/cases", json={"name": "sweep"}).json()["case_id"]
                xml = api.store().xml_path(case)
                before = xml.read_bytes()
                r = c.patch(f"/api/cases/{case}/fields/{pf.field_id}", json={"value": value})
                after = xml.read_bytes()
                if r.status_code != 200:
                    stats[f"refused ({r.status_code})"] += 1
                    continue
                w = r.json().get("written") or {}
                if before != after:
                    stats["saved"] += 1
                elif w.get("old") and w.get("old") == w.get("new"):
                    stats["already that value"] += 1
                else:
                    stats["SILENT DROP"] += 1
                    silent.append((pf.field_id, pf.label[:40], value,
                                   {k: w.get(k) for k in ("data_point", "old", "new")}))
    print(dict(stats))
    for row in silent:
        print("  SILENT", *row)
    return 1 if silent else 0


if __name__ == "__main__":
    raise SystemExit(main())
