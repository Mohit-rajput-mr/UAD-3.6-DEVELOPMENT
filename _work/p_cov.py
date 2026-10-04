import pathlib
p=pathlib.Path("engine/uad/coverage.py"); s=p.read_text(encoding="utf-8")
old = """                written = edit.write(tree, fid, value, binding=binding, scope=scope)
                back = bind.locate(root, binding, written.data_point, scope, 1)
                got = (back.text or "").strip() if back is not None else ""
                f.write = "ok" if got == written.new else "wrong"
                if f.write == "wrong":
                    f.write_detail = f"wrote {written.new!r}, read {got!r}\""""
new = """                written = edit.write(tree, fid, value, binding=binding, scope=scope)
                back = bind.locate(root, binding, written.data_point, scope, 1)
                got = (back.text or "").strip() if back is not None else ""
                if got != written.new:
                    # A-1 gates some data points on an indicator elsewhere
                    # ("IF IncomeApproachIndicator = true").  The editor never
                    # shows a gated field while its gate is shut, so the audit
                    # opens the gate and asks again rather than reporting a
                    # field that works as broken.
                    opened = _open_gates(root, dp)
                    if opened:
                        edit.write(tree, fid, value, binding=binding, scope=scope)
                        back = bind.locate(root, binding, written.data_point, scope, 1)
                        got = (back.text or "").strip() if back is not None else ""
                        if got == written.new:
                            f.write_detail = "displays when " + ", ".join(opened)
                f.write = "ok" if got == written.new else "wrong"
                if f.write == "wrong":
                    f.write_detail = f"wrote {written.new!r}, read {got!r}\""""
assert old in s
s = s.replace(old, new, 1)

helper = '''def _open_gates(root, dp: dict) -> list[str]:
    """Set the indicators A-1 conditions this data point on, and say which."""
    opened = []
    for key, want in (dp.get("requires") or {}).items():
        if key.startswith(("@", "__")) or not key.endswith("Indicator"):
            continue
        for node in root.iter(f"{{{bind.MISMO}}}{key}"):
            if (node.text or "").strip() != want:
                node.text = want
                opened.append(f"{key} = {want}")
    return opened


def _classify(f: Field, extra_names) -> None:'''
s = s.replace("def _classify(f: Field, extra_names) -> None:", helper, 1)
p.write_text(s, encoding="utf-8"); print("ok")
