"""Browser review application.

Serves the report as an editable page, holds the appraiser's edits, and builds
the deliverable ZIP from the edited state — so the archive always reflects what
was reviewed on screen, never the machine's first draft.
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path
from typing import Any

import uuid

from fastapi import FastAPI, Request
from fastapi.responses import (
    FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse,
)

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "engine"))

import pipeline  # noqa: E402
from uad import model  # noqa: E402
from uad.report import images as images_mod  # noqa: E402
from app.access import COOKIE, Access, gate_page, guard  # noqa: E402
from app.store import Store  # noqa: E402
from uad.report import builder, package, render, review  # noqa: E402

WORK = ROOT / "_work"
IMAGE_DIR = WORK / "Images"
ASSET_DIR = WORK / "assets"   # rendering assets, not delivered in the archive
CONFIG_DIR = ROOT / "engine" / "config"

app = FastAPI(title="UAD 3.6 Report Engine")

# The live session: the pipeline result plus whatever the appraiser has changed.
SESSION: dict[str, Any] = {"packet": None, "state": None, "edits": {}}

# Edits are shared and durable, so every viewer of a report sees the same
# values whatever device they open it on.
REPORT_ID = "default"
STORE = Store(WORK / "report.db")
ACCESS = Access()


# ------------------------------------------------------------------ session
def load(packet_path: str, effective: date, signature: date | None = None) -> dict:
    """Run the pipeline and cache the result for editing."""
    exhibits = images_mod.load_manifest(CONFIG_DIR, ROOT)
    facts, trend, rates, grids, data, report = pipeline.run(
        packet_path,
        effective_date=effective,
        signature_date=signature,
        images=images_mod.image_nodes(exhibits),
    )
    closed = [g for g in grids if not g.is_active_listing]
    opinion, weights = pipeline.reconcile(closed)

    images_mod.write(exhibits, IMAGE_DIR)
    _copy_signature(facts)

    state = {
        "facts": facts.as_dict(),
        "trend": {**trend.as_dict(), "summary": trend.summary()},
        "rates": {k: v.as_dict() for k, v in rates.items()},
        "grids": [g.as_dict() for g in grids],
        "weights": weights,
        "opinion_of_value": opinion,
        "reconciliation_comment": pipeline._reconciliation_text(
            grids, closed, opinion, weights, facts
        ),
        "effective_date": effective.isoformat(),
        "signature_date": (signature or effective).isoformat(),
        "findings": [f.as_dict() for f in report.findings],
        "images": [e.as_dict() for e in exhibits],
        "model": data,
        "schema_valid": report.schema_valid,
        "edits": STORE.values(REPORT_ID),
    }
    SESSION["packet"] = packet_path
    SESSION["state"] = state
    return state


def _copy_signature(facts) -> None:
    """Place the signature graphic where the report template expects it."""
    source = facts.appraiser.get("assets", {}).get("signature_image")
    if not source:
        return
    path = ROOT / source
    if not path.exists():
        return
    from PIL import Image

    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with Image.open(path) as image:
        image.convert("RGBA").save(ASSET_DIR / "SIGNATURE.png")


def current() -> dict:
    if SESSION["state"] is None:
        raise RuntimeError("No packet loaded; start the server with a packet path.")
    return SESSION["state"]


def _apply_edits(state: dict) -> dict:
    """Overlay the shared edits onto the generated values."""
    edited = dict(state)
    edited["field_edits"] = STORE.values(REPORT_ID)
    for path, value in edited["field_edits"].items():
        if path == "opinion_of_value":
            edited["opinion_of_value"] = _number(value, state["opinion_of_value"])
        elif path == "reconciliation_comment":
            edited["reconciliation_comment"] = value
        elif path in ("effective_date", "signature_date"):
            edited[path] = value
        elif path.startswith("commentary."):
            edited.setdefault("commentary", {})[path.split(".", 1)[1]] = value
    return edited


def _number(value: Any, fallback: Any) -> Any:
    try:
        return float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return fallback


def _address(state: dict) -> str:
    addr = state["facts"]["subject"].get("address", {})
    return (
        f"{addr.get('line', '')}, {addr.get('city', '')}, "
        f"{addr.get('state', '')} {addr.get('postal_code', '')}"
    )


def _html(editable: bool = True) -> str:
    state = _apply_edits(current())
    sections = review.build(state)
    return render.document(
        sections,
        address=_address(state),
        appraiser=state["facts"]["appraiser"],
        editable=editable,
    )


@app.middleware("http")
async def require_passcode(request: Request, call_next):
    """A tunnelled server is reachable by anyone with the URL."""
    blocked = guard(ACCESS, request)
    if blocked is not None:
        return blocked
    return await call_next(request)


@app.post("/access")
async def unlock(request: Request) -> Response:
    form = await request.form()
    token = ACCESS.check(str(form.get("code", "")), request.client.host if request.client else "")
    if token is None:
        return gate_page(error=True)
    response = Response(status_code=303, headers={"Location": "/"})
    ACCESS.grant(response, token)
    return response


@app.get("/healthz")
def healthz() -> JSONResponse:
    return JSONResponse({"ok": True, "revision": STORE.revision(REPORT_ID)})


# ------------------------------------------------------------------- routes
@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return _html(editable=True)


@app.get("/print", response_class=HTMLResponse)
def printable() -> str:
    return _html(editable=False)


@app.get("/images/{name}")
def image(name: str):
    """Serve a delivered exhibit, or a rendering asset such as the signature."""
    for folder in (IMAGE_DIR, ASSET_DIR):
        path = folder / name
        if path.exists():
            return FileResponse(path)
    return Response(status_code=404)


@app.post("/api/edits")
async def save_edits(request: Request) -> JSONResponse:
    """Record edits and push them to everyone with the report open."""
    body = await request.json()
    editor = body.pop("__editor", "")
    name = body.pop("__name", "") or "A reviewer"
    STORE.seen(editor or str(uuid.uuid4()), name)
    revision = STORE.apply(REPORT_ID, body, editor=name)
    return JSONResponse({"revision": revision, "editors": STORE.editors()})


@app.get("/api/sync")
def sync(since: int = 0) -> JSONResponse:
    """Catch a viewer up after a reconnect."""
    return JSONResponse({
        "revision": STORE.revision(REPORT_ID),
        "values": STORE.values(REPORT_ID),
        "editors": STORE.editors(),
    })


@app.get("/api/stream")
def stream() -> StreamingResponse:
    """Live changes, as server-sent events."""
    queue = STORE.subscribe()

    def events():
        try:
            yield from STORE.stream(queue)
        finally:
            STORE.unsubscribe(queue)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/presence")
async def presence(request: Request) -> JSONResponse:
    body = await request.json()
    STORE.seen(body.get("editor", ""), body.get("name", "A reviewer"))
    return JSONResponse({"editors": STORE.editors()})


@app.post("/api/reset")
def reset() -> JSONResponse:
    """Discard every edit and return to what the engine generated."""
    STORE.reset(REPORT_ID)
    return JSONResponse({"revision": 0})


@app.get("/api/state")
def state() -> JSONResponse:
    snapshot = {k: v for k, v in current().items() if k != "model"}
    return JSONResponse(snapshot)


@app.post("/api/package")
def build_package() -> Response:
    state = _apply_edits(current())

    order = state["facts"]["order"]
    pdf_bytes = package.html_to_pdf(
        _html(editable=False),
        base_url="http://127.0.0.1:8000/print",
        order_id=order.get("order_number", ""),
        loan_id=order.get("loan_number", ""),
        appraisal_version=builder.APPRAISAL_VERSION,
        form_version=builder.FORM_VERSION,
        cookie=(COOKIE, ACCESS.token),
    )
    xml_bytes = model.serialize(state["model"])

    archive = package.build(
        pdf_bytes=pdf_bytes, xml_bytes=xml_bytes, image_dir=IMAGE_DIR
    )
    name = package.filename_for(
        state["facts"]["subject"]["address"].get("line", "appraisal"),
        state["effective_date"],
    )
    return Response(
        content=archive,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "X-Filename": name,
        },
    )
