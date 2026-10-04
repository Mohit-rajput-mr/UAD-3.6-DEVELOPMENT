"""Two server copies with separate disks share one durable store: a case made
on one is found, current, on the other; an edit on either reaches both; a
delete reaches both.  This is the serverless (Vercel) case -- where a report
made on one copy "did not load" on the next.

Run:  python engine/tests/test_durable.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cases import Store  # noqa: E402
from app.durable import DirBackend, Durable  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        shared = DirBackend(str(Path(tmp) / "shared"))
        a, b = Store(Path(tmp) / "a"), Store(Path(tmp) / "b")
        da, db = Durable(shared), Durable(shared)

        case = a.create(template="sf1_appraisal_v1_4", name="Durable test", blank=True)
        cid = case.case_id
        da.push(a, cid)
        check("copy B does not hold the case before asking", cid not in {c.case_id for c in b.list()})
        check("copy B finds the case in the shared store", db.pull(b, cid))
        check("copy B's XML matches copy A's",
              (a.folder(cid) / "mismo.xml").read_bytes() == (b.folder(cid) / "mismo.xml").read_bytes())

        # an edit on B reaches A
        tree = b.tree(cid)
        tree.getroot().set("{urn:test}marker", "edited-on-b")
        b.save_tree(cid, tree)
        db.push(b, cid)
        da.pull(a, cid)
        check("an edit on B reaches A", b"edited-on-b" in (a.folder(cid) / "mismo.xml").read_bytes())
        check("nothing changed: pull is a no-op", da.pull(a, cid))

        # the case list on a third, empty copy
        c, dc = Store(Path(tmp) / "c"), Durable(shared)
        dc.pull_all(c)
        check("a fresh copy lists the case", cid in {x.case_id for x in c.list()})

        # delete on A is seen by C's list
        a.delete(cid)
        da.forget(cid)
        dc.pull_all(c)
        check("a delete reaches the other copies", cid not in {x.case_id for x in c.list()})
        check("an unknown case is not invented", not Durable(shared).pull(Store(Path(tmp) / "d"), "0123456789ab"))

        off = Durable(None)
        check("without a backend the module does nothing", not off.on and off.pull(a, "x"))
    print("all passed" if not FAILS else f"{len(FAILS)} FAILED")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
