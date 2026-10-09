"""The REST API.

Everything the browser can do, a program can do: the interface is the API, and
the single-page front end is one of its clients rather than a privileged path.
That is what lets a case be driven headlessly -- intake a folder, fill fields,
read the compliance findings, sign off and export -- without a person at a
keyboard.

Two rules hold throughout:

* Every write goes through the same editor the UI uses, so a value set by a
  script lands exactly where a value typed into the form would.
* Export is reachable only from a signed case.  The route asks the state
  machine, and the state machine asks the Review Master; there is no parameter
  that skips either.
"""
from __future__ import annotations

import io
import os
import json
import re
import mimetypes
import shutil
import threading
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response, StreamingResponse
from lxml import etree

from uad import (bind, compliance, conditions, delivery, edit, extra, integrity, maps, market, parties, review, schema,
                 templates)
from uad.report import comparables, flow, paginate, urar
from uad.report import form as report_form

from . import autofill, renders

from .cases import (DRAFT, EXPORTED, IN_REVIEW, MEDIA_CATEGORIES, SIGNED,
                    GateError, Store)

router = APIRouter(prefix="/api")
STORE: Store | None = None


def store() -> Store:
    if STORE is None:
        raise RuntimeError("the case store has not been opened")
    return STORE


def _actor(request: Request) -> str:
    return request.headers.get("X-Actor") or "appraiser"


def _case_or_404(case_id: str):
    try:
        return store().get(case_id)
    except KeyError:
        raise HTTPException(404, f"no case {case_id}")


def _comp_photo(case_id: str, number: int) -> str:
    """The photo an appraiser attached to this comparable, if any."""
    for m in store().media(case_id):
        if int(m.comparable or 0) == number:
            return f"/api/cases/{case_id}/media/{m.media_id}/file"
    return ""


def _labels(tree, kind: str = "sales") -> list[str]:
    """The comparables' durable identifiers, in their current order."""
    _sheet, role, _title = comparables.SHEETS[kind]
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    return comparables.labels(root, role)


def _fills(case_id: str) -> dict:
    """Which of the document's own image boxes each stored image fills.

    There is one Sales Comparison Map (Appendix E p66).  A map saved before it
    was linked to the document's SalesComparableMap box would otherwise print
    beside that box as a second map page, so it is linked here, once, for the
    form, the preview and the package alike."""
    st = store()
    prefs = get_prefs(case_id) if (st.folder(case_id) / "editor.json").exists() else {}
    fills = dict(prefs.get("fills") or {})
    used = set(fills.values())
    maps_ = [m for m in st.media(case_id) if m.category == "map"
             and (m.caption or "").strip() == "Sales Comparison Map" and m.media_id not in used]
    if maps_:
        M_ = f"{{{bind.MISMO}}}"
        for image in st.tree(case_id).getroot().iter(f"{M_}IMAGE"):
            if image.findtext(f"{M_}ImageCategoryType", "").strip() != "SalesComparableMap":
                continue
            loc = image.findtext(f"{M_}ImageFileLocationIdentifier", "").strip()
            if loc and loc not in fills:
                fills[loc] = maps_[-1].media_id
                break
    return fills


def _media_for_render(case_id: str) -> list[dict]:
    """The case's images, with the path and section the renderer needs."""
    st = store()
    folder = st.media_dir(case_id)
    # A photo can fill one of the document's own exhibit boxes (an IMAGE whose
    # file is not there -- a template's "Property Access" box, say); the box
    # is named by its ImageFileLocationIdentifier.
    fills = {media_id: location for location, media_id in _fills(case_id).items()}
    # The comparable's number travels with its photo: without it the grid had
    # no way to tell whose thumbnail an image was, and printed none.
    return [{"path": str(folder / m.filename), "caption": m.caption,
             "section": m.section, "category": m.category,
             "comparable": int(m.comparable or 0), "media_id": m.media_id,
             "fills": fills.get(m.media_id, ""),
             "section_name": bind.SECTION_NAME.get(int(m.section or 0), "")}
            for m in st.media(case_id) if m.section or m.comparable]


# ------------------------------------------------------------------ templates
@router.get("/templates")
def list_templates() -> dict:
    """The starting points, grouped by property type."""
    groups: dict[str, list] = {}
    for tpl in templates.catalogue():
        groups.setdefault(tpl.property_type, []).append(tpl.to_json())
    return {"property_types": templates.PROPERTY_TYPES, "templates": groups}


# ---------------------------------------------------------------------- cases
# A case created only to be read from -- the file behind "Fill the report".
# It holds the uploaded document and its pictures so the filler can walk them
# exactly as it walks a template, and it is removed when the run ends.  The
# appraiser never chose it, so it does not belong in their list of jobs.
STAGING_PREFIX = "‹fill source› "


@router.get("/cases")
def list_cases() -> dict:
    return {"cases": [c.to_json() for c in store().list()
                      if not (c.name or "").startswith(STAGING_PREFIX)]}


@router.post("/cases")
def create_case(request: Request, body: dict = Body(...)) -> dict:
    # One "New report": the report is shaped by what the appraiser enters, not
    # by picking a form.  A caller may still name a template (tests, imports).
    template = body.get("template") or NEW_REPORT
    chosen = body.get("setup") if isinstance(body.get("setup"), dict) else None
    from uad import setup
    if chosen and not body.get("template"):
        # the report setup page: start on the official structure of the kind
        # the appraiser chose, so nothing has to be carried across
        try:
            template, _det = setup._target(str(chosen.get("property_type", "")),
                                           int(chosen.get("units") or 1))
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc))
    try:
        case = store().create(template=template,
                              name=body.get("name", "") or (NEW_NAME if not body.get("template") else ""),
                              blank=bool(body.get("blank", True)),
                              actor=_actor(request))
    except KeyError:
        raise HTTPException(404, f"no template {template}")
    if chosen:
        st = store()
        try:
            tree, _t, notes, _f = setup.apply(st.tree(case.case_id), case.template,
                                              str(chosen.get("property_type", "")),
                                              int(chosen.get("units") or 1),
                                              dict(chosen.get("approaches") or {}))
        except (KeyError, ValueError) as exc:
            raise HTTPException(422, str(exc))
        st.save_tree(case.case_id, tree)
        st.log(case.case_id, _actor(request), "setup", "; ".join(notes) or "approaches stated")
        case = st.get(case.case_id)
    return case.to_json()


@router.post("/cases/{case_id}/derive")
def derive_case(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """A Restricted Appraisal Update Report or a Completion Report for this
    URAR's property, as a new case (uad/report_types.py ``derive``): the
    subject, the Original Appraisal section, the borrower / client / lender /
    AMC and, for a completion report, the original's repairs are carried; the
    new assignment's inspection, certifications and signature are left to be
    entered."""
    from uad import report_types
    case = _case_or_404(case_id)
    kind = str(body.get("kind") or "")
    if kind not in report_types.KINDS:
        raise HTTPException(400, f"kind must be one of {', '.join(report_types.KINDS)}")
    src = store().tree(case_id)
    if report_types.kind_of(src) != report_types.URAR:
        raise HTTPException(409, "an update or completion report is made from a URAR, not from another update")
    tree, filled = report_types.derive(src, kind)
    title = report_types.title(kind)
    new = store().create_from(
        tree, name=str(body.get("name") or f"{title} - {case.name}")[:120],
        template=f"report:{kind}", property_type=title, actor=_actor(request),
        note=f"{title} derived from case {case_id}")
    return {**new.to_json(), "kind": kind, "parent": case_id, "filled": filled}


# ------------------------------------------------------------- case bundles
# A whole case in one ZIP (app/cases.py ``Store.bundle``): a backup the
# appraiser can download, a way to move a case to another machine, and the copy
# the browser keeps so a case survives the server losing it (a serverless
# instance is recycled with its /tmp).
DURABLE = None     # app/durable.py, set by main.py


@router.get("/host")
def host_info() -> dict:
    """What this server can do, so the interface offers only what works."""
    from uad.report import browser
    durable = not os.environ.get("VERCEL") or bool(DURABLE and DURABLE.on)
    return {"serverLayout": browser.server_layout(), "pdf": browser.AVAILABLE,
            "durable": durable,
            "host": "serverless" if not durable else "server"}


@router.get("/cases/{case_id}/bundle")
def case_bundle(case_id: str, images: bool = Query(True)) -> Response:
    case = _case_or_404(case_id)
    data = store().bundle(case_id, images=images)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in case.name)[:60].strip() or case_id
    return Response(data, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{safe}.uadcase.zip"',
                             "Cache-Control": "no-store",
                             "X-Case-Updated": case.updated})


@router.post("/cases/restore")
async def restore_case(request: Request, file: UploadFile = File(...),
                       replace: bool = Query(False)) -> dict:
    data = await file.read()
    try:
        case = store().restore(data, actor=_actor(request), replace=replace)
    except FileExistsError as exc:
        raise HTTPException(409, f"case {exc} already exists here; nothing was overwritten")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    renderer().forget(case.case_id)
    return {**case.to_json(),
            "missing_media": [m.media_id for m in store().missing_media(case.case_id)]}


@router.put("/cases/{case_id}/media/{media_id}/file")
async def restore_media_file(case_id: str, media_id: str, request: Request) -> dict:
    """The file of an image whose row came back in a bundle without it."""
    _case_or_404(case_id)
    data = await request.body()
    if not data:
        raise HTTPException(400, "no file content")
    try:
        item = store().put_media_file(case_id, media_id, data)
    except KeyError:
        raise HTTPException(404, f"no image {media_id} in case {case_id}")
    return item.to_json()


# ------------------------------------------------------------ import (UAD 3.6)
IMPORT_CATEGORY = {"SalesComparableMap": "map", "SubjectPropertyImprovementSketch": "sketch",
                   "FloorPlan": "floor_plan"}


@router.post("/import")
async def import_appraisal(request: Request, files: list[UploadFile] = File(...),
                           name: str = Query(""), into: str = Query("")) -> dict:
    """A UAD 3.6 appraisal in, as a new case: the XML (alone, in the B-1
    delivery zip, or with its image files) and every picture it names.

    All of it is read, normalised and checked in memory first (``uad/importer``);
    only then is a case created, so a failed import leaves nothing behind.
    """
    import time
    from uad import importer
    started = time.time()
    sent = [(f.filename or "file", await f.read()) for f in files]
    report = importer.Report()
    try:
        xml_name, xml_bytes, assets = importer.open_bundle(sent)
        tree = importer.parse(xml_bytes)
        report.xml_name = xml_name
        # a portable file carries its pictures (and the editor's state) inside
        carried, editor_state = importer.take_embedded(tree, report)
        for low, item in carried.items():
            assets.setdefault(low, item)
        importer.normalise(tree, report)
        importer.repair_enumerations(tree, report)
        pictures = importer.pictures(tree, assets, report)
    except importer.ImportError_ as exc:
        raise HTTPException(422, str(exc))
    root = tree.getroot()
    det = {k: templates._text(root, xp) for k, (_fid, xp) in templates.determinants().items()}
    report.property_type = templates.classify({k: v for k, v in det.items() if v})
    family = templates.by_property_type().get(report.property_type) or templates.by_property_type().get("single_family")         or [templates.catalogue()[0]]
    report.schema_errors = [e.message[:240] for e in schema.validate(tree)][:50]
    try:
        importer.count(tree, report)
    except Exception:                                   # noqa: BLE001 -- counting is a courtesy
        pass

    st = store()
    subject_addr = " ".join(filter(None, [
        root.findtext(f".//{{{bind.MISMO}}}PROPERTY[@ValuationUseType='SubjectProperty']/{{{bind.MISMO}}}ADDRESS/{{{bind.MISMO}}}AddressLineText"),
        root.findtext(f".//{{{bind.MISMO}}}PROPERTY[@ValuationUseType='SubjectProperty']/{{{bind.MISMO}}}ADDRESS/{{{bind.MISMO}}}CityName")]))
    # Into the case the appraiser already has open, when one is named: an
    # import is not always a new job.  A blank template is opened first and
    # the file poured into it, and creating a second case instead would leave
    # the appraiser looking at the empty one.
    if into:
        case = _case_or_404(into)
        replacing = True
    else:
        case = st.create(template=family[0].key, name=name or subject_addr or xml_name,
                         blank=True, actor=_actor(request))
        replacing = False
    try:
        st.save_tree(case.case_id, tree, allow_invalid=True)
        folder = st.media_dir(case.case_id)
        fills: dict[str, str] = {}
        by_file: dict[str, str] = {}
        for pic in pictures:
            (folder / pic.name).write_bytes(pic.data)
            if pic.name not in by_file:
                if pic.comparable and pic.owner and pic.owner != "SubjectProperty" and pic.category in ("PropertyPhoto", ""):
                    category = "comparable"
                elif pic.category in ("DwellingFront", "PropertyPhoto") and pic.owner == "SubjectProperty":
                    category = "subject"
                else:
                    category = IMPORT_CATEGORY.get(pic.category, "other")
                caption = "Sales Comparison Map" if category == "map" else pic.caption
                # A-1 gives every ImageCategoryType a Report Location, so the
                # picture knows which section's exhibits it belongs under.
                # Without it an imported report's images arrived with no
                # section at all and had no slot to appear in -- thirty-four
                # of the forty-two in a real file.
                from uad import uadmap
                item = st.add_media(case.case_id, category=category, filename=pic.name, caption=caption,
                                    comparable=pic.comparable if category == "comparable" else 0,
                                    section=uadmap.image_section(pic.category),
                                    size=len(pic.data), content_type=importer.IMAGE_TYPES.get(
                                        Path(pic.name).suffix.lower(), "image/jpeg"))
                by_file[pic.name] = item.media_id
            fills[pic.location] = by_file[pic.name]
        # pictures the bundle carried that no IMAGE names: kept, to be placed by hand
        for low in list(report.pictures_unreferenced):
            base, data = assets[low.lower()]
            target = folder / base
            if not target.exists():
                target.write_bytes(data)
                st.add_media(case.case_id, category="other", filename=base, size=len(data),
                             content_type=importer.IMAGE_TYPES.get(Path(base).suffix.lower(), "image/jpeg"))
        # What the file answered, so the editor can show it: a value read back
        # cannot say where it came from, so it is recorded here while we know.
        from uad import provenance
        brought = provenance.imported_fields(tree.getroot())
        prefs = {**{k: v for k, v in editor_state.items()
                    if k in ("mapState", "savedSections", "autoMaps", "exhibitSlots", "compWidths")},
                 "fills": fills, "imported": {"from": xml_name, "at": time.time(),
                                              "fields": brought}}
        if any(p.category == "SalesComparableMap" for p in pictures):
            prefs["autoMaps"] = False          # the appraisal brought its own map: keep it
        set_prefs(case.case_id, prefs)
        rv = st.review(case.case_id)
        report.compliance = dict(rv.counts) if hasattr(rv, "counts") else {}
        st.log(case.case_id, _actor(request), "imported",
               f"{xml_name}: {report.values} values, {len(pictures)} pictures")
    except Exception as exc:
        if not replacing:
            st.delete(case.case_id)            # all or nothing
        raise HTTPException(500, f"The import could not be completed, nothing was kept: {exc}")
    report.seconds = round(time.time() - started, 2)
    try:
        renderer().request(case.case_id, "form")          # lay it out while the page opens
    except Exception:                                      # noqa: BLE001
        pass
    return {"case": st.get(case.case_id).to_json(), "report": report.to_json()}


@router.patch("/cases/{case_id}/images")
def name_image(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """An exhibit's name, written to its IMAGE's ImageCaptionCommentDescription."""
    _case_or_404(case_id)
    st = store()
    tree = deepcopy(st.tree(case_id))
    image = bind.find_path(tree.getroot(), str(body.get("key", "")))
    if image is None or etree.QName(image).localname != "IMAGE":
        raise HTTPException(404, "That picture is no longer in the report.")
    text = str(body.get("caption", "")).strip()
    node = image.find(f"{{{bind.MISMO}}}ImageCaptionCommentDescription")
    if text:
        if node is None:
            node = edit.insert_ordered(image, "ImageCaptionCommentDescription")
        node.text = text
    elif node is not None:
        image.remove(node)
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "exhibit named")
    return {"caption": text}


@router.delete("/cases/{case_id}/images")
def remove_image(case_id: str, request: Request, key: str = Query(...)) -> dict:
    """Take a picture out of the report: its IMAGE, and the file linked to it."""
    _case_or_404(case_id)
    st = store()
    tree = deepcopy(st.tree(case_id))
    image = bind.find_path(tree.getroot(), key)
    if image is None or etree.QName(image).localname != "IMAGE":
        raise HTTPException(404, "That picture is no longer in the report.")
    loc = (image.findtext(f"{{{bind.MISMO}}}ImageFileLocationIdentifier") or "").strip()
    parent = image.getparent()
    parent.remove(image)
    if not len(parent):
        parent.getparent().remove(parent)          # an empty IMAGES is not valid
    st.save_tree(case_id, tree)
    prefs = get_prefs(case_id)
    fills = dict(prefs.get("fills") or {})
    media_id = fills.pop(loc, None)
    if media_id is not None:
        set_prefs(case_id, {"fills": fills})
        if media_id not in fills.values():
            st.remove_media(case_id, media_id)
    st.invalidate(case_id, _actor(request), "exhibit removed")
    return {"removed": loc}


@router.get("/cases/{case_id}/portable.xml")
def portable_xml(case_id: str) -> Response:
    """The whole appraisal in one UAD 3.6 XML: every placed picture inside its
    IMAGE (EXTENSION/OTHER, schema-valid), and the editor's state, so that
    importing this one file restores the report exactly."""
    from uad import importer
    _case_or_404(case_id)
    st = store()
    built = _delivery(case_id)
    prefs = get_prefs(case_id) if (st.folder(case_id) / "editor.json").exists() else {}
    state = {k: prefs[k] for k in ("mapState", "savedSections", "autoMaps", "exhibitSlots", "compWidths")
             if k in prefs}
    result = importer.embed(built.tree, built.images, state)
    data = etree.tostring(built.tree, xml_declaration=True, encoding="utf-8", pretty_print=True)
    name = st.get(case_id).name.replace(" ", "_") or case_id
    return Response(data, media_type="application/xml",
                    headers={"Content-Disposition": f'attachment; filename="{name}_UAD36_portable.xml"',
                             "X-Embedded-Pictures": str(result["embedded"]),
                             "X-Missing-Pictures": str(len(result["missing"]))})


@router.get("/cases/{case_id}")
def get_case(case_id: str) -> dict:
    case = _case_or_404(case_id)
    st = store()
    out = case.to_json()
    out["sections_present"] = st.sections_present(case_id)
    out["media"] = len(st.media(case_id))
    out["blockers"] = st.blockers(case_id)
    return out


@router.delete("/cases/{case_id}")
def delete_case(case_id: str) -> dict:
    _case_or_404(case_id)
    store().delete(case_id)
    return {"deleted": case_id}


@router.get("/cases/{case_id}/history")
def case_history(case_id: str) -> dict:
    _case_or_404(case_id)
    return {"history": store().history(case_id)}


@router.get("/cases/{case_id}/mismo.xml")
def case_xml(case_id: str) -> Response:
    _case_or_404(case_id)
    data = store().xml_path(case_id).read_bytes()
    return Response(data, media_type="application/xml")


@router.post("/cases/{case_id}/mismo.xml")
async def replace_xml(case_id: str, request: Request) -> dict:
    _case_or_404(case_id)
    body = await request.body()
    errors = schema.validate(body)
    store().import_xml(case_id, body, _actor(request))
    return {"imported": True, "schema_errors": [str(e) for e in errors[:20]]}


# --------------------------------------------------------------------- fields
def _write_checked(tree, pf, value: str, *, data_point: str = "", ordinal: int = 1):
    """Never persist an edit that the field cannot read back."""
    candidate = deepcopy(tree)
    written = edit.write(candidate, pf.field_id, value, data_point=data_point,
                         ordinal=ordinal, binding=pf.binding)
    if pf.field_id in ("2.010", "2.011"):
        # The client's second role is found by an anchor ("the party already
        # tagged Client") that a normal read-back would mistake for the
        # value itself.
        actual = edit.read_client_role(candidate.getroot())
    else:
        node = bind.locate(candidate.getroot(), pf.binding, written.data_point,
                           ordinal=ordinal)
        actual = (node.text or "").strip() if node is not None else ""
    # compared with what was stored ("$515k" is stored 515000), not the typing
    if actual != written.new:
        raise ValueError(
            f"Field {pf.field_id} could not be saved to its matching report field. "
            "Check the related type or applicability selection first. No changes were saved.")
    return candidate, written


@router.get("/cases/{case_id}/fields")
def case_fields(case_id: str, section: int | None = Query(None),
                only_filled: bool = Query(False), slim: bool = Query(False)) -> dict:
    """The form: every field the specification places on the page, with values.

    Each field carries where its value came from, so any figure on the report
    can be traced to the data point and xPath that produced it.
    """
    _case_or_404(case_id)
    # every field and the H-1 rules over the whole document cost about a
    # second; the answer depends on the document alone, so it is made once per
    # version of it, not on every open of the editor
    if slim is not True:                 # also when called directly, with the Query default
        return store()._memo(f"fields:{section}:{only_filled}", case_id,
                             lambda: _case_fields(case_id, section, only_filled))
    # the rail shows which fields hold a value, never the findings: skip the
    # H-1 run (a quarter of a second on every version of the document)
    full = store()._memo(f"fields-slim:{section}:{only_filled}", case_id,
                         lambda: _case_fields(case_id, section, only_filled, findings=False))
    # what the editor's rail needs: each section and which of its fields hold
    # a value -- a few kilobytes instead of two megabytes of field definitions
    return {"sections": [{"number": sec["number"], "name": sec["name"], "tab": sec["tab"],
                          "fields": [{"field_id": f["field_id"], "value": f["value"]}
                                     for f in sec["fields"]]}
                         for sec in full["sections"]]}


def _case_fields(case_id: str, section: int | None, only_filled: bool,
                 findings: bool = True) -> dict:
    from uad import report_types
    tree = store().tree(case_id)
    root = tree.getroot()
    findings = report_types.evaluate(tree) if findings else []   # H-1, or H-2 / H-3 by kind
    by_field: dict[str, list[dict]] = {}
    for f in findings:
        if f.status == compliance.FINDING and f.field_id:
            by_field.setdefault(f.field_id, []).append(f.to_json())

    kind = report_types.kind_of(tree)
    if kind == report_types.URAR:
        model, section_list, tabs = bind.page_model(), bind.SECTIONS, bind.TAB_NAME
    else:
        # an update / completion report: its own sections and fields (A-2 / A-3)
        section_list = [(int(n), name) for n, name in report_types.spec(kind)["sections"].items()]
        tabs, model = {}, {}
        for fid in report_types.fields(kind):
            b = report_types.binding(fid)
            if b is None:
                continue
            number = int(report_types.split(fid)[1].split(".")[0])
            model.setdefault(number, []).append(bind.PageField(
                field_id=fid, label=b.label, section=b.section, subsection=b.subsection,
                column=0, indent=0, binding=b))
    sections = []
    for number, name in section_list:
        if section is not None and number != section:
            continue
        fields = model.get(number, [])
        if not fields:
            continue
        rows = []
        for pf in fields:
            groups = bind.read_groups(root, pf.binding, ordinal=pf.ordinal)
            parts = [p for g in groups for p in g]
            text = bind.display_value(groups, pf.binding)
            if only_filled and not text:
                continue
            try:
                dp = edit.choose_data_point(pf.binding)
            except KeyError:
                dp = {}
            # A printed value may contain currency symbols, units or several
            # data points. Editing must use the XML value of the write target.
            target = dp.get("mismo", "")
            node = bind.locate(root, pf.binding, target, ordinal=pf.ordinal) if target else None
            rows.append({
                "field_id": pf.field_id,
                "label": pf.label,
                "subsection": pf.subsection,
                "column": pf.column,
                "indent": pf.indent,
                "ordinal": pf.ordinal,
                "group": pf.group,
                # what the report prints; an answer B-1 prints nothing for
                # ("<<Does Not Display>>") still reads as answered here
                "value": text or bind.answer_label((node.text or "").strip() if node is not None else ""),
                "printed": text,
                "edit_value": (node.text or "").strip() if node is not None else "",
                "edit_data_point": target,
                "definition": dp.get("definition", ""),
                "editors": [
                    {
                        "data_point": point["mismo"],
                        "value": next((v for n, v in parts if n == point["mismo"]), ""),
                        "format": point.get("format_type", ""),
                        "definition": point.get("definition", ""),
                        "options": [{"value": o["value"],
                                     "label": bind.answer_label(o["value"], o.get("display") or "")}
                                    for o in point.get("enumerations", []) if o.get("value")],
                    }
                    for point in {d["mismo"]: d for d in pf.binding.data_points
                                  if d.get("mismo") and not d.get("attribute")}.values()
                ],
                "raw": [{"data_point": n, "value": v} for n, v in parts],
                "format": dp.get("format_type", ""),
                "format_details": dp.get("format_details", ""),
                "conditionality": dp.get("conditionality", ""),
                "conditionality_details": dp.get("conditionality_details", ""),
                "options": [
                    {"value": o["value"], "label": bind.answer_label(o["value"], o.get("display") or "")}
                    for o in dp.get("enumerations", []) if o.get("value")],
                "data_points": [d.get("mismo") for d in pf.binding.data_points
                                if d.get("mismo")],
                "xpath": dp.get("xpath", ""),
                "source": dp.get("source", ""),
                "display_rules": pf.binding.display_rules,
                "findings": by_field.get(pf.field_id, []),
            })
        sections.append({"number": number, "name": name,
                         "tab": tabs.get(number, name), "fields": rows})
    return {"sections": sections}


# --------------------------------------------------------------- table cells
def _new_instance(root, dp: dict, base):
    """Add another instance of the repeating container a data point lives in,
    next to the ones already there, and return it."""
    M_ = f"{{{bind.MISMO}}}"
    segments = [t for t in dp.get("xpath", "").strip("/").split("/") if t and t != "MESSAGE"]
    plural = [i for i in range(1, len(segments)) if bind.is_plural_of(segments[i - 1], segments[i])]
    if not plural:
        return None
    i = plural[-1]
    container = segments[i]
    if base is None and "PROPERTY" in segments:
        base = bind.subject(root)
    start = base if base is not None else root
    # a sibling that already exists names the parent
    for existing in start.iter(f"{M_}{container}"):
        return edit.insert_ordered(existing.getparent(), container)
    upto = segments[:i]
    if base is not None:
        tag = etree.QName(base).localname
        if tag in upto:
            upto = upto[upto.index(tag) + 1:]
    holder = start
    for depth in range(len(upto), 0, -1):
        found = start.find("/".join(f"{M_}{t}" for t in upto[:depth]))
        if found is not None:
            holder, upto = found, upto[depth:]
            break
    parent, _ = edit.ensure_path(holder, upto)
    return edit.insert_ordered(parent, container)

def _new_defect(root, dp: dict, owner):
    """A new DEFECT under the owner's PROPERTY, linked to the owner (a
    PROPERTY_UNIT, IMPROVEMENT, CAR_STORAGE or AMENITY) by arcrole."""
    from uad import sources
    M_, XL = f"{{{bind.MISMO}}}", "{http://www.w3.org/1999/xlink}"
    prop = next((a for a in owner.iterancestors(f"{M_}PROPERTY")), None) or bind.subject(root)
    defect = _new_instance(root, dp, prop)
    if defect is None:
        raise ValueError("the defect row could not be created")
    tag = etree.QName(owner).localname
    if not owner.get(f"{XL}label"):
        owner.set(f"{XL}label", edit._free_label(root, tag))
    defect.set(f"{XL}label", edit._free_label(root, f"DEFECT_{tag}"))
    rel = edit.insert_ordered(sources._relationships(root), "RELATIONSHIP")
    rel.set(f"{XL}arcrole", f"urn:fdc:mismo.org:2009:residential/DEFECT_ContainsDefectOf_{tag}")
    rel.set(f"{XL}from", defect.get(f"{XL}label"))
    rel.set(f"{XL}to", owner.get(f"{XL}label"))
    return defect


def _instance_count(root, binding, data_point: str, scope) -> tuple[int, str]:
    """How many instances of this field's repeating container exist, and its tag."""
    node = bind.locate(root, binding, data_point, scope, 1)
    if node is None:
        return 0, ""
    container = bind.find_path(root, bind.instance_of(node))
    if container is None:
        return 0, ""
    parent = container.getparent()
    return len(parent.findall(container.tag)), etree.QName(container).localname


@router.patch("/cases/{case_id}/cells/{field_id}")
def set_cell(case_id: str, field_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Write one table cell, inside the instance its row stands for.

    ``key`` is the path of the row's repeating container.  A fixed row that has
    no instance yet sends the field that identifies it (``sel``) and its label
    (``label``): the instance is created with that value first.  The empty line
    under a repeating table sends ``new``: a new instance is created.  Nothing
    is saved unless the value reads back and the document still validates.
    """
    _case_or_404(case_id)
    st = store()
    try:
        binding = edit._binding_for(field_id)
    except KeyError:
        raise HTTPException(404, f"no field {field_id}")
    candidate = deepcopy(st.tree(case_id))
    root = candidate.getroot()
    value = str(body.get("value", ""))
    key = str(body.get("key") or "")
    parts = None
    base = None
    if body.get("scope"):
        base = bind.find_path(root, str(body["scope"]))
    try:
        dp = edit.choose_data_point(binding, body.get("data_point", ""))
        scope = None
        if key:
            scope = bind.find_path(root, key)
            if scope is None:
                raise ValueError("that row is no longer in the report; reload it")
            from uad.report import form as _form
            if (not value.strip() and _form.repeats_as_list(field_id)
                    and dp.get("mismo") == (_form.printed_point(field_id) or dp.get("mismo"))
                    and etree.QName(scope).localname == bind.repeating_container(dp.get("xpath", ""))):
                # clearing one value of a list removes its whole block (the
                # amenity and its description), never leaving half of it
                holder = scope.getparent()
                holder.remove(scope)
                if not len(holder) and holder.getparent() is not None:
                    holder.getparent().remove(holder)
                st.save_tree(case_id, candidate)
                st.invalidate(case_id, _actor(request), f"{field_id} value removed")
                return {"value": "", "key": "", "removed": True, "state": st.get(case_id).state}
        elif body.get("sel") and body.get("label"):
            sel_binding = edit._binding_for(str(body["sel"]))
            sel_dp = edit.choose_data_point(sel_binding)
            label = str(body["label"]).strip().casefold()
            want = next((v for v, shown in report_form.choices_for(str(body["sel"]))
                         if label in (v.casefold(), shown.casefold())), str(body["label"]))
            n, _tag = _instance_count(root, sel_binding, sel_dp["mismo"], base)
            # a row of this kind already made (the row's first answer, saved
            # before the page knew its key): the value goes in that one
            scope = None
            for k in range(1, n + 1):
                there = bind.locate(root, sel_binding, sel_dp["mismo"], base, k)
                if there is not None and (there.text or "").strip() == want:
                    scope = bind.find_path(root, bind.instance_of(there))
                    break
            if scope is None:
                made = edit.write(candidate, str(body["sel"]), want, ordinal=n + 1,
                                  binding=sel_binding, scope=base)
                node = bind.locate(root, sel_binding, made.data_point, base, n + 1)
                if node is None:
                    raise ValueError("the row could not be created")
                scope = bind.find_path(root, bind.instance_of(node))
        elif body.get("new") and "/DEFECTS/DEFECT/" in dp.get("xpath", "") \
                and base is not None and etree.QName(base).localname == "DEFECT":
            scope = base                  # the row is that defect already
        elif body.get("new") and "/DEFECTS/DEFECT/" in dp.get("xpath", "") \
                and base is not None and etree.QName(base).localname != "PROPERTY":
            # a defect row in a unit's, building's or garage's own table: the
            # DEFECT lives under the PROPERTY and is tied to what it is in by
            # DEFECT_ContainsDefectOf_<it> (D-1 2-4), which is how it is read
            scope = _new_defect(root, dp, base)
        elif body.get("new"):
            scope = _new_instance(root, dp, base)
            if scope is None:
                raise ValueError("the row could not be created")
            # an update / completion report's row knows which table it is in
            from uad import report_types
            report_types.stamp_instance(scope, field_id)
        if scope is None and body.get("cat") and "VALUATION_COMMENTAR" in dp.get("xpath", ""):
            # a row's impact and comment live in the commentary of its category
            cat = str(body["cat"])
            M_ = f"{{{bind.MISMO}}}"
            scope = next((vc for vc in root.iter(f"{M_}VALUATION_COMMENTARY")
                          if (vc.findtext(f"{M_}ValuationAnalysisCategoryType") or "").strip() == cat), None)
            if scope is None:
                segments = [t for t in dp["xpath"].strip("/").split("/") if t and t != "MESSAGE"]
                upto = segments[:segments.index("VALUATION_COMMENTARIES") + 1]
                holder = root
                for depth in range(len(upto), 0, -1):
                    found = root.find("/".join(f"{M_}{t}" for t in upto[:depth]))
                    if found is not None:
                        holder, upto = found, upto[depth:]
                        break
                parent, _ = edit.ensure_path(holder, upto)
                scope = edit.insert_ordered(parent, "VALUATION_COMMENTARY")
                edit.insert_ordered(scope, "ValuationAnalysisCategoryType").text = cat
        if scope is None:
            scope = base
        from uad.report import form as _form
        target = (_form.data_source_target(field_id)
                  if "DATA_SOURCES/DATA_SOURCE" in dp.get("xpath", "") else "")
        if scope is not None and target and target != "PROPERTY":
            # a source tied by arcrole to its row (a transfer's Data Source):
            # the row is the scope, and the value reads back through the link
            from uad import sources
            written = edit.write(candidate, field_id, value, binding=binding,
                                 data_point=dp.get("mismo", ""), scope=scope)
            here = next(scope.iter(f"{{{bind.MISMO}}}{target}"), None)
            have = [(ds.findtext(f"{{{bind.MISMO}}}{written.data_point}") or "").strip()
                    for ds in (sources.linked(root, here, target) if here is not None else [])]
            if value.strip() and value.strip() not in have:
                raise ValueError(f"Field {field_id} could not be saved to this row. No changes were saved.")
            arc_written = written
        else:
            arc_written = None
        if arc_written is None and scope is not None:
            # write inside the nearest element on this data point's own path
            segments = [t for t in dp.get("xpath", "").strip("/").split("/") if t]
            holder = scope
            while holder is not None and etree.QName(holder).localname not in segments:
                holder = holder.getparent()
            if holder is None:
                raise ValueError(f"Field {field_id} does not belong to this row.")
            scope = holder
        parts = (edit.split_address(value, binding)
                 if arc_written is None and not body.get("data_point") and edit.is_address(binding) else None)
        if parts:
            # a whole address typed into one cell: stored as its parts
            for dp_name, part in parts.items():
                written = edit.write(candidate, field_id, part, binding=binding,
                                     data_point=dp_name, scope=scope)
            arc_written = written
        if arc_written is None:
            written = edit.write(candidate, field_id, value, binding=binding,
                                 data_point=body.get("data_point", ""), scope=scope)
            back = bind.locate(root, binding, written.data_point, scope, 1)
            got = (back.text or "").strip() if back is not None else ""
            if got != written.new:
                raise ValueError(f"Field {field_id} could not be saved to this row. No changes were saved.")
            if written.new and scope is not None:
                # a value typed is a value available (PaymentAmountAvailableIndicator)
                for d in binding.data_points:
                    if (d.get("mismo", "").endswith("AvailableIndicator")
                            and d.get("mismo") != written.data_point):
                        edit.write(candidate, field_id, "true", binding=binding,
                                   data_point=d["mismo"], scope=scope)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    st.save_tree(case_id, candidate)          # refuses a write that adds a schema error
    st.invalidate(case_id, _actor(request), f"{field_id} changed")
    st.log(case_id, _actor(request), "edited", f"{field_id} (table) {written.old!r} -> {written.new!r}")
    new_key = bind.stable_path(scope) if scope is not None else ""
    shown = bind.trim_cents(bind.display_value([(written.data_point, written.new)], binding),
                            binding.label) if written.new else ""
    if parts:
        shown = value.strip()                # the address as typed, now stored as its parts
    return {"value": shown, "key": new_key, "state": st.get(case_id).state}


@router.patch("/cases/{case_id}/client-role")
def set_client_role(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Client/[Party Role Type] (A-1 2.010/2.011): the client party, and the
    second role it plays -- Attorney, Investor, Lender, Appraisal Management
    Company, or Other with its description (H-1 UAD1542, UAD1543)."""
    from uad.report import form as report_form
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    root = tree.getroot()
    M_ = f"{{{bind.MISMO}}}"
    value = str(body.get("value", "")).strip()
    point = str(body.get("data_point", ""))
    allowed = [e["value"] for e in edit._binding_for("2.011").data_points[0].get("enumerations") or []]
    party = next((p for p in root.iter(f"{M_}PARTY")
                  if any((r.text or "").strip() == "Client" for r in p.iter(f"{M_}PartyRoleType"))), None)
    if party is None:
        parties = next(root.iter(f"{M_}PARTIES"))
        party = edit.insert_ordered(parties, "PARTY")
        role, _ = edit.ensure_path(party, ["ROLES", "ROLE"])
        detail, _ = edit.ensure_path(role, ["ROLE_DETAIL"])
        edit.insert_ordered(detail, "PartyRoleType").text = "Client"
    detail, _shown = report_form.client_role(party)
    if detail is None:
        roles, _ = edit.ensure_path(party, ["ROLES"])
        role = edit.insert_ordered(roles, "ROLE")
        detail, _ = edit.ensure_path(role, ["ROLE_DETAIL"])
    kind = detail.find(f"{M_}PartyRoleType")
    other = detail.find(f"{M_}PartyRoleTypeOtherDescription")
    if point == "PartyRoleTypeOtherDescription":
        if (kind is None or (kind.text or "") != "Other"):
            raise HTTPException(422, "Pick Other before describing it.")
        if other is None:
            other = edit.insert_ordered(detail, "PartyRoleTypeOtherDescription")
        other.text = value[:50]
    else:
        if value and value not in allowed:
            raise HTTPException(422, f"{value!r} is not one of {allowed}")
        if kind is None:
            kind = edit.insert_ordered(detail, "PartyRoleType")
        if not value:
            detail.getparent().getparent().remove(detail.getparent())
        else:
            kind.text = value
            if value != "Other" and other is not None:
                detail.remove(other)
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "client role changed")
    _d, shown = report_form.client_role(party)
    return {"value": shown, "state": st.get(case_id).state}


@router.patch("/cases/{case_id}/fields/{field_id}")
def set_field(case_id: str, field_id: str, request: Request,
              body: dict = Body(...)) -> dict:
    case = _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    if field_id.split(".")[0] == "1":
        # B-1 chapter 01: the Summary redisplays the report; its values are
        # entered where they come from, never here
        raise HTTPException(422, "The Summary redisplays the rest of the report and cannot be edited.")
    if parties.name_role(field_id) and not body.get("data_point"):
        # a party's name: person or organisation, one party per name, and the
        # owner as B-1 Case A / B / C -- never another party's name
        candidate = deepcopy(tree)
        result = parties.write(candidate, field_id, str(body.get("value", "")), str(body.get("kind", "")))
        st.save_tree(case_id, candidate)
        st.invalidate(case_id, _actor(request), f"{field_id} changed")
        st.log(case_id, _actor(request), "edited", f"{field_id} -> {result['value']!r}")
        return {**result, "state": st.get(case_id).state}
    try:
        pf = edit.field(field_id)
    except KeyError:
        raise HTTPException(404, f"no field {field_id}")
    try:
        ordinal = int(body.get("ordinal") or pf.ordinal)
        if ordinal < 1:
            raise ValueError("The field instance must be at least 1")
        value = str(body.get("value", ""))
        # A whole address typed where the report prints one is stored as the
        # parts A-1 defines (street, unit, city, state, ZIP), each read back.
        parts = (edit.split_address(value, pf.binding)
                 if not body.get("data_point") and edit.is_address(pf.binding) else None)
        if parts:
            for dp_name, part in parts.items():
                tree, written = _write_checked(tree, pf, part, data_point=dp_name, ordinal=ordinal)
        else:
            tree, written = _write_checked(tree, pf, value,
                                           data_point=body.get("data_point", ""),
                                           ordinal=ordinal)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    if field_id == "3.000" and case.name == NEW_NAME and value.strip():
        # an unnamed report takes the subject's address as its name
        st.rename(case_id, value.strip())
    reshaped = _reshape_if_needed(case_id, case, st.tree(case_id), tree)
    if reshaped is not None:
        tree = reshaped.tree
    # A count typed where the report asks for it (3.005 units, 3.006 ADUs) is
    # a shortcut for the structure operations: the tree is made to hold that
    # many, and the counts are then read back from the tree (uad/structure.py).
    said: list[str] = []
    if written.data_point in ("LivingUnitExcludingADUCount", "AccessoryDwellingUnitTotalCount") \
            and written.new.isdigit():
        from uad import structure
        candidate, lost = deepcopy(tree), []
        op = structure.set_units if written.data_point == "LivingUnitExcludingADUCount" else structure.set_adus
        said = op(candidate.getroot(), int(written.new), lost)
        if lost and not body.get("confirm"):
            return JSONResponse({"detail": "Removing a unit would discard what was entered for it.",
                                 "lost": lost[:40], "confirm": True}, status_code=409)
        tree = candidate
    if reshaped is not None:
        st.save_tree(case_id, tree, allow_invalid=True)
        st.set_shape(case_id, reshaped.template, reshaped.property_type)
    else:
        st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), f"{field_id} changed")
    st.log(case_id, _actor(request), "edited",
           f"{field_id} {written.old!r} -> {written.new!r}")
    if reshaped is not None:
        st.log(case_id, _actor(request), "reshaped",
               f"now {reshaped.property_type} on the {reshaped.template} structure; "
               f"{reshaped.carried} values carried, {len(reshaped.failed)} not placed")
    root = tree.getroot()
    groups = bind.read_groups(root, pf.binding, ordinal=ordinal)
    return {"written": written.to_json(),
            "structure": said,
            "reshaped": None if reshaped is None else {
                "property_type": reshaped.property_type,
                "type_name": templates.PROPERTY_TYPES.get(reshaped.property_type, reshaped.property_type),
                "template": reshaped.template, "carried": reshaped.carried,
                "not_placed": [f.get("label") or f.get("fid") for f in reshaped.failed][:20]},
            # what the report prints: whole dollars without cents, as D-1 sets them
            "value": bind.trim_cents(bind.display_value(groups, pf.binding), pf.label),
            "state": st.get(case_id).state}


# ------------------------------------------------------------ structure engine
# ------------------------------------------------------------ rooms & levels
def _rooms_change(case_id: str, request: Request, fn, what: str) -> dict:
    from uad import rooms
    st = store()
    candidate = deepcopy(st.tree(case_id))
    root = candidate.getroot()
    try:
        said = fn(root, rooms)
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc).strip("'"))
    st.save_tree(case_id, candidate)
    st.invalidate(case_id, _actor(request), what)
    st.log(case_id, _actor(request), "rooms", what)
    return {"ok": True, "said": said}


@router.post("/cases/{case_id}/rooms")
def add_room(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """One more room of a type on a level (Level and Room Detail, 10.029-10.033);
    Levels in Unit, Total Bedrooms and Total Bathrooms follow (uad/rooms.py)."""
    _case_or_404(case_id)
    level_key, kind, other = str(body.get("level") or ""), str(body.get("type") or ""), str(body.get("other") or "")

    def fn(root, rooms):
        level = rooms.level_at(root, level_key)
        rooms.add_room(level, kind, other)
        return rooms.recount(rooms.unit_of(level)) or {}
    return _rooms_change(case_id, request, fn, f"room added: {other or kind}")


@router.delete("/cases/{case_id}/rooms")
def remove_room(case_id: str, request: Request, level: str = Query(...),
                type: str = Query(...), other: str = Query("")) -> dict:
    _case_or_404(case_id)

    def fn(root, rooms):
        lv = rooms.level_at(root, level)
        if not rooms.remove_room(lv, type, other):
            raise ValueError("there is no such room on that level")
        return {}
    return _rooms_change(case_id, request, fn, f"room removed: {other or type}")


@router.delete("/cases/{case_id}/levels")
def remove_level(case_id: str, request: Request, level: str = Query(...)) -> dict:
    _case_or_404(case_id)

    def fn(root, rooms):
        n = rooms.remove_level(rooms.level_at(root, level))
        return {"rooms_removed": n}
    return _rooms_change(case_id, request, fn, "level removed")


@router.post("/cases/{case_id}/flooring")
def add_flooring(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Another flooring type in a unit's Interior Features (B-1 10.045: one row
    per flooring type)."""
    _case_or_404(case_id)
    unit_key, kind, other = str(body.get("unit") or ""), str(body.get("type") or ""), str(body.get("other") or "")

    def fn(root, rooms):
        rooms.add_flooring(rooms.unit_at(root, unit_key), kind, other)
        return {}
    return _rooms_change(case_id, request, fn, f"flooring added: {other or kind}")


#: repeated rows the editor may remove whole, by their own x
REMOVABLE_ROWS = {"FLOOR_COVERING", "AMENITY"}


@router.delete("/cases/{case_id}/rows")
def remove_row(case_id: str, request: Request, key: str = Query(...), tag: str = Query(...)) -> dict:
    _case_or_404(case_id)
    if tag not in REMOVABLE_ROWS:
        raise HTTPException(400, f"{tag} rows are not removed this way")

    def fn(root, rooms):
        rooms.remove_block(root, key, tag)
        return {}
    return _rooms_change(case_id, request, fn, f"{tag.lower()} row removed")


@router.get("/cases/{case_id}/structure")
def get_structure(case_id: str) -> dict:
    """Dwellings with their units, outbuildings, and the counts read from them."""
    from uad import structure
    _case_or_404(case_id)
    return structure.tree(store().tree(case_id).getroot())


@router.get("/cases/{case_id}/structure/loss")
def structure_loss(case_id: str, key: str = Query(...)) -> dict:
    """What removing this dwelling, unit, ADU or outbuilding would discard."""
    from uad import structure
    _case_or_404(case_id)
    root = store().tree(case_id).getroot()
    node = structure.find(root, key)
    if node is None:
        raise HTTPException(404, "that part of the property is no longer in the report")
    return {"lost": structure.loss(root, node)}


def _structure_change(case_id: str, request: Request, fn, what: str) -> dict:
    from uad import report_types, structure
    st = store()
    candidate = deepcopy(st.tree(case_id))
    if report_types.kind_of(candidate) != report_types.URAR:
        raise HTTPException(409, "an update or completion report has no dwellings or units of its own")
    try:
        said = fn(candidate.getroot())
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc).strip("'"))
    st.save_tree(case_id, candidate)
    st.invalidate(case_id, _actor(request), what)
    st.log(case_id, _actor(request), "structure", "; ".join(said) or what)
    return {**structure.tree(candidate.getroot()), "said": said}


@router.post("/cases/{case_id}/structure")
def add_structure(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Add a dwelling, a living unit, an ADU (in a dwelling or an outbuilding)
    or an outbuilding.  Counts 3.005 / 3.006 / 3.007 follow from the tree."""
    from uad import structure
    _case_or_404(case_id)
    what = str(body.get("add") or "")
    ident = str(body.get("identifier") or "")
    dwelling = int(body.get("dwelling") or 0)
    if what == "dwelling":
        def fn(r): return structure.add_dwelling(r, ident)
    elif what == "unit":
        def fn(r): return structure.add_unit(r, dwelling, ident)
    elif what == "adu" and body.get("location") == "outbuilding":
        kind = str(body.get("type") or "StandaloneADU")
        def fn(r):
            if kind == "ADUGarage":           # B-1 p217: Other + "ADUGarage"
                return structure.add_outbuilding(r, "Other", "ADUGarage", adu=True)
            return structure.add_outbuilding(r, kind, adu=True)
    elif what == "adu":
        def fn(r): return structure.add_unit(r, dwelling, ident or "ADU", adu=True)
    elif what == "outbuilding":
        kind, other = str(body.get("type") or "Other"), str(body.get("other") or "")
        def fn(r): return structure.add_outbuilding(r, kind, other)
    else:
        raise HTTPException(400, "add one of: dwelling, unit, adu, outbuilding")
    return _structure_change(case_id, request, fn, f"added a {what}")


@router.delete("/cases/{case_id}/structure")
def remove_structure(case_id: str, request: Request, key: str = Query(...)) -> dict:
    """Remove a dwelling, unit, ADU or outbuilding -- and only what exists
    because of it (its comparable unit rows, rental comparisons, defects).
    Ask ``/structure/loss`` first to show the appraiser what goes."""
    from uad import structure
    _case_or_404(case_id)
    return _structure_change(case_id, request, lambda r: structure.remove(r, key),
                             "removed part of the property")


def _reshape_if_needed(case_id: str, case, before_tree, after_tree):
    """One report, shaped by its answers (uad/shape.py): when a determining
    answer (units, ADUs, project legal structure, construction method,
    attachment...) changes what kind of property this is, the report is
    rebuilt on the closest official structure with every value carried."""
    from uad import report_types, shape
    if report_types.kind_of(after_tree) != report_types.URAR:
        return None              # an update / completion report has one shape
    before = shape.determinants(before_tree.getroot())
    after = shape.determinants(after_tree.getroot())
    if not shape.needed(before, after):
        return None
    template = shape.best_template(after, prefer=case.template)
    if not template or template == case.template:
        return None
    return shape.reshape(after_tree, template)


@router.get("/cases/{case_id}/setup")
def get_setup(case_id: str) -> dict:
    """The report's setup: its property type, units and approaches (uad/setup.py)."""
    _case_or_404(case_id)
    from uad import setup
    return setup.current(store().tree(case_id).getroot())


@router.put("/cases/{case_id}/setup")
def put_setup(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """State the property type (rebuilding the report on its structure, every
    value carried) and the approaches developed -- B-1's "Not on report"
    indicators that show Rental Information, Income and Cost Approach."""
    case = _case_or_404(case_id)
    st = store()
    from uad import setup
    try:
        tree, template, notes, failed = setup.apply(
            st.tree(case_id), case.template, str(body.get("property_type", "")),
            int(body.get("units") or 1), dict(body.get("approaches") or {}))
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    st.save_tree(case_id, tree, allow_invalid=template is not None)
    if template is not None:
        st.set_shape(case_id, template, templates.get(template).property_type)
    st.invalidate(case_id, _actor(request), "report setup changed")
    st.log(case_id, _actor(request), "setup", "; ".join(notes) or "approaches stated")
    return {**setup.current(tree.getroot()), "notes": notes,
            "not_placed": [f.get("label") or f.get("fid") for f in failed][:20],
            "reshaped": template is not None, "state": st.get(case_id).state}


@router.post("/cases/{case_id}/fields")
def set_fields(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Set many fields at once -- what a headless intake uses."""
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    results, failures = [], []
    for item in body.get("fields", []):
        fid = item.get("field_id", "")
        try:
            if fid.split(".")[0] == "1":
                raise ValueError("The Summary redisplays the rest of the report and cannot be edited.")
            if parties.name_role(fid) and not item.get("data_point"):
                candidate = deepcopy(tree)
                done = parties.write(candidate, fid, str(item.get("value", "")), str(item.get("kind", "")))
                tree = candidate
                results.append({"field_id": fid, "new": done["value"]})
                continue
            pf = edit.field(fid)
            ordinal = int(item.get("ordinal") or pf.ordinal)
            if ordinal < 1:
                raise ValueError("The field instance must be at least 1")
            tree, written = _write_checked(tree, pf, str(item.get("value", "")),
                                           data_point=item.get("data_point", ""),
                                           ordinal=ordinal)
            results.append(written.to_json())
        except (KeyError, ValueError) as exc:
            failures.append({"field_id": fid, "error": str(exc)})
    if results:
        st.save_tree(case_id, tree)
        st.invalidate(case_id, _actor(request), f"{len(results)} field(s) changed")
        st.log(case_id, _actor(request), "edited", f"{len(results)} fields")
    return {"written": results, "failed": failures}


# -------------------------------------------------------------- preferences
# How the appraiser has arranged the editor for this report -- column widths,
# chiefly.  It belongs to the case, so the grid a colleague opens is the grid
# that was set up, but it is not part of the deliverable and never enters the
# package.
def _prefs_path(case_id: str) -> Path:
    return store().folder(case_id) / "editor.json"


@router.get("/cases/{case_id}/prefs")
def get_prefs(case_id: str) -> dict:
    _case_or_404(case_id)
    path = _prefs_path(case_id)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {}


@router.put("/cases/{case_id}/prefs")
def set_prefs(case_id: str, body: dict = Body(...)) -> dict:
    _case_or_404(case_id)
    merged = {**get_prefs(case_id), **body}
    _prefs_path(case_id).write_text(json.dumps(merged, indent=1),
                                    encoding="utf-8")
    if {"exhibitSlots", "fills", "rentalLayout"} & set(body):
        renderer().changed(case_id)       # the form draws these
    return merged


# ------------------------------------------------------------ field guidance
@router.get("/cases/{case_id}/guide/{field_id}")
def field_guide(case_id: str, field_id: str) -> dict:
    """What the specifications say about one field, and how it stands now.

    A-1 gives each data point's definition, format and whether it is required
    ('R'), required under a condition ('CR', with the condition) or optional;
    H-1 gives the rules that check it.  Each rule carries its live status for
    this report: failing (a finding on this field), to be read by the
    appraiser (a rule H-1 leaves to judgement), or met."""
    _case_or_404(case_id)
    try:
        pf = edit.field(field_id)
    except KeyError:
        raise HTTPException(404, f"no field {field_id}")
    b = pf.binding
    points, seen = [], set()
    for d in b.data_points:
        name = d.get("mismo") or ""
        if not name or name in seen:
            continue
        seen.add(name)
        details = str(d.get("format_details") or "")
        cond, scope = conditions.read(d.get("conditionality_details") or "")
        fmt = d.get("format_type") or ""
        points.append({
            "name": name, "label": conditions.words(name), "definition": d.get("definition") or "",
            "format": fmt, "max": int(details) if fmt == "String" and details.isdigit() else None,
            "required": d.get("conditionality") or "",
            "condition": cond, "scope": scope,
            "values": len([e for e in d.get("enumerations") or [] if e.get("value")]),
        })
    # required within its block when the only condition was the block itself
    for p in points:
        if p["required"] == "CR" and not p["condition"]:
            p["required"] = "R"
        elif p["required"] == "CR" and p["condition"] == "there is one":
            p["required"] = "O"
    req = [p["required"] for p in points]
    requirement = ("R" if "R" in req else "CR" if "CR" in req else "O" if req else "")
    multi = len(points) > 1
    when = sorted({(f"{p['label']}: " if multi else "") + "when " + p["condition"]
                         for p in points if p["required"] == "CR" and p["condition"]})
    names = {p["name"] for p in points}

    def norm(label: str) -> str:
        return re.sub(r"\s*\(%\w+%\)", "", label or "").strip().casefold()
    own = norm(b.label)
    # the rule must be about this field, not only the same data point --
    # AddressLineText is checked for the subject, every comparable, ...
    mine = [r for r in compliance.rules() if r.data_point in names and norm(r.label) == own]
    codes = {r.message_id for r in mine}
    # a finding is filed under one field; a value printed twice (the Summary's
    # 1.001 repeats Reconciliation's 26.007) fails in both places
    failing = {}
    for i in store().review(case_id).to_json()["items"]:
        if i.get("severity") not in ("Fatal", "Warning"):
            continue
        if i.get("field_id") == field_id or (i["code"] in codes and norm(i.get("label")) == own):
            failing.setdefault(i["code"], i)
    rules = []
    for r in mine:
        status = ("fail" if r.message_id in failing
                  else "read" if not r.executable or r.severity == "Review" else "ok")
        rules.append({"id": r.message_id, "severity": r.severity, "text": r.text, "status": status})
    order = {"fail": 0, "read": 1, "ok": 2}
    rules.sort(key=lambda x: (order[x["status"]], x["id"]))
    maxes = [p["max"] for p in points if p["max"]]
    scope = sorted({x for p in points if p["required"] in ("R", "CR") for x in p["scope"]})
    return {"field_id": field_id, "label": b.label, "section": b.section,
            "subsection": getattr(b, "subsection", "") or "",
            "requirement": requirement, "conditions": when, "scope": scope,
            "max": max(maxes) if maxes else None, "points": points, "rules": rules,
            "problems": [{"code": i["code"], "severity": i["severity"], "message": i["message"]}
                         for i in failing.values()]}


# --------------------------------------------------------------- review master
@router.get("/cases/{case_id}/review")
def case_review(case_id: str, include_review: bool = Query(True)) -> dict:
    """Every compliance finding, from all three authorities, in one list."""
    case = _case_or_404(case_id)
    st = store()
    report = st.review(case_id, include_review=include_review)
    out = report.to_json()
    out["by_section"] = {
        name: [i.to_json() for i in items]
        for name, items in report.by_section().items()}
    out["state"] = case.state
    out["acknowledged"] = case.acknowledged
    out["sections_present"] = st.sections_present(case_id)
    out["blockers"] = st.blockers(case_id)
    return out


@router.get("/cases/{case_id}/integrity")
def case_integrity(case_id: str, deep: bool = Query(False)) -> dict:
    """Whether the report, the document and the package agree with each other.

    ``deep`` also draws the report and compares the figures on the page with
    the ones in the document, which costs a render.
    """
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    html = ""
    if deep:
        html = flow.build(tree, folder=st.folder(case_id),
                          media=_media_for_render(case_id), screen=False)
    found = integrity.check(tree, st.media(case_id), html=html)
    return {"counts": integrity.counts(found),
            "findings": [f.to_json() for f in found]}


@router.get("/cases/{case_id}/rules")
def rule_coverage() -> dict:
    """What the compliance engine executes, and what it leaves for a reader."""
    rules = compliance.rules()
    kinds: dict[str, int] = {}
    reasons: dict[str, int] = {}
    for r in rules:
        kinds[r.kind] = kinds.get(r.kind, 0) + 1
        if not r.executable:
            reasons[r.reason] = reasons.get(r.reason, 0) + 1
    return {"total": len(rules),
            "executable": sum(1 for r in rules if r.executable),
            "by_kind": kinds, "not_executed": reasons,
            "schema_version": schema.schema_version()}


# ---------------------------------------------------------- comparable grid
@router.get("/cases/{case_id}/comparables")
def case_comparables(case_id: str, kind: str = Query("sales")) -> dict:
    """The comparable grid as rows, which is how it is entered and printed.

    Each row is one line of the grid -- Property Address, Sale Price, a
    Condition adjustment -- and carries the Report Field ID to write for the
    subject, for each comparable, and for that comparable's adjustment.  The
    editor is then the grid, not a form that happens to feed one.
    """
    _case_or_404(case_id)
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    tree = store().tree(case_id)
    root = tree.getroot()
    _sheet, role, title = comparables.SHEETS[kind]
    props = comparables.properties(root, role)
    subject = bind.subject(root)

    rows = []
    for spec in comparables.specs(root, kind, every_row=True):
        cells = []
        for prop in props:
            cells.append({
                "value": (comparables.value_for(root, spec.comp_fid, prop, spec)
                          if spec.comp_fid else ""),
                "parts": (comparables.parts_for(root, spec.comp_fid, prop)
                          if spec.comp_fid else {}),
                "adjustment": comparables.adjustment_for(root, spec, prop),
                "adjust_raw": (comparables.adjustment_value(prop, spec.adjust_type)
                               if spec.adjust_type else ""),
            })
        rows.append({
            "options": comparables.options_for(spec.comp_fid or spec.subject_fid),
            "comp_points": comparables.points_for(spec.comp_fid),
            "subject_points": comparables.points_for(spec.subject_fid),
            "subject_parts": (comparables.parts_for(root, spec.subject_fid, subject)
                              if spec.subject_fid else {}),
            "label": spec.label,
            "heading": spec.heading,
            "always": spec.always,
            "adjustable": spec.adjustable,
            "subject_fid": spec.subject_fid,
            "comp_fid": spec.comp_fid,
            "adjust_fid": spec.adjust_fid,
            "adjust_type": spec.adjust_type,
            "item_name": spec.item_name,
            "container": spec.container,
            "new_item": spec.new_item,
            "subject": (comparables.value_for(root, spec.subject_fid, subject, spec)
                        if spec.subject_fid else ""),
            "cells": cells,
        })
    if kind == "rental":
        # the Comparable Rental Properties strip (B-1 23.02) above the grids:
        # its address, data source, lease start and rent are entered here too
        for label, subject_fid, comp_fid in (("Address", "23.02.01", "23.02.03"),
                                             ("Data Source", "", "23.02.04"),
                                             ("Lease Start Date", "", "23.02.05"),
                                             ("Actual Rent", "", "23.02.06")):
            rows.append({
                "options": comparables.options_for(comp_fid), "label": label, "heading": False,
                "always": True, "adjustable": False, "adjust_fid": "", "adjust_type": "",
                "item_name": "", "container": "", "new_item": False,
                "comp_points": comparables.points_for(comp_fid),
                "subject_points": comparables.points_for(subject_fid) if subject_fid else [],
                "subject_parts": comparables.parts_for(root, subject_fid, subject) if subject_fid else {},
                "subject_fid": subject_fid, "comp_fid": comp_fid,
                "subject": comparables.value_for(root, subject_fid, subject) if subject_fid else "",
                "cells": [{"value": comparables.value_for(root, comp_fid, p_),
                           "parts": comparables.parts_for(root, comp_fid, p_),
                           "adjustment": "", "adjust_raw": ""} for p_ in props],
            })
    return {
        "kind": kind, "title": title, "role": role,
        "comparables": [{"index": i + 1,
                         "label": f"Comparable #{i + 1}",
                         "address": comparables.value_for(root, "22.01.17", p),
                         "photo": _comp_photo(case_id, i + 1)}
                        for i, p in enumerate(props)],
        "rows": rows,
    }


def _grid_scope(root, kind: str, number: int):
    """The property a grid cell belongs to -- 0 is the subject column."""
    if number == 0:
        return bind.subject(root)
    _sheet, role, _title = comparables.SHEETS[kind]
    props = comparables.properties(root, role)
    if not 1 <= number <= len(props):
        raise HTTPException(404, f"no comparable #{number}")
    return props[number - 1]


@router.patch("/cases/{case_id}/comparables/{number}/fields/{field_id}")
def set_comparable_field(case_id: str, number: int, field_id: str,
                         request: Request, body: dict = Body(...)) -> dict:
    """Write one cell of the grid, inside the property that cell is about.

    The form's own route cannot serve this: a data point under a PROPERTY is
    taken to be the subject's unless it is told which property is meant, so
    without the scope every comparable's value would be written over the
    subject's.
    """
    _case_or_404(case_id)
    st = store()
    kind = body.get("kind", "sales")
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    tree = st.tree(case_id)
    value = str(body.get("value", ""))
    point = body.get("data_point", "")
    adjust_type = body.get("adjust_type", "")
    if not adjust_type:
        adjust_type = comparables.adjustment_type_of(field_id, kind)
        if not adjust_type:
            try:
                dp_ = edit.choose_data_point(edit.field(field_id).binding, point)
            except (KeyError, ValueError):
                dp_ = {}
            if "COMPARABLE_ADJUSTMENT" in dp_.get("xpath", ""):
                raise HTTPException(422, f"Field {field_id} is an adjustment; say which one "
                                         "(adjust_type, a ComparableAdjustmentType).")

    pf = None
    if not adjust_type:
        try:
            pf = edit.field(field_id)
        except KeyError:
            raise HTTPException(404, f"no field {field_id}")

    candidate = deepcopy(tree)
    scope = _grid_scope(candidate.getroot(), kind, number)
    if scope is None:
        raise HTTPException(404, "this case has no property for that column")
    if body.get("scope") and not adjust_type:
        # a rental grid drawn per subject unit: the cell names the pairing it
        # was read in, and the value is written where the field's own path
        # runs through it (the pairing, its unit, or the property)
        inner = bind.find_path(candidate.getroot(), str(body["scope"]))
        if inner is None:
            try:
                hit = candidate.getroot().getroottree().xpath(str(body["scope"]))
                inner = hit[0] if hit else None
            except etree.XPathError:
                inner = None
        if inner is None or (inner is not scope and scope not in list(inner.iterancestors())):
            raise HTTPException(422, "that cell's block is not part of this column's property")
        scope = comparables._field_scope(field_id, comparables._scopes(inner))
    try:
        if adjust_type:
            written = comparables.write_adjustment(scope, adjust_type, value)
        else:
            # A comparable on a 2-4 unit report has more than one living
            # unit, and the grid asks for bedrooms, bathrooms and area for each
            # of them.  Without the ordinal every unit wrote over unit one, so
            # the second unit of every comparable was unreportable.
            ordinal = int(body.get("ordinal") or 1)
            if ordinal < 1:
                raise ValueError("The field instance must be at least 1")
            written = edit.write(candidate, field_id, value, data_point=point,
                                 ordinal=ordinal, binding=pf.binding,
                                 scope=scope)
            node = bind.locate(candidate.getroot(), pf.binding,
                               written.data_point, scope, ordinal)
            actual = (node.text or "").strip() if node is not None else ""
            if actual != written.new:
                raise ValueError(
                    f"Field {field_id} could not be saved to this comparable. "
                    "No changes were saved.")
    except (KeyError, ValueError) as exc:
        raise HTTPException(422, str(exc))

    st.save_tree(case_id, candidate)
    st.invalidate(case_id, _actor(request), f"{field_id} changed")
    st.log(case_id, _actor(request), "edited",
           f"{field_id} on {'subject' if not number else f'comparable #{number}'}")
    root = candidate.getroot()
    again = scope if body.get("scope") and not adjust_type else _grid_scope(root, kind, number)
    if adjust_type:
        # shown as the report prints it ("-$2,500"), not as stored
        printed = next((r for r in comparables.rows(kind)
                        if r.adjust_type == adjust_type and r.adjust_fid), None)
        shown = (comparables.adjustment_for(root, printed, again) if printed is not None
                 else comparables.adjustment_value(again, adjust_type))
    else:
        shown = comparables.value_for(root, field_id, again)
    return {"value": shown,
            "state": st.get(case_id).state}


@router.put("/cases/{case_id}/comparables/lineitems")
def name_line_item(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Name, rename or remove a row the appraiser adds to a grid.

    B-1 gives each grid group an "[Additional Row]" the appraiser names --
    "Below Grade Exterior Access" -- and A-1 keeps that name against every
    property the grid shows, so naming it here writes it to the subject and to
    every comparable at once.  Renaming follows the same rule, and an empty
    name removes the row from all of them.
    """
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    root = tree.getroot()
    kind = str(body.get("kind") or "sales")
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    container = str(body.get("container") or "")
    adjust_type = str(body.get("adjust_type") or "")
    was = str(body.get("was") or "").strip()
    name = str(body.get("name") or "").strip()
    if not container:
        raise HTTPException(422, "the row does not say where it is kept")
    if not name and not was:
        raise HTTPException(422, "give the row a name")
    _sheet, role, _title = comparables.SHEETS[kind]
    props = comparables.properties(root, role)
    subject = bind.subject(root)
    everywhere = ([subject] if subject is not None else []) + props
    named = comparables.named_row(kind, *_line_row(kind, container))
    if named is None:
        raise HTTPException(422, f"no added-row template for {container}")
    if name and any(name == other
                    for other in comparables.named_values(root, named, everywhere)
                    if other != was):
        raise HTTPException(422, f"this grid already has a row called {name!r}")
    for prop in everywhere:
        node = comparables.named_node(prop, named, was or name,
                                      create=bool(name and not was))
        if node is None:
            if not name:
                continue
            node = comparables.named_node(prop, named, name, create=True)
        if not name:
            node.getparent().remove(node)
            continue
        label = node.find(f"{{{bind.MISMO}}}{named.name_dp}")
        if label is None:
            label = edit.insert_ordered(node, named.name_dp)
        label.text = name
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "grid row named")
    st.log(case_id, _actor(request), "edited",
           f"added row {was!r} -> {name!r}" if was else f"added row {name!r}")
    return {"name": name, "removed": not name, "state": st.get(case_id).state}


def _line_row(kind: str, container: str) -> tuple[str, str, str]:
    """The workbook's own template for the rows kept in this container."""
    for row in comparables.rows(kind):
        fid = row.subject_fid or row.comp_fid
        named = comparables.named_row(kind, fid, row.data_point, row.adjust_type)
        if named is not None and named.container == container:
            return fid, row.data_point, row.adjust_type
    raise HTTPException(422, f"no added-row template for {container}")


@router.post("/cases/{case_id}/comparables")
def add_comparable(case_id: str, request: Request,
                   body: dict = Body(default={})) -> dict:
    """Add another comparable property to the case."""
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    kind = body.get("kind", "sales")
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    _sheet, role, _title = comparables.SHEETS[kind]
    problem = comparables.limit_problem(kind, len(_labels(tree, kind)) + 1)
    if problem:
        raise HTTPException(409, problem)
    added = comparables.add_property(tree, role)
    if kind == "rental":
        # compared with every subject unit until the appraiser says otherwise
        from uad import rentals
        rentals.pair_new_comparable(tree.getroot())
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "a comparable was added")
    st.log(case_id, _actor(request), "added a comparable", f"{role} #{added}")
    return {"added": added, "kind": kind}


@router.get("/cases/{case_id}/rentals/pairs")
def get_rental_pairs(case_id: str) -> dict:
    """Which rental comparable is compared with which subject unit (uad/rentals.py)."""
    _case_or_404(case_id)
    from uad import rentals
    return rentals.matrix(store().tree(case_id).getroot())


@router.put("/cases/{case_id}/rentals/pairs")
def put_rental_pair(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Compare rental comparable #comparable with subject unit #unit, or stop."""
    _case_or_404(case_id)
    from uad import rentals
    st = store()
    tree = deepcopy(st.tree(case_id))
    try:
        rentals.set_pair(tree.getroot(), int(body.get("comparable") or 0), int(body.get("unit") or 0),
                         bool(body.get("on")))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, str(exc))
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "rental pairing changed")
    st.log(case_id, _actor(request), "rental pairing",
           f"comparable #{body.get('comparable')} {'with' if body.get('on') else 'not with'} unit {body.get('unit')}")
    return rentals.matrix(tree.getroot())


@router.delete("/cases/{case_id}/comparables/{number}")
def remove_comparable(case_id: str, number: int, request: Request,
                      kind: str = Query("sales")) -> dict:
    """Delete a comparable; the ones after it move up a place."""
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    _sheet, role, _title = comparables.SHEETS[kind]
    count = len(_labels(tree, kind))
    problem = comparables.limit_problem(kind, count - 1) if 1 <= number <= count else ""
    if problem:
        raise HTTPException(409, problem)
    st.backfill_comparable_keys(case_id, _labels(tree, kind))
    try:
        comparables.remove_property(tree, role, number)
    except IndexError as exc:
        raise HTTPException(404, str(exc))
    # The property is gone, so its photographs are too, and the ones after it
    # take their number from where they now sit.
    if kind == "sales":
        # comparable photographs are the sales grid's (media carry a column
        # number, not a grid): removing a rental, GRM or "not used" entry
        # must never take a sale's photo with it
        st.drop_comparable_media(case_id, number)
        st.renumber_comparable_media(case_id, _labels(tree, kind))
    left = len(_labels(tree, kind))
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "a comparable was removed")
    st.log(case_id, _actor(request), "removed a comparable", f"{role} #{number}")
    return {"removed": number, "remaining": left, "kind": kind}


@router.post("/cases/{case_id}/comparables/{number}/copy")
def copy_comparable(case_id: str, number: int, request: Request,
                    kind: str = Query("sales")) -> dict:
    """Copy a comparable to a new last one (WinTOTAL's "Copy Comp"): every
    value and data source, freshly identified; not its photographs."""
    _case_or_404(case_id)
    st = store()
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    _sheet, role, _title = comparables.SHEETS[kind]
    tree = deepcopy(st.tree(case_id))
    problem = comparables.limit_problem(kind, len(_labels(tree, kind)) + 1)
    if problem:
        raise HTTPException(409, problem)
    try:
        added = comparables.copy_property(tree, role, number)
    except IndexError as exc:
        raise HTTPException(404, str(exc))
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "a comparable was copied")
    st.log(case_id, _actor(request), "copied a comparable", f"{role} #{number} -> #{added}")
    return {"added": added, "from": number, "kind": kind}


@router.get("/cases/{case_id}/smartadjust")
def smartadjust_suggest(case_id: str, profile: str = Query(""), rates: str = Query("")) -> dict:
    """Adjustments suggested from the owner's rate profile (uad/smartadjust.py),
    each beside the adjustment the grid holds now.  ``rates`` (JSON) overrides
    single rates for this report.  Nothing is written."""
    _case_or_404(case_id)
    from uad import smartadjust
    try:
        override = json.loads(rates) if rates else {}
    except ValueError:
        raise HTTPException(422, "rates must be JSON")
    tree = store().tree(case_id)
    p = smartadjust.profile_for(tree, profile, override if isinstance(override, dict) else {})
    cols = smartadjust.suggest(tree, p)
    prices = {}
    for c in comparables.build(tree, "sales", per_block=99)[:1]:
        for r in c.rows:
            if r.label.strip() in ("Sale Price", "List Price"):
                for i, cell in enumerate(r.cells, start=1):
                    v = re.sub(r"[^0-9.]", "", cell.text or "")
                    if v and (r.label.strip() == "Sale Price" or i not in prices):
                        prices[i] = float(v)
    return {"profile": p.to_json(), "profiles": list(smartadjust.PROFILES),
            "rate_keys": smartadjust.RATE_KEYS,
            "comparables": [{**c.to_json(), "price": prices.get(c.number)} for c in cols]}


@router.post("/cases/{case_id}/smartadjust")
def smartadjust_apply(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Write the suggestions the appraiser accepted:
    {"picks": [{"comparable": n, "adjust_type": t, "amount": a}]}."""
    _case_or_404(case_id)
    st = store()
    tree = deepcopy(st.tree(case_id))
    root = tree.getroot()
    allowed = {r.adjust_type for r in comparables.rows("sales") if r.adjust_type and r.adjust_fid}
    written = []
    for pick in body.get("picks") or []:
        try:
            n, kind, amount = int(pick["comparable"]), str(pick["adjust_type"]), int(round(float(pick["amount"])))
        except (KeyError, TypeError, ValueError):
            raise HTTPException(422, f"not a suggestion: {pick!r}")
        if kind not in allowed:
            raise HTTPException(422, f"{kind} is not an adjustment row of the sales grid")
        props = comparables.properties(root, comparables.SHEETS["sales"][1])
        if not 1 <= n <= len(props):
            # 422, not 404: the editor reads a 404 on a case as "the report is gone"
            raise HTTPException(422, f"no comparable #{n}")
        comparables.write_adjustment(props[n - 1], kind, str(amount))
        written.append(f"#{n} {kind} {amount}")
    if written:
        st.save_tree(case_id, tree)
        st.invalidate(case_id, _actor(request), "suggested adjustments accepted")
        st.log(case_id, _actor(request), "accepted suggested adjustments", "; ".join(written))
    return {"written": len(written)}


@router.post("/cases/{case_id}/comparables/order")
def order_comparables(case_id: str, request: Request,
                      body: dict = Body(...)) -> dict:
    """Reorder the comparables; every section that numbers them follows."""
    _case_or_404(case_id)
    st = store()
    kind = body.get("kind", "sales")
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    _sheet, role, _title = comparables.SHEETS[kind]
    tree = st.tree(case_id)
    st.backfill_comparable_keys(case_id, _labels(tree, kind))
    moved = comparables.reorder(tree, role, [int(n) for n in body.get("order", [])])
    st.renumber_comparable_media(case_id, _labels(tree, kind))
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "the comparables were reordered")
    st.log(case_id, _actor(request), "reordered comparables", str(body.get("order")))
    # The comparables' former numbers, in the order they now appear.
    return {"order": [old for old, _new in sorted(moved.items(),
                                                  key=lambda kv: kv[1])],
            "kind": kind}


# ---------------------------------------------------------------------- media
@router.get("/cases/{case_id}/media")
def list_media(case_id: str, category: str = Query("")) -> dict:
    _case_or_404(case_id)
    return {"categories": list(MEDIA_CATEGORIES),
            "media": [m.to_json() for m in store().media(case_id, category)]}


# ---------------------------------------------------------------- auto-fill
# A case arrives as an order sheet, an MLS export and a folder of photographs.
# The appraiser watches it being entered rather than being handed a filled
# report: the server writes the whole document in one pass while the page
# replays the same steps, section by section, control by control.
AUTOFILL: dict[str, dict] = {}


@router.post("/cases/{case_id}/autofill/source")
async def autofill_source(case_id: str, request: Request,
                          files: list[UploadFile] = File(...)) -> dict:
    """Stage an uploaded UAD 3.6 file as the source "Fill the report" reads.

    The filler already knows how to walk a document and act every value out on
    screen; what it lacked was a way to be handed one.  So the upload goes
    through the same import the rest of the application uses -- normalised,
    pictures decoded and written out, whether they arrive in a portable file's
    EXTENSION nodes, in a delivery zip or as loose files -- and lands in a
    case the filler then reads exactly as it reads a template.  Nothing about
    the filling itself changes.

    The staged case is hidden from the case list and removed when the run
    ends (``DELETE .../autofill/source``).
    """
    _case_or_404(case_id)
    from uad import importer, uadmap

    sent = [(f.filename or "file", await f.read()) for f in files]
    report = importer.Report()
    try:
        xml_name, xml_bytes, assets = importer.open_bundle(sent)
        tree = importer.parse(xml_bytes)
        report.xml_name = xml_name
        carried, _state = importer.take_embedded(tree, report)
        for low, item in carried.items():
            assets.setdefault(low, item)
        importer.normalise(tree, report)
        importer.repair_enumerations(tree, report)
        pictures = importer.pictures(tree, assets, report)
        importer.count(tree, report)          # so the page can say what arrived
    except importer.ImportError_ as exc:
        raise HTTPException(422, str(exc))

    st = store()
    stage = st.create(template=st.get(case_id).template,
                      name=f"{STAGING_PREFIX}{xml_name}", blank=True,
                      actor=_actor(request))
    try:
        st.save_tree(stage.case_id, tree, allow_invalid=True)
        folder = st.media_dir(stage.case_id)
        for pic in pictures:
            (folder / pic.name).write_bytes(pic.data)
            category = ("comparable" if (pic.comparable and pic.owner
                                         and pic.owner != "SubjectProperty"
                                         and pic.category in ("PropertyPhoto", ""))
                        else "subject" if (pic.category in ("DwellingFront", "PropertyPhoto")
                                           and pic.owner == "SubjectProperty")
                        else IMPORT_CATEGORY.get(pic.category, "other"))
            st.add_media(stage.case_id, category=category, filename=pic.name,
                         caption=pic.caption,
                         comparable=pic.comparable if category == "comparable" else 0,
                         section=uadmap.image_section(pic.category),
                         size=len(pic.data),
                         content_type=importer.IMAGE_TYPES.get(
                             Path(pic.name).suffix.lower(), "image/jpeg"))
    except Exception as exc:                                   # noqa: BLE001
        st.delete(stage.case_id)
        raise HTTPException(500, f"The file could not be staged: {exc}")
    return {"source": stage.case_id, "name": xml_name,
            "pictures": len(pictures), "values": report.values,
            "missing_pictures": len(report.pictures_missing)}


@router.delete("/cases/{case_id}/autofill/source")
def drop_autofill_source(case_id: str, source: str = Query(...)) -> dict:
    """Remove a staged source once the run has finished with it."""
    _case_or_404(case_id)
    st = store()
    try:
        staged = st.get(source)
    except Exception:
        return {"dropped": False}
    if not (staged.name or "").startswith(STAGING_PREFIX):
        raise HTTPException(400, "that case is not a staged fill source")
    st.delete(source)
    return {"dropped": True}


@router.post("/cases/{case_id}/autofill")
def start_autofill(case_id: str, request: Request, body: dict = Body(default={})) -> dict:
    """Plan the steps that fill this case, and begin writing them."""
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    source = str(body.get("source") or "")
    if not source:
        raise HTTPException(422, "Name the case or template the values come from.")
    src_folder, src_media = None, []
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
    source_name = source
    try:
        staged = st.get(source)
        if (staged.name or "").startswith(STAGING_PREFIX):
            source_name = staged.name[len(STAGING_PREFIX):]
    except Exception:                                   # noqa: BLE001
        pass
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

    # Which of the document's own image boxes each photograph fills.  Without
    # this the report draws both: the IMAGE the document carries (the values
    # for it are written like any other) and, beside it, the photograph that
    # *is* that image -- so every exhibit came out twice.  The import has
    # always recorded this; the filler did not.
    filled_boxes: dict[str, str] = {}

    def add_media(row: dict) -> None:
        origin = Path(row.get("path") or "")
        if not origin.exists():
            raise FileNotFoundError(row.get("filename", ""))
        target = st.media_dir(case_id) / origin.name
        if not target.exists():
            shutil.copy2(origin, target)
        item = st.add_media(case_id, category=row.get("category") or "other",
                            filename=origin.name, caption=row.get("caption") or "",
                            order=int(row.get("order") or 0),
                            comparable=int(row.get("comparable") or 0),
                            section=int(row.get("section") or 0),
                            size=target.stat().st_size,
                            content_type=row.get("content_type") or "image/jpeg",
                            provenance=row.get("provenance") or "template")
        filled_boxes[delivery.location_of(origin.name)] = item.media_id

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
                source=src_root, add_media=add_media)
            result["written"] += sum(1 for s in steps if s.kind == autofill.COMP)
            st.save_tree(case_id, working, allow_invalid=True)
            # A fill answers the same fields an import would, so it is
            # recorded the same way: the appraiser can then turn the green
            # marking on and see exactly what the file put in.
            import time as _time

            from uad import provenance
            brought = provenance.imported_fields(st.tree(case_id).getroot())
            prior = get_prefs(case_id)
            was = prior.get("imported") or {}
            update = {"imported": {**was, "from": source_name,
                                   "at": _time.time(), "fields": brought}}
            if filled_boxes:
                update["fills"] = {**(prior.get("fills") or {}), **filled_boxes}
            set_prefs(case_id, update)
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


@router.post("/cases/{case_id}/media")
async def add_media(case_id: str, request: Request,
                    file: UploadFile = File(...),
                    category: str = Query("other"),
                    caption: str = Query(""),
                    comparable: int = Query(0),
                    section: int = Query(0)) -> dict:
    _case_or_404(case_id)
    if category not in MEDIA_CATEGORIES:
        raise HTTPException(400, f"category must be one of {MEDIA_CATEGORIES}")
    st = store()
    data = await file.read()
    name = Path(file.filename or "image.jpg").name
    target = st.media_dir(case_id) / name
    stem, suffix, n = target.stem, target.suffix, 1
    while target.exists():
        target = target.with_name(f"{stem}-{n}{suffix}")
        n += 1
    target.write_bytes(data)
    # The front of the dwelling and a comparable's thumbnail are single
    # slots: a new photo takes the place of the old one rather than queueing
    # behind it where the report would never show it.
    for old in st.media(case_id, category):
        if (category == "subject") or (category == "comparable" and comparable
                                       and int(old.comparable or 0) == comparable):
            st.remove_media(case_id, old.media_id)
    existing = [m for m in st.media(case_id, category)]
    # A photograph belongs to a property, not to a position in the grid, so the
    # property's own identifier is recorded beside the number.
    comp_key = ""
    if comparable:
        marks = _labels(st.tree(case_id))
        if 1 <= comparable <= len(marks):
            comp_key = marks[comparable - 1]
    item = st.add_media(case_id, category=category, filename=target.name,
                        caption=caption, order=len(existing) + 1,
                        comparable=comparable, comp_key=comp_key,
                        section=section, size=len(data),
                        content_type=file.content_type or
                        mimetypes.guess_type(target.name)[0] or "image/jpeg")
    st.log(case_id, _actor(request), "added media", f"{category}: {target.name}")
    st.invalidate(case_id, _actor(request), "media added")
    return item.to_json()


@router.patch("/cases/{case_id}/media/{media_id}")
def update_media(case_id: str, media_id: str, request: Request,
                 body: dict = Body(...)) -> dict:
    """Rename an exhibit -- its caption is the name printed above it."""
    _case_or_404(case_id)
    st = store()
    if not any(m.media_id == media_id for m in st.media(case_id)):
        raise HTTPException(404, f"no media {media_id}")
    caption = str(body.get("caption", "")).strip()
    st.set_media_caption(case_id, media_id, caption)
    st.log(case_id, _actor(request), "renamed media", f"{media_id}: {caption}")
    st.invalidate(case_id, _actor(request), "media renamed")
    return next(m.to_json() for m in st.media(case_id) if m.media_id == media_id)


@router.delete("/cases/{case_id}/media/{media_id}")
def remove_media(case_id: str, media_id: str, request: Request) -> dict:
    _case_or_404(case_id)
    store().remove_media(case_id, media_id)
    # a photo that filled one of the document's own exhibit boxes leaves the
    # box empty again, rather than pointing at a file that is gone
    prefs = get_prefs(case_id)
    fills = {k: v for k, v in (prefs.get("fills") or {}).items() if v != media_id}
    if fills != (prefs.get("fills") or {}):
        set_prefs(case_id, {"fills": fills})
    store().invalidate(case_id, _actor(request), "media removed")
    return {"deleted": media_id}


@router.get("/cases/{case_id}/media/{media_id}/file")
def media_file(case_id: str, media_id: str) -> Response:
    _case_or_404(case_id)
    for m in store().media(case_id):
        if m.media_id == media_id:
            path = store().media_dir(case_id) / m.filename
            if not path.exists():
                raise HTTPException(404, "the file is missing from the case folder")
            return Response(path.read_bytes(),
                            media_type=m.content_type or "image/jpeg")
    raise HTTPException(404, media_id)


# -------------------------------------------------------------------- preview
@router.get("/cases/{case_id}/preview", response_class=HTMLResponse)
def preview(case_id: str, request: Request, screen: bool = Query(True)) -> HTMLResponse:
    """The report, drawn by the engine that prints the PDF (Appendix C-1 form)."""
    from uad.report import browser
    if not (screen and not browser.server_layout()):
        _case_or_404(case_id)
    if screen:
        return _rendered(case_id, "preview", request)
    st = store()
    html = flow.build(st.tree(case_id), folder=st.folder(case_id),
                      media=_media_for_render(case_id), screen=False)
    return HTMLResponse(html)


@router.get("/geocode/suggest")
def address_suggestions(q: str = Query("")) -> dict:
    """Candidate real addresses for what has been typed (see ``maps.suggest``)."""
    return {"suggestions": maps.suggest(q)}


@router.get("/fields/{field_id}/options")
def field_options(field_id: str, dp: str = Query("")) -> dict:
    """What a field may be set to -- for one of its data points when a table
    row names it (``dp``), since a field can bind several.

    Fetched when a list is opened rather than written into the page: there are
    a hundred and thirty of them on a report and most are never opened.
    """
    from uad.report import form as report_form

    choices = report_form.choices_for(field_id)
    if dp:
        b = report_form.binding(field_id)
        point = next((d for d in (b.data_points if b else []) if d.get("mismo") == dp
                      and not d.get("attribute")), None)
        if point is not None:
            choices = report_form.point_choices(point)
    # An "Other" with a description data point beside it (A-1: CR, IF
    # XType = "Other") asks for the description when it is picked.
    b = report_form.binding(field_id)
    others = {}
    for d in (b.data_points if b else []):
        for key, want in (d.get("requires") or {}).items():
            if want == "Other" and d.get("mismo", "").endswith("OtherDescription") and not d.get("attribute"):
                others[key] = {"data_point": d["mismo"],
                               "max": int(d["format_details"]) if str(d.get("format_details", "")).isdigit() else 0}
    enum_name = dp or next((d.get("mismo") for d in (b.data_points if b else [])
                            if d.get("enumerations") and not d.get("attribute")), "")
    out = []
    for value, label in choices:
        item = {"value": value, "label": label}
        if value == "Other" and enum_name in others:
            item["other"] = others[enum_name]
        out.append(item)
    return {"field_id": field_id, "options": out}


# ------------------------------------------------------------ market charts
MARKET_SECTION = 17


@router.get("/market/prompt")
def market_prompt() -> dict:
    """What to hand an assistant, with the order and the MLS exports, to get
    the import file back."""
    return {"prompt": market.PROMPT, "example": market.example(),
            "charts": {key: caption for key, caption in market.CHARTS.values()}}


@router.post("/cases/{case_id}/market/charts")
async def import_market_charts(case_id: str, request: Request) -> dict:
    """Draw the Market section's graphs from imported figures.

    The five charts are the same numbers the appraisal already argues from, so
    they are drawn rather than pasted: one file in, five exhibits out, in the
    report's own face and at its own measure.
    """
    _case_or_404(case_id)
    st = store()
    body = await request.body()
    try:
        series = market.parse(body.decode("utf-8"))
    except market.MarketDataError as exc:
        raise HTTPException(422, str(exc))
    except UnicodeDecodeError:
        raise HTTPException(422, "the file is not text")

    # Drawing them again replaces the last set rather than stacking a second.
    drawn = {c.title for c in series}
    for item in st.media(case_id):
        if item.section == MARKET_SECTION and item.caption in drawn:
            st.remove_media(case_id, item.media_id)

    tree = st.tree(case_id)
    folder = st.media_dir(case_id)
    made = []
    for chart in series:
        name = f"market-{chart.key.replace('_', '-')}.svg"
        (folder / name).write_text(market.svg(chart), encoding="utf-8")
        category = market.category_of(chart)
        # A case started from a sample already carries the GSEs' own picture
        # of this chart.  Point that IMAGE at the drawing instead of adding a
        # second one, or the report shows both.
        replaced = market.point_image_at(tree, category, name)
        if not replaced:
            st.add_media(case_id, category="other", filename=name,
                         caption=chart.title, section=MARKET_SECTION,
                         size=(folder / name).stat().st_size,
                         content_type="image/svg+xml")
        made.append({"chart": chart.key, "title": chart.title,
                     "category": category, "periods": len(chart.periods),
                     "series": len(chart.plots), "replaced": replaced})
    st.save_tree(case_id, tree)
    st.log(case_id, _actor(request), "imported market charts",
           ", ".join(m["title"] for m in made))
    st.invalidate(case_id, _actor(request), "the market charts changed")
    return {"drawn": made}


@router.get("/cases/{case_id}/form", response_class=HTMLResponse)
def editable_form(case_id: str, request: Request) -> HTMLResponse:
    """The report itself, with every value typed into where it stands.

    Not a form that resembles the report: the same renderer, the same C-1
    geometry, the same fonts and rules, with each printed value carrying the
    Report Field ID behind it so it can be edited in place.  What an appraiser
    fills in and what the lender receives are then the same page.

    Served from the background renderer (``app/renders.py``) so opening it
    does not wait on a layout pass.
    """
    from uad.report import browser
    if browser.server_layout():
        _case_or_404(case_id)
    return _rendered(case_id, "form", request)


@router.get("/cases/{case_id}/render/{kind}")
def render_status(case_id: str, kind: str) -> dict:
    """Whether the current render of the form or preview is ready."""
    _case_or_404(case_id)
    if kind not in renders.KINDS:
        raise HTTPException(404, f"no render kind {kind}")
    from uad.report import browser
    if not browser.server_layout():
        # the appraiser's browser lays the report out (no Chromium on this
        # host): a newer key means "reload and lay out again", never "wait for
        # the server" -- waiting here was the endless "Updating the report"
        return {"ready": True, "key": renderer().key(case_id, kind), "stale": False}
    have, want = renderer().get(case_id, kind)
    if (have is None or have.key != want) and layouts().get(want, kind) is not None:
        return {"ready": True, "key": want, "stale": False}
    return {"ready": have is not None and have.key == want, "key": want,
            "stale": have is not None and have.key != want}


@router.get("/cases/{case_id}/layout/{kind}/galley", response_class=HTMLResponse)
def layout_galley(case_id: str, kind: str) -> HTMLResponse:
    """The report as one long column, for the browser to measure (client layout)."""
    _case_or_404(case_id)
    if kind not in renders.KINDS:
        raise HTTPException(404, f"no render kind {kind}")
    # the key first: if the case changes while the galley is built, the page
    # carries the older key and the editor asks for one more layout
    key = renderer().key(case_id, kind)
    return HTMLResponse(renderer().client_galley(case_id, kind),
                        headers={"Cache-Control": "no-store", "X-Render-Key": key})


@router.post("/cases/{case_id}/layout/{kind}/keep")
def layout_keep(case_id: str, kind: str, body: dict = Body(...)) -> dict:
    """The browser's final pass fitted every page: share that layout by key.

    The page is rebuilt here from the same measurements and caps (the server's
    own HTML, never the browser's), and kept only while the case still has the
    key it was laid out for."""
    _case_or_404(case_id)
    if kind not in renders.KINDS:
        raise HTTPException(404, f"no render kind {kind}")
    key = str(body.get("key") or "")
    measured = body.get("measured")
    if key != renderer().key(case_id, kind) or not isinstance(measured, list) or not measured:
        return {"kept": False}
    try:
        caps = {int(k): float(v) for k, v in (body.get("caps") or {}).items()}
        # only the browser's numbers are used: the markup of every block is
        # the server's own galley for this key (flow.trusted), so a shared
        # layout never holds anything a browser sent
        galley = renderer().client_galley(case_id, kind)
        measured = flow.trusted(measured, galley)
        html, _planned = renderer().client_pages(case_id, kind, measured, caps)
    except (KeyError, TypeError, ValueError):
        return {"kept": False}
    if key != renderer().key(case_id, kind):
        return {"kept": False}               # the case changed meanwhile
    from app.layouts import neutral
    layouts().put(key, kind, neutral(html, case_id))
    return {"kept": True}


@router.post("/cases/{case_id}/layout/{kind}/pages")
def layout_pages(case_id: str, kind: str, body: dict = Body(...)) -> dict:
    """Pages planned from the browser's measurements of the galley.

    ``measured`` is what flow.MEASURE_JS returned in the browser; ``caps``
    the per-page limits from earlier passes.  The pages go back to the browser
    that asked and are not kept: what a browser sends is never stored or
    served to anyone else."""
    _case_or_404(case_id)
    if kind not in renders.KINDS:
        raise HTTPException(404, f"no render kind {kind}")
    measured = body.get("measured")
    if not isinstance(measured, list) or not measured:
        raise HTTPException(400, "measured blocks are required")
    try:
        caps = {int(k): float(v) for k, v in (body.get("caps") or {}).items()}
        html, planned = renderer().client_pages(case_id, kind, measured, caps)
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(400, f"the measurements could not be planned: {exc}")
    key = str(body.get("key") or "")
    key = key if re.fullmatch(r"[0-9a-f]{16}", key) else "client"
    info = json.dumps({"case": case_id, "kind": kind, "key": key, "stale": False})
    html = html.replace("</head>", f"<script>window.UAD_RENDER={info};</script>" + FRESH_JS
                        + "</head>", 1)
    return {"html": html, "planned": planned, "bodyBottom": flow.BODY_BOTTOM,
            "attempts": flow.ATTEMPTS}


def _client_layout_page(case_id: str, kind: str) -> str:
    return (CLIENT_LAYOUT_HTML.replace("{{case}}", case_id).replace("{{kind}}", kind)
            .replace("{{measure}}", flow.MEASURE_JS).replace("{{overflow}}", flow.OVERFLOW_JS))


# The page the editor's frame loads when this server cannot lay the report out
# itself.  It measures the galley in a hidden frame with the same script the
# server's Chromium runs (flow.MEASURE_JS, injected below -- one source), asks
# for pages, checks them against the body rule (flow.OVERFLOW_JS), and asks
# again with tighter caps if a page ran long, exactly as flow.build does.
CLIENT_LAYOUT_HTML = """<!doctype html><html><head><meta charset='utf-8'>
<title>Laying out the report</title><style>
html,body{margin:0;height:100%;background:transparent;font:13px/1.4 "Geist","Segoe UI",system-ui,sans-serif}
.msg{position:fixed;left:50%;top:18px;transform:translateX(-50%);background:rgba(17,17,19,.9);color:#f4f4f5;
  border:1px solid rgba(255,255,255,.12);padding:9px 16px;border-radius:999px;display:flex;gap:10px;align-items:center;z-index:2}
.spin{width:12px;height:12px;border:1.5px solid rgba(255,255,255,.25);border-top-color:#f4f4f5;border-radius:50%;
  animation:sp .8s linear infinite}@keyframes sp{to{transform:rotate(360deg)}}
.err{background:#3a1416;border-color:rgba(242,120,126,.45)}
iframe.m{position:absolute;left:-10000px;top:0;width:900px;height:1400px;border:0;visibility:hidden}
</style></head><body>
<div class='msg' id='msg'><span class='spin'></span><span id='say'>Laying out the report in this browser...</span></div>
<script>
function stage(T){ document.documentElement.style.background=document.body.style.background=(T==='light'?'#e4e4e6':'#19191c'); }
try{ stage(window.parent!==window&&window.parent.document.documentElement.dataset.theme); }catch(e){}
window.addEventListener('message',function(e){ if(e.data&&e.data.uad==='theme') stage(e.data.theme); });
try{ if(window.parent!==window&&window.parent.UADVault) window.parent.UADVault.install(window); }catch(e){}
(function(){
  var CASE='{{case}}', KIND='{{kind}}';
  var MEASURE={{measure}};
  var OVERFLOW={{overflow}};
  function say(t,bad){document.getElementById('say').textContent=t;
    if(bad){document.getElementById('msg').className='msg err';}}
  function frame(html){
    return new Promise(function(res,rej){
      var f=document.createElement('iframe'); f.className='m';
      f.onload=function(){
        var d=f.contentDocument;
        (d.fonts?d.fonts.ready:Promise.resolve()).then(function(){
          var imgs=Array.prototype.slice.call(d.images);
          return Promise.all(imgs.map(function(i){return i.complete?0:new Promise(function(r){i.onload=i.onerror=r;});}));
        }).then(function(){setTimeout(function(){res(f);},120);}).catch(rej);
      };
      document.body.appendChild(f);
      f.srcdoc=html;
    });
  }
  function run(fn,f){return fn.call(f.contentWindow);}  // the scripts read document via `document`
  function inFrame(src,f){return f.contentWindow.eval('('+src+')()');}
  function post(body){
    return fetch('/api/cases/'+CASE+'/layout/'+KIND+'/pages',{method:'POST',
      headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
      .then(function(r){if(!r.ok) return r.text().then(function(t){throw new Error(t);}); return r.json();});
  }
  var measured, caps={}, attempt=0, last=null, KEY='client';
  /* The last layout this browser made of this report is kept (IndexedDB), so
     opening or reloading the report shows it at once.  When the case has
     changed since, the kept one is shown all the same and the editor lays the
     current one out behind it and swaps it in -- a frame made for that swap
     (?t=...) always lays out afresh. */
  var SWAP=/[?&]t=/.test(location.search), SLOT=CASE+'/'+KIND;
  function idb(){
    return new Promise(function(res){
      try{ var r=indexedDB.open('uad36-layout',1);
        r.onupgradeneeded=function(){ r.result.createObjectStore('pages'); };
        r.onsuccess=function(){ res(r.result); }; r.onerror=function(){ res(null); };
      }catch(e){ res(null); }
    });
  }
  function kept(){
    return idb().then(function(db){ return db&&new Promise(function(res){
      try{ var q=db.transaction('pages').objectStore('pages').get(SLOT);
        q.onsuccess=function(){ res(q.result||null); }; q.onerror=function(){ res(null); };
      }catch(e){ res(null); } }); });
  }
  function keep(rec){
    idb().then(function(db){ if(!db) return;
      try{ db.transaction('pages','readwrite').objectStore('pages').put(rec,SLOT); }catch(e){} });
  }
  function layout(){
    fetch('/api/cases/'+CASE+'/layout/'+KIND+'/galley').then(function(r){
      if(!r.ok) throw new Error('the report could not be prepared ('+r.status+')');
      KEY=r.headers.get('X-Render-Key')||'client'; return r.text();
    }).then(frame).then(function(f){
      say('Measuring every block against Appendix C-1...');
      measured=inFrame(String(MEASURE),f); f.remove();
      return pass();
    }).catch(function(e){ say('The report could not be laid out: '+e.message, true); });
  }
  Promise.all([SWAP?null:kept(),
               SWAP?null:fetch('/api/cases/'+CASE+'/render/'+KIND).then(function(r){
                 return r.ok?r.json():null; }).catch(function(){ return null; })])
    .then(function(got){
      var rec=got[0], now=got[1]&&got[1].key;
      if(rec&&rec.html&&rec.key){
        KEY=rec.key; show(rec.html, now&&rec.key!==now);
        return;
      }
      layout();
    }, layout);

  function pass(){
    attempt++;
    say('Paginating (pass '+attempt+')...');
    return post({measured:measured,caps:caps,key:KEY}).then(function(res){
      last=res;
      return frame(res.html).then(function(f){
        var bottoms=inFrame(String(OVERFLOW),f); f.remove();
        var over={}, any=false;
        bottoms.forEach(function(b,i){ if(b>res.bodyBottom){ over[i+1]=b; any=true; } });
        if(any && attempt<res.attempts){
          // flow.tighten: shrink from the cap in force, by the overrun and 1pt
          Object.keys(over).forEach(function(n){
            caps[n]=(caps[n]!==undefined?caps[n]:res.bodyBottom)-(over[n]-res.bodyBottom)-1.0; });
          return pass();
        }
        if(KEY!=='client') keep({key:KEY,html:res.html,at:Date.now()});
        if(KEY!=='client'&&!any){
          // every page fits: the server keeps this layout for every report with
          // the same content, so the next one opens without a layout pass
          fetch('/api/cases/'+CASE+'/layout/'+KIND+'/keep',{method:'POST',
            headers:{'Content-Type':'application/json'},
            body:JSON.stringify({measured:measured,caps:caps,key:KEY})}).catch(function(){});
        }
        show(res.html, false);
      });
    });
  }
  function show(html, stale){
    document.open(); document.write(html); document.close();
    // the editor waits for this, as it does for a server-rendered page; a kept
    // layout older than the case asks for the current one straight after
    setTimeout(function(){ try{ if(window.parent!==window){
      window.parent.postMessage({uad:'frame-ready',kind:KIND,key:KEY,stale:!!stale},'*');
      if(stale) window.parent.postMessage({uad:'relayout'},'*'); } }catch(e){} }, 50);
  }
})();
</script></body></html>"""


@router.get("/fontasset/{name}")
def font_asset(name: str) -> Response:
    """A report typeface, named by its digest.  Fonts come from the code alone,
    never from a case, so any server copy can produce the file another copy
    referenced (renders.FONT_ASSETS)."""
    import re as _re
    if not _re.fullmatch(r"[0-9a-f]{20}\.(ttf|otf|woff2?)", name):
        raise HTTPException(404, "no such font")
    path = renders.font_asset(name)
    if path is None:
        raise HTTPException(404, "no such font")
    return Response(path.read_bytes(), media_type="font/" + path.suffix[1:],
                    headers={"Cache-Control": "public, max-age=31536000, immutable"})


_ASSET_LOCKS: dict[str, "threading.Lock"] = {}


@router.get("/cases/{case_id}/asset/{name}")
def render_asset(case_id: str, name: str) -> Response:
    """A photograph or font a rendered page references, named by its digest --
    so it never changes and the browser may keep it."""
    import re as _re
    if not _re.fullmatch(r"[0-9a-f]{20}\.[a-z0-9]{2,5}", name):
        raise HTTPException(404, "no such asset")
    path = renderer().assets(case_id) / name
    if not path.is_file():
        _case_or_404(case_id)
        # Content-addressed: a page laid out for another report with the same
        # content (every new report opens on the shared layout of the blank
        # one) names files that report's render wrote.  Same name, same bytes.
        twin = next(iter(sorted(store().root.glob(f"*/_render/assets/{name}"))), None) \
            if hasattr(store(), "root") else None
        if twin is not None and twin.is_file():
            renders._write_once(path, twin.read_bytes())
    if not path.is_file():
        # Written by a render on another instance (serverless) or cleared:
        # laying the case out again writes the same files under the same
        # names.  A page asks for all its images at once; one request lays it
        # out, the rest wait and then find the file -- before this lock every
        # image rebuilt the whole report at the same moment (12 s on SF1).
        with _ASSET_LOCKS.setdefault(case_id, threading.Lock()):
            for kind in renders.KINDS:
                if path.is_file():
                    break
                try:
                    renderer().client_galley(case_id, kind)
                except Exception:
                    pass
    if not path.is_file():
        raise HTTPException(404, "no such asset")
    kind = {"ttf": "font/ttf", "otf": "font/otf", "svg": "image/svg+xml",
            "jpg": "image/jpeg", "tif": "image/tiff"}.get(path.suffix[1:]) or         mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return Response(path.read_bytes(), media_type=kind,
                    headers={"Cache-Control": "private, max-age=31536000, immutable"})


RENDERER = None
LAYOUTS = None
#: The document every new report starts from (one entry point; the report then
#: takes its shape from the appraiser's answers).
NEW_REPORT = "sf1_appraisal_v1_4"
#: what an unnamed new report is called until its address is entered
NEW_NAME = "New report"


def layouts():
    """Laid-out reports shared by content key (app/layouts.py)."""
    global LAYOUTS
    if LAYOUTS is None:
        from app.layouts import Layouts
        backend = DURABLE.backend if (DURABLE is not None and DURABLE.on) else None
        LAYOUTS = Layouts(backend, folder=None if backend else Path(store().root) / "_layouts")
    return LAYOUTS


def _shared_page(case_id: str, kind: str):
    """The current layout of this case if any report with the same content was
    laid out before -- one read instead of a layout pass."""
    try:
        key = renderer().key(case_id, kind)
        html = layouts().get(key, kind)
    except Exception:
        return None, ""
    if html is None:
        return None, key
    from app.layouts import for_case
    return for_case(html, case_id), key


def _warm_id(template: str) -> str:
    import hashlib
    return hashlib.sha1(f"warm:{template}".encode()).hexdigest()[:12]


@router.post("/warm")
def warm(body: dict = Body(default={})) -> dict:
    """Make sure a new report will open at once.

    A new report is the same document every time, so its layout is the same
    every time; the editor asks for this while the list of reports is on
    screen, and lays the hidden warm-up report out in the background if no
    server copy has its layout yet (app/layouts.py)."""
    from app.cases import WARM
    template = body.get("template") or NEW_REPORT
    case_id = _warm_id(template)
    st = store()
    try:
        st.get(case_id)
    except KeyError:
        try:
            st.create(template=template, name=f"{WARM}{template}", blank=True,
                      actor="server", case_id=case_id)
        except KeyError:
            raise HTTPException(404, f"no template {template}")
        except Exception:                       # noqa: BLE001
            # two windows (or two server copies) warming at once: the other
            # one made it, which is all that was wanted
            st.get(case_id)
    ready = {}
    for kind in renders.KINDS:
        html, _key = _shared_page(case_id, kind)
        ready[kind] = html is not None
    return {"case_id": case_id, "ready": ready}


def renderer():
    global RENDERER
    if RENDERER is None:
        RENDERER = renders.Renderer(store, _media_for_render, get_prefs)

        def _share(case_id, kind, key, html):
            from app.layouts import neutral
            layouts().put(key, kind, neutral(html, case_id))
        RENDERER.on_rendered = _share
    return RENDERER


def _rendered(case_id: str, kind: str, request: Request) -> HTMLResponse:
    """The newest render there is, never an unexpected wait in a browser.

    A browser (it asks for text/html) gets the current render at once, an
    older one marked stale that replaces itself when the fresh one lands, or a
    loading page that waits for it.  Anything else -- a test, a script --
    waits for the current render, so it never reads a stale report.
    """
    from uad.report import browser
    shared, key = _shared_page(case_id, kind)
    if shared is not None:
        return _page(shared, case_id, kind, key, stale=False)
    if not browser.server_layout():
        # no Chromium here (a serverless host): the appraiser's own browser
        # measures the page and this server does the arithmetic
        return HTMLResponse(_client_layout_page(case_id, kind),
                            headers={"Cache-Control": "no-store"})
    r = renderer()
    browser = "text/html" in request.headers.get("accept", "")
    have, want = r.get(case_id, kind)
    if have is not None and have.key == want:
        return _page(have.html, case_id, kind, want, stale=False)
    if not browser:
        fresh = r.wait(case_id, kind)
        if fresh is None:
            raise HTTPException(503, "the report is still being laid out")
        return _page(fresh.html, case_id, kind, fresh.key, stale=False)
    if have is not None:
        return _page(have.html, case_id, kind, want, stale=True)
    return HTMLResponse(_loading_page(case_id, kind), headers={"Cache-Control": "no-store"})


def _page(html: str, case_id: str, kind: str, key: str, *, stale: bool) -> HTMLResponse:
    info = json.dumps({"case": case_id, "kind": kind, "key": key, "stale": stale})
    tag = f"<script>window.UAD_RENDER={info};</script>"
    return HTMLResponse(html.replace("</head>", tag + FRESH_JS + "</head>", 1),
                        headers={"Cache-Control": "no-store", "X-Render-Key": key,
                                 "X-Render-Stale": "1" if stale else "0"})


# A page served stale watches for its fresh render and tells the editor, which
# swaps it in behind the scenes; a page on its own reloads.
FRESH_JS = """<script>
(function(){ try{ if(window.parent!==window&&window.parent.UADVault) window.parent.UADVault.install(window); }catch(e){} })();
(function(){
  var R=window.UAD_RENDER||{}; var parentWin=(window.parent!==window)?window.parent:null;
  window.addEventListener('load',function(){
    if(parentWin) parentWin.postMessage({uad:'frame-ready',kind:R.kind,key:R.key,stale:!!R.stale},'*');
  });
  if(!R.stale) return;
  function poll(){
    fetch('/api/cases/'+R.case+'/render/'+R.kind).then(function(r){return r.json();})
      .then(function(s){
        if(s.ready){
          // never swap the page out from under an edit in progress
          if(document.querySelector('.gedit,.picklist,.mapframe')){
            setTimeout(poll,1500); return;
          }
          if(parentWin) parentWin.postMessage({uad:'fresh',kind:R.kind,key:s.key},'*');
          else location.reload();
          return;
        }
        setTimeout(poll,700);
      }).catch(function(){ setTimeout(poll,1500); });
  }
  setTimeout(poll,400);
})();
</script>"""


def _loading_page(case_id: str, kind: str) -> str:
    """Shown only while a report has never been laid out before."""
    what = "report" if kind == "form" else "preview"
    return (LOADING_HTML.replace("{{case}}", case_id).replace("{{kind}}", kind)
            .replace("{{what}}", what))


LOADING_HTML = """<!doctype html><html><head><meta charset='utf-8'>
<title>Preparing the report</title><style>
html,body{margin:0;height:100%;background:#6f6f6f;font:13px/1.4 'Segoe UI',system-ui,sans-serif}
.wrap{display:flex;flex-direction:column;align-items:center;padding:28px 12px}
.page{width:min(816px,96vw);aspect-ratio:612/1008;background:#fff;position:relative;overflow:hidden;
  box-shadow:0 2px 12px rgba(0,0,0,.25)}
.bar{position:absolute;left:6%;right:6%;height:10px;border-radius:2px;background:#e6e7e8;overflow:hidden}
.bar:after{content:'';position:absolute;inset:0;transform:translateX(-100%);
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.85),transparent);animation:sh 1.3s infinite}
.tab{position:absolute;left:6%;width:30%;height:16px;background:#231f20;border-radius:0 8px 0 0;opacity:.85}
@keyframes sh{100%{transform:translateX(100%)}}
.msg{position:fixed;left:50%;top:18px;transform:translateX(-50%);background:#101010;color:#f2f2f0;
  padding:9px 16px;border-radius:2px;display:flex;gap:10px;align-items:center;z-index:2;
  box-shadow:0 2px 10px rgba(0,0,0,.3);white-space:nowrap}
.spin{width:14px;height:14px;border:2px solid #6a6a66;border-top-color:#f2f2f0;border-radius:50%;
  animation:sp .8s linear infinite}
@keyframes sp{to{transform:rotate(360deg)}}
.prog{position:fixed;left:0;top:0;height:3px;background:#f2f2f0;width:0;transition:width .5s ease}
@media (prefers-reduced-motion:reduce){.bar:after,.spin{animation:none}}
</style></head><body>
<div class='prog' id='prog'></div>
<div class='msg'><span class='spin'></span><span id='say'>Preparing the {{what}}...</span></div>
<div class='wrap'><div class='page' id='page'></div></div>
<script>
(function(){
  var page=document.getElementById('page'), y=7;
  for(var i=0;i<34;i++){
    var el=document.createElement('div');
    if(i%9===0){ el.className='tab'; el.style.top=y+'%'; y+=3.2; }
    else { el.className='bar'; el.style.top=y+'%'; el.style.right=(6+((i*37)%30))+'%'; y+=2.6; }
    page.appendChild(el);
  }
  var steps=['Preparing the {{what}}...','Reading the case document...',
             'Measuring every line against Appendix C-1...','Placing photographs and exhibits...',
             'Checking nothing runs off the page...','Almost there...'];
  var n=0, t0=Date.now(), prog=document.getElementById('prog');
  setInterval(function(){ n=Math.min(n+1,steps.length-1); document.getElementById('say').textContent=steps[n]; },1600);
  setInterval(function(){ var s=(Date.now()-t0)/1000; prog.style.width=Math.min(92,100*(1-Math.exp(-s/4)))+'%'; },250);
  function poll(){
    fetch('/api/cases/{{case}}/render/{{kind}}').then(function(r){return r.json();}).then(function(s){
      if(s.ready){ prog.style.width='100%'; location.reload(); return; }
      setTimeout(poll,500);
    }).catch(function(){ setTimeout(poll,1500); });
  }
  poll();
})();
</script></body></html>"""


def _render_pdf(case_id: str):
    st = store()
    html = flow.build(st.tree(case_id), folder=st.folder(case_id),
                      media=_media_for_render(case_id), screen=False)
    out = st.folder(case_id) / "appraisal.pdf"
    flow.to_pdf(html, out)
    return out


@router.get("/cases/{case_id}/report.pdf")
def report_pdf(case_id: str) -> Response:
    _case_or_404(case_id)
    out = _render_pdf(case_id)
    return Response(out.read_bytes(), media_type="application/pdf",
                    headers={"Content-Disposition":
                             'inline; filename="appraisal.pdf"'})


# ------------------------------------------------------------------- sign-off
@router.post("/cases/{case_id}/state")
def set_state(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    _case_or_404(case_id)
    to = body.get("state", "")
    try:
        case = store().transition(case_id, to, _actor(request),
                                  force=bool(body.get("force")))
    except GateError as exc:
        return JSONResponse(
            {"error": str(exc), "reasons": exc.reasons}, status_code=409)
    return case.to_json()


@router.post("/cases/{case_id}/acknowledge")
def acknowledge(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    _case_or_404(case_id)
    case = store().acknowledge(case_id, int(body.get("section", 0)),
                               _actor(request), bool(body.get("on", True)))
    return case.to_json()


# --------------------------------------------------------------------- export
def _delivery(case_id: str) -> "delivery.Package":
    """The XML and images this case would ship, with every delivery fault."""
    st = store()
    templates_ = {m.filename for m in st.media(case_id) if m.provenance == "template"}
    return delivery.build(st.tree(case_id), st.media(case_id), st.media_dir(case_id),
                          fills=_fills(case_id), template_names=templates_)


# ------------------------------------------------------------------- maps
MAPPER = None


# the running server's own address and session, for its headless map tool
SERVER: dict | None = None


def mapper():
    global MAPPER
    if MAPPER is None:
        from . import mapper as _mapper
        MAPPER = _mapper.Mapper(store, get_prefs, set_prefs, lambda: SERVER)
    return MAPPER


@router.post("/cases/{case_id}/maps")
def generate_maps(case_id: str) -> dict:
    """Draw the Sales Comparison Map now, with the Location Map tool (Appendix
    E p66: the map sets full page)."""
    _case_or_404(case_id)
    return mapper().generate(case_id, force=True)


@router.post("/cases/{case_id}/maps/aerial")
def generate_aerial(case_id: str) -> dict:
    """The subject from above, as a Site exhibit at the exhibit picture's size."""
    _case_or_404(case_id)
    return mapper().aerial(case_id)


@router.post("/cases/{case_id}/maps/image")
async def save_map_image(case_id: str, file: UploadFile = File(...)) -> dict:
    """The Location Map tool's own export, saved as the Sales Comparison Map."""
    _case_or_404(case_id)
    data = await file.read()
    if not data.startswith(bytes([0x89]) + b"PNG"):
        raise HTTPException(422, "the map must be a PNG exported by the map tool")
    media_id = mapper().store_png(case_id, data)
    return {"media_id": media_id}


@router.get("/cases/{case_id}/maps")
def maps_status(case_id: str) -> dict:
    _case_or_404(case_id)
    return {**mapper().status(case_id),
            "auto": get_prefs(case_id).get("autoMaps") is not False}


@router.get("/cases/{case_id}/maps/places")
def map_places(case_id: str, kind: str = Query("sales")) -> dict:
    """The subject and its comparables, with the coordinates the case holds.

    A-1 requires LatitudeIdentifier and LongitudeIdentifier on every property,
    and an appraisal that arrives from other software carries them -- so the
    map had no business looking any of it up.  It was seeding itself from the
    printed addresses and geocoding each one: a request a second, against an
    address the report prints for a person to read rather than for a gazetteer
    to parse ("15 S Beechwood Rd Unit"), so the comparables came back
    unplaced and the subject, whose coordinates it did take, was the only pin
    on the map.

    Here the coordinates are simply handed over.  Geocoding stays as the
    fallback for a property the document has none for.
    """
    _case_or_404(case_id)
    root = store().tree(case_id).getroot()
    # The map's own words for what a property is: a closed sale, an active
    # listing or a rental.  It colours and labels the callout from this --
    # yellow for a sale, purple for a listing, green for a rental -- so the
    # value handed over has to be one the map knows, not the one A-1 uses.
    status = {"listing": "active", "sale": "closed"}
    if kind in ("rental", "grm"):
        status = dict.fromkeys(("listing", "sale"), "rent")
    out = []
    for place in maps.places(root, kind):
        out.append({"kind": "subject" if place.kind == "subject" else "comp",
                    "number": place.number,
                    "address": place.address,
                    "lines": list(place.lines),
                    "lat": place.lat, "lon": place.lon,
                    "status": status.get(place.kind, "closed")})
    return {"kind": kind, "places": out}


# ------------------------------------------------ data that does not print
@router.get("/cases/{case_id}/extra")
def extra_data(case_id: str) -> dict:
    """What A-1 requires that has no place on the report (``uad/extra.py``)."""
    _case_or_404(case_id)
    groups = extra.groups(store().tree(case_id).getroot())
    missing = sum(1 for g in groups for r in g["rows"] if r["conditionality"] == "R"
                  for a in r["answers"] if not a["value"])
    return {"groups": groups, "missing_required": missing}


@router.patch("/cases/{case_id}/extra/{uid}")
def set_extra_data(case_id: str, uid: str, request: Request, body: dict = Body(...)) -> dict:
    _case_or_404(case_id)
    try:
        row = extra.by_uid(uid)
    except KeyError:
        raise HTTPException(404, f"no data point {uid} to edit here")
    st = store()
    try:
        tree = extra.write(st.tree(case_id), row, str(body.get("value", "")),
                           scope=int(body.get("scope") or 0),
                           instance=int(body.get("instance") or 0))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), f"{row.name} changed")
    st.log(case_id, _actor(request), "edited", f"{row.name} ({uid}) -> {body.get('value')!r}")
    return {"answers": extra.read(tree.getroot(), row)}


def _export_verdict(case_id: str):
    """One answer to "can this case be exported?", for the check and the
    export alike -- they used to disagree: the check said ready (delivery
    rules and schema only) while the export refused for the sign-off gate
    (owner's section test B12).  Returns (built package, blockers)."""
    st = store()
    allowed, reasons = st.exportable(case_id)
    built = _delivery(case_id)
    blockers = [] if allowed else [str(r) for r in reasons]
    blockers += [f"{f.code}: {f.message} {f.detail}".strip() for f in built.fatal]
    problems = schema.validate(built.tree)
    blockers += [f"Schema: {e}" for e in problems[:20]]
    return built, problems, blockers, allowed


@router.get("/cases/{case_id}/package/check")
def package_check(case_id: str) -> dict:
    """What stands between this case and a deliverable ZIP (B-1 pp 69-73),
    including the sign-off gate: ``ready`` is true exactly when
    ``package.zip`` would answer with an archive."""
    _case_or_404(case_id)
    built, problems, blockers, signed = _export_verdict(case_id)
    return {"faults": [f.to_json() for f in built.faults],
            "schema": [str(e) for e in problems[:50]],
            "images": sorted(built.images),
            "signed_off": signed,
            "blockers": blockers,
            "ready": not blockers}


@router.get("/cases/{case_id}/package.zip")
def package(case_id: str) -> Response:
    """The deliverable: appraisal.pdf, mismo.xml and Images/, in one archive.

    The gate is asked first and there is no way past it, so an archive can only
    exist for a case an appraiser has signed.
    """
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    built, problems, blockers, _signed = _export_verdict(case_id)
    if blockers:
        return JSONResponse(
            {"error": "this case cannot be exported yet", "reasons": blockers},
            status_code=409)
    pdf_path = _render_pdf(case_id)

    # B-1 p69-73: one XML, one PDF, and the Images folder -- nothing else.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.write(pdf_path, delivery.PDF_NAME)
        zf.writestr(delivery.XML_NAME, etree.tostring(
            built.tree, xml_declaration=True, encoding="UTF-8", pretty_print=True))
        for name, path in sorted(built.images.items()):
            zf.writestr(f"{delivery.IMAGES}/{name}", path.read_bytes())

    size_faults = delivery.check_size(buffer.getbuffer().nbytes)
    if size_faults:
        return JSONResponse({"error": "the package is too large",
                             "reasons": [f"{f.code}: {f.message} {f.detail}" for f in size_faults]},
                            status_code=409)

    # The archive is inspected as an archive before anyone is handed it: what
    # it actually contains, against what this case actually references.
    buffer.seek(0)
    with zipfile.ZipFile(buffer) as zipped:
        names = zipped.namelist()
    html = flow.build(tree, folder=st.folder(case_id),
                      media=_media_for_render(case_id), screen=False)
    shipped = [m for m in st.media(case_id) if m.filename in built.images]
    faults = [f for f in integrity.check(tree, shipped, html=html, names=names)
              if f.severity == integrity.FATAL]
    if faults:
        return JSONResponse(
            {"error": "the package does not match the report",
             "reasons": [f"{f.code}: {f.message} {f.detail}".strip()
                         for f in faults]},
            status_code=409)

    buffer.seek(0)
    st.transition(case_id, EXPORTED, "system", force=True)
    st.log(case_id, "system", "exported", "package.zip built")
    name = f"{st.get(case_id).name.replace(' ', '_')}.zip"
    return StreamingResponse(
        buffer, media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{name}"'})
