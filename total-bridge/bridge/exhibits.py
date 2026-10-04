"""Photographs into a report: look first, then place by what each picture shows.

The failure this exists to prevent (CATALOG E-047): pictures placed by folder
name and free slot, without being looked at -- a living room captioned
Kitchen, a basement room filed under Level 1, the AC condenser filed as the
Deck.  So placement is two steps:

1. ``contact_sheets(folder, out)`` -- one labelled sheet per sub-folder, EXIF
   orientation applied (``ImageOps.exif_transpose``, no extra rotation).  The
   agent VIEWS every sheet and writes a manifest row per picture.
2. ``place(report, manifest)`` -- adds exhibit rows as needed (through the
   guidance panel, E-046), drops each picture, writes category + description.

Manifest (in case.json, key "photos"):

    {"section": "interior-1", "file": "first floor/IMG_7188.jpeg",
     "category": "Level 1 - Kitchen", "description": "Kitchen"}
    {"slot": "DE1_PHOTO1", "section": "dwelling-exterior-1", "file": "..."}

Exhibit categories come from the field's own option list and exist only after
the thing they name exists (Unit Interior offers "Level 1 - Kitchen" once the
room table holds a Level 1 Kitchen) -- so photos go in AFTER rooms/levels.
Every picture in the folder must be in the manifest or listed in
"photos_excluded" with a reason.
"""
from __future__ import annotations

from pathlib import Path

from . import formkit, place, rtv
from .images import Photo

#: section -> (photo field, category field, description field)
TABLES = {
    "interior-1": ("UI1_UNIT_INTERIOR_EXHIBIT_PHOTO", "UI1_UNIT_INTERIOR_EXHIBIT_CATEGORY",
                   "UI1_UNIT_INTERIOR_EXHIBIT_DESCRIPTION"),
    "dwelling-exterior-1": ("DE1_EXTERIOR_EXHIBIT_PHOTO", "DE1_EXTERIOR_EXHIBIT_CATEGORY",
                            "DE1_EXTERIOR_EXHIBIT_DESCRIPTION"),
    "site": ("SIT_EXHIBIT_PHOTO", "SIT_EXHIBIT_CATEGORY", "SIT_EXHIBIT_DESCRIPTION"),
    "garage": ("VS_EXHIBIT_PHOTO", "VS_EXHIBIT_CATEGORY", "VS_EXHIBIT_DESCRIPTION"),
    "amenities": ("SPA_EXHIBIT_PHOTO", "SPA_EXHIBIT_CATEGORY", "SPA_EXHIBIT_DESCRIPTION"),
    "sub-prop": ("SUBJECT_EXHIBIT_PHOTO", None, "SUBJECT_EXHIBIT_DESCRIPTION"),
    "assignment": ("ASSIGNMENT_EXHIBIT_PHOTO", None, "ASSIGNMENT_EXHIBIT_DESC"),
    "sketch": ("SKT_EXHIBIT_PHOTO", "SKT_EXHIBIT_CATEGORY", "SKT_EXHIBIT_DESCRIPTION"),
}
# unit n of a 2-4 unit report (sections interior-2 .. interior-4, fields UI<n>_)
for _n in range(2, 5):
    TABLES[f"interior-{_n}"] = tuple(f"UI{_n}_UNIT_INTERIOR_EXHIBIT_{k}" for k in ("PHOTO", "CATEGORY", "DESCRIPTION"))

IMAGE_TYPES = {".jpg", ".jpeg", ".png"}


def contact_sheets(folder: str | Path, out: str | Path, cols: int = 4) -> list[Path]:
    """One labelled contact sheet per sub-folder (and one for loose pictures)."""
    from PIL import Image, ImageDraw, ImageFont, ImageOps
    folder, out = Path(folder), Path(out)
    out.mkdir(parents=True, exist_ok=True)
    try:
        font = ImageFont.truetype("arial.ttf", 22)
    except OSError:
        font = ImageFont.load_default()
    groups: dict[str, list[Path]] = {}
    for p in sorted(folder.rglob("*")):
        if p.suffix.lower() in IMAGE_TYPES and p.is_file():
            groups.setdefault(str(p.parent.relative_to(folder)) or ".", []).append(p)
    sheets = []
    for name, files in groups.items():
        W, H = 300, 400
        rows = (len(files) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * W, rows * (H + 30)), "white")
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(files):
            im = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
            im.thumbnail((W - 6, H - 6))
            x, y = (i % cols) * W, (i // cols) * (H + 30)
            sheet.paste(im, (x + 3, y + 30))
            d.text((x + 6, y + 4), f.stem, fill="red", font=font)
        safe = "".join(ch if ch.isalnum() else "_" for ch in name)[:40] or "root"
        path = out / f"sheet_{safe}.jpg"
        sheet.save(path, quality=80)
        sheets.append(path)
    return sheets


def _photo(src: Path, caption: str) -> Photo:
    mime = "image/png" if src.suffix.lower() == ".png" else "image/jpeg"
    return Photo(category="", caption=caption, location=src.name, mime=mime,
                 data=None, source=src, owner="SubjectProperty", ordinal=0)


def drop(report, section: str, field: str, instance: int, src: Path, caption: str = "") -> bool:
    report.goto(section, settle=1.2)
    slot = next((s for s in place.slots(report)
                 if s["fn"] == field and str(s["instance"]) == str(instance)), None)
    if not slot:
        return False
    return bool(place.drop_photo(report, slot, _photo(Path(src), caption)).get("ok"))


def not_available_card(label: str, out: str | Path) -> Path:
    """A plain card stating that no photograph exists for this exhibit.

    The owner's rule for a picture that was not taken: label the exhibit, no
    picture.  TOTAL rejects an interior exhibit row without an image ("A photo
    is required for this exhibit", E-059), so the exhibit carries this card --
    text only, never anything that could pass for a photograph of the property.
    """
    from PIL import Image, ImageDraw, ImageFont
    out = Path(out)
    im = Image.new("RGB", (1600, 1200), (238, 238, 238))
    d = ImageDraw.Draw(im)
    d.rectangle([40, 40, 1559, 1159], outline=(150, 150, 150), width=6)
    try:
        big, small = ImageFont.truetype("arial.ttf", 84), ImageFont.truetype("arial.ttf", 56)
    except OSError:
        big = small = ImageFont.load_default()
    for text, font, y in (("PHOTOGRAPH NOT AVAILABLE", big, 430), (label, small, 600),
                          ("No photograph was taken of this room at inspection.", small, 700)):
        wdt = d.textlength(text, font=font)
        d.text(((1600 - wdt) / 2, y), text, fill=(60, 60, 60), font=font)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out)
    return out


def link_guid(report, category_field: str, instance: int, label: str) -> str | None:
    """The row GUID TOTAL pairs with `label` in this category field's own list
    (``field.items[i]`` <-> ``field.linkguids[i]``), or None when the field
    keeps no links (or the label is not offered).  An empty label -> ""."""
    import json
    return report.page.evaluate("""((k, i, label) => {
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      const f = d.GetDataField(k, i);
      if (!f || !Array.isArray(f.linkguids)) return null;
      if (!label) return '';
      const items = (f.items || []).map(x => String(x && x.value !== undefined ? x.value : x));
      const at = items.indexOf(label);
      return at > -1 ? (f.linkguids[at] || '') : null; })(%s, %d, %s)"""
                                % (json.dumps(category_field), instance, json.dumps(label)))


def place_manifest(report, manifest: list[dict], base: str | Path, dry_run: bool = False) -> dict:
    """Place every manifest row.  Returns {"placed": n, "failed": [...], "plan": [...]}."""
    base = Path(base)
    tables: dict[str, list[dict]] = {}
    singles: list[dict] = []
    for row in manifest:
        (singles if row.get("slot") else tables.setdefault(row["section"], [])).append(row)
    out = {"placed": 0, "failed": [], "plan": []}
    for section, rows in tables.items():
        pf, cf, df = TABLES[section]
        if not dry_run:
            formkit.ensure_exhibit_rows(report, section, pf, df, len(rows))
            formkit.trim_exhibit_rows(report, section, pf, df, len(rows))     # E-069
        writes = []
        for i, row in enumerate(rows):
            # a row with no file labels an exhibit whose picture does not exist
            # (owner: "just label the exhibits but without picture")
            name = row.get("file") or "(no photograph)"
            out["plan"].append(f"{section} #{i} {name} [{row.get('category', '')}] {row.get('description', '')}")
            if dry_run:
                continue
            if row.get("file"):
                src = base / row["file"]
                ok = src.exists() and drop(report, section, pf, i, src, row.get("description", ""))
                out["placed"] += ok
                if not ok:
                    out["failed"].append(f"{section} #{i} {row['file']}")
            else:
                out["labelled"] = out.get("labelled", 0) + 1
            if cf and row.get("category") is not None:
                items = formkit.field_items(report, cf, i)
                cat = formkit.stored_value(items, row["category"]) if items else row["category"]
                writes.append({"field": cf, "instance": i, "value": cat if cat is not None else row["category"]})
                # CATALOG E-056: the category is re-derived on every calc pass
                # from the exhibit's link GUID (<...>_EXHIBIT_GUID_ID -> the
                # room / feature row), so the link must name the same row
                guid = link_guid(report, cf, i, cat if cat is not None else row["category"])
                if guid is not None:
                    writes.append({"field": cf[:-len("CATEGORY")] + "GUID_ID", "instance": i, "value": guid})
            if df:
                writes.append({"field": df, "instance": i, "value": row.get("description", "")})
        if writes:
            rtv.put(report, writes)
    for row in singles:
        src = base / row["file"]
        out["plan"].append(f"{row['slot']} <- {row['file']}")
        if dry_run:
            continue
        ok = src.exists() and drop(report, row["section"], row["slot"], row.get("instance", 0), src,
                                   row.get("description", ""))
        out["placed"] += ok
        if not ok:
            out["failed"].append(f"{row['slot']} {row['file']}")
        if row.get("description_field"):
            rtv.put(report, [{"field": row["description_field"], "instance": row.get("instance", 0),
                              "value": row.get("description", "")}])
    return out
