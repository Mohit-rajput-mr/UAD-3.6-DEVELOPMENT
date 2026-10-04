import pathlib
p=pathlib.Path("engine/app/api.py"); s=p.read_text(encoding="utf-8")
old = '''    try:
        src_root = etree.parse(str(templates.get(source).path)).getroot()
    except KeyError:
        try:
            src_root = st.tree(source).getroot()
        except Exception:
            raise HTTPException(404, f"no source {source!r}")
    steps = autofill.plan(tree, src_root, folder=st.folder(case_id))
    job = {"running": True, "written": 0, "total": len(steps), "failed": []}
    AUTOFILL[case_id] = job

    def run() -> None:
        try:
            working = st.tree(case_id)
            result = autofill.apply(working, steps)
            st.save_tree(case_id, working, allow_invalid=True)
            st.invalidate(case_id, _actor(request), "filled from intake")
            st.log(case_id, _actor(request), "autofill",
                   f"{result['written']} of {len(steps)} values written")
            job.update(result)
        except Exception as exc:                        # noqa: BLE001
            job["failed"].append({"n": 0, "fid": "", "reason": str(exc)[:200]})
        finally:
            job["running"] = False'''
new = '''    src_folder, src_media = None, []
    try:
        tpl = templates.get(source)
        src_root = etree.parse(str(tpl.path)).getroot()
        src_folder = tpl.path.parent
        src_media = [{"category": "other", "filename": p.name, "caption": "",
                      "section": 0, "order": n, "content_type": "image/jpeg",
                      "path": str(p)}
                     for n, p in enumerate(tpl.images[:60], start=1)]
    except KeyError:
        try:
            src_root = st.tree(source).getroot()
            src_folder = st.folder(source)
            src_media = [{**m.to_json(), "path": str(st.media_dir(source) / m.filename)}
                         for m in st.media(source)]
        except Exception:
            raise HTTPException(404, f"no source {source!r}")
    have = {m.filename for m in st.media(case_id)}
    src_media = [m for m in src_media if m["filename"] not in have]
    steps = autofill.plan(tree, src_root, folder=st.folder(case_id),
                          source_folder=src_folder, media=src_media)
    job = {"running": True, "written": 0, "total": len(steps), "failed": []}
    AUTOFILL[case_id] = job

    def add_comparable(kind: str) -> int:
        working_ = st.tree(case_id)
        number = comparables.add_property(working_, comparables.SHEETS[kind][1])
        st.save_tree(case_id, working_, allow_invalid=True)
        return number

    def add_media(row: dict) -> None:
        origin = Path(row.get("path") or "")
        if not origin.exists():
            raise FileNotFoundError(row.get("filename", ""))
        target = st.media_dir(case_id) / origin.name
        if not target.exists():
            shutil.copy2(origin, target)
        st.add_media(case_id, category=row.get("category") or "other",
                     filename=origin.name, caption=row.get("caption") or "",
                     order=int(row.get("order") or 0),
                     comparable=int(row.get("comparable") or 0),
                     section=int(row.get("section") or 0),
                     size=target.stat().st_size,
                     content_type=row.get("content_type") or "image/jpeg",
                     provenance=row.get("provenance") or "template")

    def run() -> None:
        try:
            # The comparables are created first, through the same route the
            # editor uses, so the grid has columns to write into.
            for step in steps:
                if step.kind == autofill.COMP:
                    add_comparable(step.comp_kind)
            working = st.tree(case_id)
            result = autofill.apply(
                working, [s for s in steps if s.kind != autofill.COMP],
                add_media=add_media)
            result["written"] += sum(1 for s in steps if s.kind == autofill.COMP)
            st.save_tree(case_id, working, allow_invalid=True)
            st.invalidate(case_id, _actor(request), "filled from intake")
            st.log(case_id, _actor(request), "autofill",
                   f"{result['written']} of {len(steps)} values written")
            job.update(result)
        except Exception as exc:                        # noqa: BLE001
            job["failed"].append({"n": 0, "fid": "", "reason": str(exc)[:200]})
        finally:
            job["running"] = False'''
assert old in s
p.write_text(s.replace(old,new,1),encoding="utf-8"); print("ok")
