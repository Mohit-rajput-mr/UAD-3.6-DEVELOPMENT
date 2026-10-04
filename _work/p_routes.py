import pathlib
p=pathlib.Path("engine/app/api.py"); s=p.read_text(encoding="utf-8")
s=s.replace("from . import renders", "from . import autofill, renders", 1)

routes = '''
# ---------------------------------------------------------------- auto-fill
# A case arrives as an order sheet, an MLS export and a folder of photographs.
# The appraiser watches it being entered rather than being handed a filled
# report: the server writes the whole document in one pass while the page
# replays the same steps, section by section, control by control.
AUTOFILL: dict[str, dict] = {}


@router.post("/cases/{case_id}/autofill")
def start_autofill(case_id: str, request: Request, body: dict = Body(default={})) -> dict:
    """Plan the steps that fill this case, and begin writing them."""
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    source = str(body.get("source") or "")
    if not source:
        raise HTTPException(422, "Name the case or template the values come from.")
    try:
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
            job["running"] = False

    renders.background(run)
    return {"steps": [s.to_json() for s in steps], "total": len(steps)}


@router.get("/cases/{case_id}/autofill")
def autofill_status(case_id: str) -> dict:
    _case_or_404(case_id)
    return AUTOFILL.get(case_id) or {"running": False, "written": 0, "total": 0, "failed": []}


@router.post("/cases/{case_id}/media")'''
s = s.replace('@router.post("/cases/{case_id}/media")', routes.lstrip("\n"), 1)
p.write_text(s, encoding="utf-8"); print("ok")
