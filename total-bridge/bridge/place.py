"""Putting a file's photographs into the right places in TOTAL.

Where a picture belongs is published.  A-1 gives every ``ImageCategoryType`` a
Report Location naming the section it displays in, so ``VehicleStorageExhibit``
goes to Vehicle Storage and ``UnitInteriorExhibit`` to Unit Interior.  That half
of the routing is read out of the map.

The other half -- which of TOTAL's section keys *is* Vehicle Storage -- has no
shared identifier: ``garage`` is TOTAL's own word for it.  Rather than keep a
table of thirty guesses, each section is asked what it holds: its controls carry
Report Field IDs, the map says which section each of those belongs to, and the
section they mostly agree on is the section.  So the correspondence is derived
from the two indexes, and a renamed key changes nothing.

A slot is filled the way a person fills it -- by dropping a picture on it.
Each slot has a file input, and setting that input's files does work in the
sense that the file is there: ``input.files.length`` becomes 1.  It changes
nothing, because the form is not listening to that input.  It listens to the
drop zone, exactly as the words in the empty slot say.  So the picture is
built into a File in the page and a real drop is dispatched.

Every placement is then read back.  A slot that has taken a picture loses its
``photo-none`` class, and that -- not the absence of an exception -- is what
counts as placed.  The first version of this reported 41 successes while
placing nothing.
"""
from __future__ import annotations

import base64
import json
import time
from collections import Counter
from dataclasses import dataclass, field as _field

from .images import Photo, staging

# A picture that names no section in A-1 still has a home.  These go by role:
# the comparison grid's photographs belong to a *column*, and which column is
# the property the picture hangs under -- not whichever slot happens to be
# free.  Putting comparable 3's photograph above comparable 1 would be a
# quietly wrong report, so these are addressed by control name.
# The grid's own photographs are not in the Sales Comparison section: TOTAL
# builds the columns in its side-by-side view, and that is where the controls
# exist.  Looking for them anywhere else finds nothing and reports, wrongly,
# that the report has no room for them.
BY_ROLE = {
    "PropertyPhoto": ("sxs-section-key", "{col}_PHOTO"),
    "SalesComparableMap": ("sxs-section-key", "GSU_MAP"),
    "DwellingFront": ("dwelling-exterior-1", "DE1_PHOTO1"),
}


def _column_control(photo, pattern: str) -> str:
    """The control a role-placed picture belongs in."""
    if "{col}" not in pattern:
        return pattern
    # A picture hanging under a comparable is never the subject's, whatever
    # its ordinal says.  Defaulting it to the subject column is how four
    # comparable photographs ended up overwriting one subject slot.
    if photo.owner and photo.owner != "SubjectProperty":
        return pattern.format(col=f"GC{max(photo.ordinal, 1)}")
    if photo.ordinal and photo.ordinal > 0 and photo.owner != "SubjectProperty":
        return pattern.format(col=f"GC{photo.ordinal}")
    return pattern.format(col="GSU")


@dataclass
class Placement:
    placed: int = 0
    no_slot: list = _field(default_factory=list)
    no_section: list = _field(default_factory=list)
    unavailable: list = _field(default_factory=list)
    failed: list = _field(default_factory=list)
    # slots TOTAL fills itself: the subject photo is building 1's front photo
    total_owned: list = _field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.placed} placed, {len(self.no_slot)} had no free slot, "
                f"{len(self.no_section)} had nowhere to go, "
                f"{len(self.unavailable)} not in the file, "
                f"{len(self.failed)} failed")


_SLOTS = r"""
(() => {
  const out = [];
  for (const img of document.querySelectorAll('img[fn]')) {
    const box = img.closest('.photo-container');
    if (!box) continue;
    const input = box.querySelector('input[type=file]');
    if (!input) continue;
    // The caption a slot already carries says which exhibit it is.  TOTAL
    // creates a slot for every room in the schedule and labels it, so this is
    // how a picture finds the room it belongs to instead of the next gap.
    let scope = box;
    for (let i = 0; i < 4 && scope.parentElement; i++) scope = scope.parentElement;
    let caption = '';
    for (const e of scope.querySelectorAll('[fn]')) {
      const fn = e.getAttribute('fn') || '';
      if (/CAPTION|DESCRIPTION/.test(fn)) {
        const text = (e.getAttribute('data-value') || e.textContent || '').trim();
        if (text) { caption = text; break; }
      }
    }
    out.push({fn: img.getAttribute('fn'),
              instance: img.getAttribute('instance') || '0',
              inputId: input.id,
              caption: caption,
              empty: /photo-none/.test(String(img.className || ''))});
  }
  return out;
})()
"""


def _flat(text: str) -> str:
    return " ".join((text or "").upper().replace("-", " ").split())


def _matching_slot(photo: Photo, free: list[dict]) -> dict | None:
    """The slot this picture is already labelled for, if there is one.

    TOTAL builds an exhibit slot for every room in the schedule and captions
    it.  A file's pictures are captioned too.  Matching the two puts the
    kitchen photograph in the kitchen slot -- and, just as importantly, stops
    a second kitchen exhibit being created beside the one that exists.
    """
    want = _flat(photo.caption)
    if not want:
        return None
    for slot in free:
        if _flat(slot.get("caption")) == want:
            return slot
    for slot in free:
        here = _flat(slot.get("caption"))
        if here and (want in here or here in want):
            return slot
    return None


# Build the picture in the page and drop it on the slot, then say whether the
# slot took it.  Chunked, because a photograph is bigger than is comfortable in
# a single expression.
_DROP = """
(async () => {
  const input = document.getElementById(%(input)s);
  if (!input) return {ok: false, why: 'slot is gone'};
  const box = input.closest('.photo-container');
  if (!box) return {ok: false, why: 'slot has no container'};
  const bytes = Uint8Array.from(atob(window.__uadPhoto), c => c.charCodeAt(0));
  const file = new File([bytes], %(name)s, {type: %(mime)s});
  const dt = new DataTransfer();
  dt.items.add(file);
  const zone = box.querySelector('.photo-image-wrap') || box;
  for (const kind of ['dragenter', 'dragover', 'drop']) {
    zone.dispatchEvent(new DragEvent(kind,
        {bubbles: true, cancelable: true, dataTransfer: dt}));
  }
  await new Promise(done => setTimeout(done, 1200));
  const img = box.querySelector('img[fn]');
  return {ok: !!img && !/photo-none/.test(String(img.className || ''))};
})()
"""


def drop_photo(report, slot: dict, photo: Photo) -> dict:
    """Put one picture in one slot, and report what the slot did."""
    if photo.data:
        payload = base64.b64encode(photo.data).decode()
    elif photo.source and photo.source.exists():
        payload = base64.b64encode(photo.source.read_bytes()).decode()
    else:
        return {"ok": False, "why": "the file does not carry this picture"}

    page = report.page
    page.evaluate("window.__uadPhoto = '';")
    step = 200_000
    for i in range(0, len(payload), step):
        page.evaluate(f"window.__uadPhoto += {json.dumps(payload[i:i + step])};")
    try:
        return page.evaluate(_DROP % {"input": json.dumps(slot["inputId"]),
                                      "name": json.dumps(photo.name),
                                      "mime": json.dumps(photo.mime)},
                             await_promise=True) or {"ok": False, "why": "no answer"}
    finally:
        page.evaluate("delete window.__uadPhoto;")


def sections_by_name(report, case) -> dict[str, str]:
    """Which of TOTAL's section keys corresponds to each section name.

    Asked of the report rather than assumed: a section's controls carry Report
    Field IDs, and the map knows the section each ID belongs to.
    """
    found: dict[str, str] = {}
    for key, controls, _values in report.walk():
        votes = Counter()
        for control in controls:
            entry = case.map.get(control.get("fmid") or "")
            if entry and entry.get("section"):
                votes[entry["section"]] += 1
        if votes:
            name = votes.most_common(1)[0][0]
            found.setdefault(name, key)
    return found


def slots(report) -> list[dict]:
    return report.page.evaluate(_SLOTS) or []


def find_slot(report, fn: str, instance: str = "0", exclude: str = "") -> dict | None:
    """The slot for a control wherever it lives; leaves that section open."""
    for key in report.sections():
        if key == exclude:
            continue
        report.goto(key)
        slot = next((s for s in slots(report) if s["fn"] == fn and str(s["instance"]) == str(instance)), None)
        if slot is not None:
            return slot
    return None


def target_key(photo: Photo, by_name: dict[str, str], categories: dict) -> str:
    """The section key a photograph belongs in, or "" when nothing claims it."""
    entry = categories.get(photo.category) or {}
    name = entry.get("section") or ""
    if name and name in by_name:
        return by_name[name]
    # Names that differ only in wording between the two indexes.
    if name:
        flat = "".join(ch for ch in name.lower() if ch.isalnum())
        for known, key in by_name.items():
            if "".join(ch for ch in known.lower() if ch.isalnum()) == flat:
                return key
    role = BY_ROLE.get(photo.category)
    if role:
        return role[0]
    return ""


def place(report, case, found: list[Photo], *, dry_run: bool = False,
          progress=None, known: list[Photo] | None = None) -> Placement:
    """Put each photograph in the section the standard files it under.

    `known`: every picture of the file (default `found`), to recognise what a
    slot already holds when only the leftovers of `place_by_file` are placed.
    """
    out = Placement()
    known = known or found
    folder = staging()
    by_name = sections_by_name(report, case)

    # Group by destination so each section is opened once.
    wanted: dict[str, list[Photo]] = {}
    for photo in found:
        if not photo.available:
            out.unavailable.append((photo.category, photo.name))
            continue
        key = target_key(photo, by_name, case.categories)
        if not key:
            out.no_section.append((photo.category, photo.name))
            continue
        wanted.setdefault(key, []).append(photo)

    for key, group in wanted.items():
        report.goto(key)
        free = [s for s in slots(report) if s["empty"]]
        for photo in group:
            if not free and photo.category not in BY_ROLE:
                out.no_slot.append((photo.category, photo.name))
                if progress:
                    progress(photo, key, None, "no free slot")
                continue
            role = BY_ROLE.get(photo.category)
            slot = None
            if role and _column_control(photo, role[1]) == "GSU_PHOTO":
                # TOTAL copies building 1's front photo (DE1_PHOTO1) into the
                # subject's photo fields -- GSU_PHOTO, GSU_PHOTO_SUMMARY (the one
                # its XML delivers as PropertyPhoto), RSU_PHOTO, GRU_PHOTO -- one
                # second after any PHOTO1 changes (dwelling-exterior calcs).  A
                # separate subject photo placed here would print in the grid but
                # not be delivered, and be overwritten on the next change (E-039)
                out.total_owned.append((photo.category, photo.name))
                if progress:
                    progress(photo, key, "GSU_PHOTO", "TOTAL uses building 1's front photo: not placed")
                continue
            if role:
                wanted_fn = _column_control(photo, role[1])
                slot = next((s for s in slots(report)
                             if s["fn"] == wanted_fn), None)
                if slot is None:
                    # the control lives elsewhere in this build (GSU_MAP is in
                    # the Sales Comparison section, not the grid): look for it
                    # rather than trust a remembered section
                    slot = find_slot(report, wanted_fn, exclude=key)
                if slot is None:
                    out.no_slot.append((photo.category, photo.name))
                    if progress:
                        progress(photo, key, wanted_fn, "no such control")
                    continue
                # never replace a picture of the same kind: the slot already
                # holds this category's picture for another building or column
                # (E-039).  A different kind may be replaced -- TOTAL's import
                # puts the front photo in the subject's grid slot as a stand-in
                # when the file names the subject photo separately.
                held = _held_category(report, slot, known)
                if held == photo.category:
                    out.no_slot.append((photo.category, photo.name))
                    if progress:
                        progress(photo, key, wanted_fn, f"holds another {held} picture: not replaced")
                    continue
            else:
                slot = _matching_slot(photo, free)
                if slot is not None:
                    free.remove(slot)
                else:
                    slot = free.pop(0)
            if dry_run:
                out.placed += 1
                if progress:
                    progress(photo, key, slot["fn"], "would place")
                continue

            try:
                result = drop_photo(report, slot, photo)
            except Exception as exc:
                result = {"ok": False, "why": str(exc)[:90]}
            if result.get("ok"):
                out.placed += 1
                if progress:
                    progress(photo, key, slot["fn"], "placed")
            else:
                why = result.get("why", "the slot did not take it")
                out.failed.append((photo.category, photo.name, why))
                if progress:
                    progress(photo, key, slot["fn"], f"not taken: {why}")
            # A slot that took a picture is no longer free, and the section may
            # have grown another one; re-read rather than assume.
            free = [s for s in slots(report) if s["empty"]]
    return out


# ------------------------------------------------------------------ by file
# TOTAL's own import builds a photo slot for every picture the file names --
# under its room, its defect, its garage, its amenity -- captions it, and sets
# the slot's value to the picture's file location.  It never loads the bytes
# (it does not read embedded pictures).  So each empty slot already says which
# file it wants: filling slots by that name places every picture exactly where
# TOTAL's importer put its record, with no category guessing.  Pictures no slot
# asks for are then placed by category (place()).  CATALOG E-033.
_EXPECTED = r"""
(() => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const out = [];
  const walk = o => { for (const x of (o.dataObjects || [])) {
    // PHOTO, and PHOTO<n>: each building's front picture is DE<n>_PHOTO1 --
    // missed by /PHOTO$/, which put building 2's front on building 1 (E-039)
    if (!(x.dataObjects || []).length && /PHOTO\d*$/.test(x.key)) {
      const v = String(x.value ?? '').trim();
      if (/\.(png|jpe?g|gif|bmp|tiff?|webp|pdf)$/i.test(v)) {
        let has = 0;
        try { const i = d.GetImage(x.key, x.instance); has = i ? String(i).length : 0; } catch (e) {}
        out.push({fn: x.key, instance: String(x.instance ?? 0), file: v, loaded: has > 0});
      }
    }
    walk(x);
  } };
  walk(d);
  return out;
})()
"""


def _held_category(report, slot: dict, found: list[Photo]) -> str:
    """The category of the file's picture this slot holds now, or "" when it is
    empty or holds nothing from the file."""
    if slot.get("empty"):
        return ""
    try:
        value = report.page.evaluate(
            "window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName)"
            f".GetDataValue({json.dumps(slot['fn'])}, {int(slot.get('instance') or 0)})") or ""
    except Exception:
        return ""
    key = _file_key(str(value))
    return next((p.category for p in found if p.location and _file_key(p.location) == key), "")


def _file_key(location: str) -> str:
    """An image location -> its bare lower-case name: Images/SF1_Kitchen.png ->
    sf1_kitchen (folder and extension ignored: a placed picture is renamed
    .jpg, the file names it .png)."""
    base = location.replace("\\", "/").rsplit("/", 1)[-1]
    return base.rsplit(".", 1)[0].strip().lower()


def expected_files(report) -> list[dict]:
    return report.page.evaluate(_EXPECTED) or []


def place_by_file(report, found: list[Photo], progress=None) -> tuple[Placement, list[Photo]]:
    """Fill every empty slot that names a file with that file's picture.

    Returns the placement and the pictures no slot asked for.
    """
    out = Placement()
    by_name: dict[str, list[Photo]] = {}
    for photo in found:
        if photo.location:
            by_name.setdefault(_file_key(photo.location), []).append(photo)
    want = [e for e in expected_files(report) if not e["loaded"]]
    wanted_keys = {(e["fn"], e["instance"]): _file_key(e["file"]) for e in want}
    used: set[int] = set()
    if want:
        for key in report.sections():
            report.goto(key)
            for slot in slots(report):
                name = wanted_keys.get((slot["fn"], str(slot["instance"])))
                if not name or not slot["empty"]:
                    continue
                photo = next((p for p in by_name.get(name, []) if p.available), None)
                if photo is None:
                    out.unavailable.append((slot["fn"], name))
                    continue
                try:
                    result = drop_photo(report, slot, photo)
                except Exception as exc:                    # recorded, not fatal
                    result = {"ok": False, "why": str(exc)[:90]}
                if result.get("ok"):
                    out.placed += 1
                    used.add(id(photo))
                    wanted_keys.pop((slot["fn"], str(slot["instance"])), None)
                    if progress:
                        progress(photo, key, slot["fn"], "placed by file name")
                else:
                    out.failed.append((slot["fn"], name, result.get("why", "not taken")))
            if not wanted_keys:
                break
        # linked exhibits (e.g. the comparable-photo exhibit mirrors the grid
        # photo) fill themselves once their source is placed: re-read first
        now_loaded = {(e["fn"], e["instance"]) for e in expected_files(report) if e["loaded"]}
        for (fn, inst), name in wanted_keys.items():
            if (fn, inst) not in now_loaded:
                out.no_slot.append((f"{fn}#{inst}", name))
    rest = [p for p in found if id(p) not in used and _file_key(p.location) not in
            {_file_key(e["file"]) for e in want if e["loaded"]}]
    return out, rest
