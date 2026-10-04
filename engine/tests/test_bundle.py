"""A case survives the loss of its server: bundle, delete, restore -- and a
bundle is outside data, so it cannot overwrite newer work, escape the case
folder or carry a signature past the gate.

Run:  python engine/tests/test_bundle.py
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.cases import IN_REVIEW, SIGNED, Store  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILS.append(name)


def rewrite(data: bytes, edit) -> bytes:
    src = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as z:
        for name in src.namelist():
            body = src.read(name)
            if name == "case.json":
                meta = json.loads(body)
                edit(meta, z)
                body = json.dumps(meta).encode()
            z.writestr(name, body)
    return out.getvalue()


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        st = Store(Path(tmp))
        case = st.create(template="sf1_appraisal_v1_4", name="Bundle test", blank=False)
        cid = case.case_id
        st.add_media(cid, category="subject", filename="front.jpg", caption="Front", size=3)
        (st.media_dir(cid) / "front.jpg").write_bytes(b"jpg")
        (st.folder(cid) / "editor.json").write_text('{"fills": {"a": 1}}')
        xml_before = st.xml_path(cid).read_bytes()
        n_media = len(st.media(cid))

        full = st.bundle(cid, images=True)
        core = st.bundle(cid, images=False)
        check("a bundle without images is smaller", len(core) < len(full))

        st.delete(cid)
        restored = st.restore(full)
        check("restored under the same case ID", restored.case_id == cid)
        check("the MISMO document is byte-identical", st.xml_path(cid).read_bytes() == xml_before)
        check("every media row came back", len(st.media(cid)) == n_media)
        check("the editor state came back", "fills" in (st.folder(cid) / "editor.json").read_text())
        check("history records the restore", st.history(cid)[0]["action"] == "restored")
        check("nothing is missing after a full restore", not st.missing_media(cid))

        try:
            st.restore(full)
            check("an existing case is never overwritten", False)
        except FileExistsError:
            check("an existing case is never overwritten", True)

        st.delete(cid)
        st.restore(core)
        missing = st.missing_media(cid)
        check("a core restore re-fetches template photos and lists only the rest",
              [m.filename for m in missing] == ["front.jpg"])
        st.put_media_file(cid, missing[0].media_id, b"jpg")
        check("the browser can put the missing file back", not st.missing_media(cid))

        def sign(meta, _z):
            meta["case"]["state"] = SIGNED
            meta["case"]["signed_by"] = "Someone"
        st.delete(cid)
        back = st.restore(rewrite(full, sign))
        check("a signed bundle comes back in review, unsigned",
              back.state == IN_REVIEW and not back.signed_by)

        def escape(meta, z):
            z.writestr("files/../../evil.txt", "x")
        st.delete(cid)
        try:
            st.restore(rewrite(full, escape))
            check("a path outside the case folder is refused", False)
        except ValueError:
            check("a path outside the case folder is refused",
                  not (Path(tmp) / "evil.txt").exists())

        try:
            st.restore(b"not a zip")
            check("garbage is refused", False)
        except ValueError:
            check("garbage is refused", True)

    print(f"\n{'FAILED' if FAILS else 'all passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
