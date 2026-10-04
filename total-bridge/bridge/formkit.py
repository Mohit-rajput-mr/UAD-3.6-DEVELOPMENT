"""The structural moves TOTAL only allows through its own machinery.

A value can be written into the data layer (``rtv.put``).  A *row* cannot: a
comparable column, an exhibit row, a level, a room, a contact block all have
to be created by the handler TOTAL's own button runs, and some rows have to be
removed the same way.  Each function here does one of those, the way the form
itself does it, and each is recorded with its evidence in
``knowledge/errors/CATALOG.md``:

    add_comparables       E-046  dataSet.CompManagers.get("sales").AddComp
    ensure_exhibit_rows   E-046  focus a cell of the exhibit table, then the
                                 guidance button that appears
    add_rows              --     "+ Add Level", "+ Add Room", "+ AMC": visible
                                 guidance buttons clicked through the input domain
    remove_row_group      E-050  dataSet.RemoveFieldDataGroup(key, instance)
    fire                  E-048  some validators listen to one event only
                                 (SelectClosed 15, HidePopup 17), not ValueChanged
    stored_value          E-049  "stored^shown" pick lists store the LEFT half

and three formats, because a value in the wrong shape sits in the data layer
and never reaches the export (the UAD-1643 lesson): ``money``, ``area``,
``mdy``.

Nothing here writes a value that no source gave; the case kit decides values.
"""
from __future__ import annotations

import json
import time

from . import ui

#: dataChangedEventHandler action codes, read from TOTAL's bundle (0.0.1.3855).
LEAVE_FIELD = 6          # a text field left; what rtv.commit raises
SELECT_CLOSED = 15       # a pick list closed
HIDE_POPUP = 17          # a grid popup (vehicle storage, etc.) closed


# ---------------------------------------------------------------- formats
def money(n) -> str:
    """The form's own money format: $(5,100)  $7,750  $0."""
    n = int(round(float(n)))
    if n == 0:
        return "$0"
    return f"$({abs(n):,})" if n < 0 else f"${n:,}"


def area(n) -> str:
    """The form's own area format: 1,000 Sq. Ft."""
    return f"{int(round(float(n))):,} Sq. Ft."


def mdy(date: str) -> str:
    """mm/dd/yyyy from yyyy-mm-dd or mm/dd/yyyy."""
    date = str(date).strip()
    if len(date) == 10 and date[4] == "-":
        return f"{date[5:7]}/{date[8:10]}/{date[:4]}"
    return date


# ---------------------------------------------------------------- pick lists
def split_items(items: list[str]) -> list[tuple[str, str]]:
    """[(stored, shown)] for a field's options.  "a^b" stores a and shows b."""
    out = []
    for it in items or []:
        s = str(it)
        stored, _, shown = s.partition("^")
        out.append((stored, shown or stored))
    return out


def stored_value(items: list[str], wanted: str) -> str | None:
    """The text to write so TOTAL stores `wanted`, or None if it is not offered.

    Accepts either half: "None" for the option "No Hazard Zone Noted^None"
    returns "No Hazard Zone Noted" -- writing "None" there exports a hazard
    zone *called* None (CATALOG E-049).
    """
    w = str(wanted).strip().lower()
    pairs = split_items(items)
    for stored, shown in pairs:
        if stored.lower() == w:
            return stored
    for stored, shown in pairs:
        if shown.lower() == w:
            return stored
    return None


def field_items(report, key: str, instance: int = 0) -> list[str]:
    """The option list TOTAL holds for a data field (read live, never assumed)."""
    return report.page.evaluate("""((k, i) => {
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      let it = null;
      const w = o => { for (const x of (o.dataObjects || [])) {
          if (x.key === k && (x.instance ?? 0) === i && !(x.dataObjects || []).length && it === null)
            it = (x.items || []).map(v => String(v && (v.value !== undefined ? v.value : v)));
          w(x); } };
      w({dataObjects: d.dataObjects}); return it || []; })(%s, %d)""" % (json.dumps(key), instance)) or []


# ---------------------------------------------------------------- reading
def values(report, keys: list[str]) -> dict[str, str]:
    """key#instance -> value for every leaf whose key is listed (all instances)."""
    return report.page.evaluate("""(ks => {
      const want = new Set(ks);
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      const out = {};
      const w = o => { for (const x of (o.dataObjects || [])) {
          if (want.has(x.key) && !(x.dataObjects || []).length)
            out[x.key + '#' + (x.instance ?? 0)] = x.value == null ? '' : String(x.value);
          w(x); } };
      w({dataObjects: d.dataObjects}); return out; })(%s)""" % json.dumps(sorted(set(keys)))) or {}


def count(report, key: str) -> int:
    return report.page.evaluate("""(k => {
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      let n = 0; const w = o => { for (const x of (o.dataObjects || [])) {
          if (x.key === k && !(x.dataObjects || []).length) n++; w(x); } };
      w({dataObjects: d.dataObjects}); return n; })(%s)""" % json.dumps(key)) or 0


def unset(report, keys: list[str], groups: list[str] = ()) -> dict:
    """Make fields *absent* again: value ``null``, not ``""``.

    CATALOG E-055: TOTAL's global validation (realTimeValidation.
    executeRtvRulesOnChildrenRecursively) skips a field whose value is null
    and validates one that holds "" -- so a block "cleared" by writing blanks
    (supervisor, SRPA, reconsideration of value, an unused site-feature row, a
    comparable's optional pick row) becomes a block of required-but-empty
    fields.  Every leaf whose key is listed, or that sits in one of `groups`
    (data-group keys such as "supervisor"), is set to null; all copies.
    Listed keys are cleared whatever they hold; inside `groups` only leaves
    that are already blank are touched, so real data is never wiped.

    The field's ``value`` setter turns null into "" (``value ?? ""``), so the
    untouched state is restored on the backing ``_value`` -- measured: it stays
    null through TOTAL's own ExecuteAllCalcs + validation run.
    """
    return report.page.evaluate("""((ks, gs) => {
      const want = new Set(ks), gw = new Set(gs);
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      let n = 0;
      const w = (o, inGroup) => { for (const x of (o.dataObjects || [])) {
          const kids = (x.dataObjects || []).length;
          if (kids) { w(x, inGroup || gw.has(x.key)); continue; }
          if (want.has(x.key) ? x._value !== null : (inGroup && x._value === '')) { x._value = null; n++; }
      } };
      w({dataObjects: d.dataObjects}, false);
      return {unset: n}; })(%s, %s)""" % (json.dumps(sorted(set(keys))), json.dumps(list(groups)))) or {}


# ---------------------------------------------------------------- events
def fire(report, key: str, action: int, instance: int = 0) -> bool:
    """Tell the form a field raised `action` (for rules that listen to one event)."""
    return bool(report.page.evaluate("""((k, i, a) => {
      const dl = window.engine.dataLayer, d = dl.DataSets.get(window.engine.currentForm.formName);
      let f = null; const w = o => { for (const x of (o.dataObjects || [])) {
          if (x.key === k && (x.instance ?? 0) === i && !(x.dataObjects || []).length) f = x; w(x); } };
      w({dataObjects: d.dataObjects}); if (!f) return false;
      dl.NotifyObservers({action: a, changedItems: [f], changedKey: f.key}); return true;
    })(%s, %d, %d)""" % (json.dumps(key), instance, action)))


# ---------------------------------------------------------------- structure
def add_comparables(report, wanted: int, grid: str = "sales") -> int:
    """Grow a comparable grid to `wanted` columns (E-046).

    The method TOTAL's own "Add Comp #N" button and the grid's empty-column cell
    both call.  Never shrinks a grid.  Returns the number of columns after.
    `grid`: the CompManagers key -- "sales", "rentalprop" (rental properties
    RP<k>; a new 2-4 report may start with ONE column, 601 Euclid), "rentalunit",
    "grossrental".
    """
    home, render = {"sales": ("sales-comp", "sxs-section-key")}.get(grid, ("rental-information", "rental-information"))
    report.goto(home, settle=1.2)
    after = report.page.evaluate("""((n, g) => {
      const ds = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      const mgr = ds.CompManagers && ds.CompManagers.get(g);
      if (!mgr) return -1;
      while (mgr.Comps < n) mgr.AddComp(1, false);
      return mgr.Comps; })(%d, %s)""" % (wanted, json.dumps(grid)))
    if render != home:
        report.goto("site", settle=0.8)
    report.goto(render, settle=1.6)   # renders the new column
    return int(after)


def add_rows(report, section: str, button: str, count_key: str, wanted: int,
             settle: float = 1.0) -> int:
    """Click a visible guidance button until `count_key` has `wanted` leaves."""
    report.goto(section, settle=1.6)
    guard = 0

    def added(before: int) -> bool:
        # the row lands asynchronously: wait for the count to move before the
        # next click, or the loop overshoots (unit 3 got 6 levels for 2)
        end = time.time() + 4.0
        while time.time() < end:
            if count(report, count_key) > before:
                return True
            time.sleep(0.25)
        return False

    while count(report, count_key) < wanted and guard < wanted + 3:
        guard += 1
        before = count(report, count_key)
        if ui.click(report.page, ".button-guidance-add", button, 0, settle=settle):
            added(before)
            continue
        if ui.click(report.page, "button", button, 0, settle=settle):
            added(before)
            continue
        # The guidance panel shows a table's "+ Add ..." only while a cell of
        # that table has focus (as for exhibit rows, E-046): focus one, retry.
        ui.click(report.page, f'[fn="{count_key}"]', "", 0, settle=1.0)
        if not (ui.click(report.page, ".button-guidance-add", button, 0, settle=settle)
                or ui.click(report.page, "button", button, 0, settle=settle)):
            break
    return count(report, count_key)


def trim_rows(report, section: str, button: str, count_key: str, wanted: int,
              focus_key: str | None = None, protect: list[str] = (), settle: float = 1.2) -> int:
    """Remove BLANK trailing rows of a table until `count_key` has `wanted`.

    TOTAL's "- Remove Level" / "- Remove Room" act on the focused row and
    appear in the guidance panel only while a cell of that row has focus; a
    direct RemoveFieldDataGroup throws in the renderer (2026-10-01).  A row
    that holds a value is never removed -- the loop stops instead.

    `protect`: keys whose row counts must not change (CATALOG E-057: "- Remove
    Level" on a blank level also took unit 3's room rows, 7 -> 1).  The loop
    stops and raises the moment any of them drops.
    """
    report.goto(section, settle=1.4)
    focus_key = focus_key or count_key
    keep = {k: count(report, k) for k in protect}
    guard = 0
    while count(report, count_key) > wanted and guard < 30:
        lost = {k: (n, count(report, k)) for k, n in keep.items() if count(report, k) < n}
        if lost:
            raise RuntimeError(f"trim_rows stopped: protected rows were removed {lost}")
        guard += 1
        n = count(report, count_key)
        last = values(report, [count_key]).get(f"{count_key}#{n - 1}", "")
        if str(last).strip():
            break
        # focus the data's last row (index n-1), not the last drawn row: a
        # renderer error can leave a ghost row drawn after it
        if not ui.click(report.page, f'[fn="{focus_key}"]', "", n - 1, settle=1.0):
            break
        if not ui.click(report.page, ".button-guidance-remove", button, 0, settle=settle):
            break
    lost = {k: (n, count(report, k)) for k, n in keep.items() if count(report, k) < n}
    if lost:
        raise RuntimeError(f"trim_rows: protected rows were removed {lost}")
    return count(report, count_key)


def ensure_exhibit_rows(report, section: str, photo_field: str, desc_field: str,
                        wanted: int) -> int:
    """Exhibit rows appear only through the guidance panel of a focused table.

    Focus a cell of that section's exhibit table, then click the button that
    becomes visible.  Which cell and which label differ by section (E-046):
    description + "+ Add Exhibit" in Unit Interior / Dwelling Exterior,
    description + "Add Exhibit" in Site, caption + "+ Add Exhibit" in Vehicle
    Storage.
    """
    report.goto(section, settle=1.6)
    guard = 0
    while count(report, photo_field) < wanted and guard < wanted + 3:
        guard += 1
        added = False
        caption = (desc_field.replace("DESCRIPTION", "CAPTION") if desc_field.endswith("DESCRIPTION")
                   else desc_field[:-len("_DESC")] + "_CAPTION" if desc_field.endswith("_DESC") else desc_field)
        for cell in (desc_field, caption):
            ui.click(report.page, f'[fn="{cell}"]', "", 0, settle=1.0)
            if any(ui.click(report.page, ".button-guidance-add", t, 0, settle=1.8)
                   for t in ("+ Add Exhibit", "Add Exhibit")):
                added = True
                break
        if not added:
            break
    report.goto(section, settle=1.2)
    return count(report, photo_field)


def trim_exhibit_rows(report, section: str, photo_field: str, desc_field: str, wanted: int) -> int:
    """Remove trailing exhibit rows until `wanted` remain (E-069): focus the
    last row's description, then TOTAL's own "- Remove Exhibit" guidance
    button -- the reverse of ensure_exhibit_rows.  Stops if a click fails."""
    report.goto(section, settle=1.4)
    guard = 0
    while count(report, photo_field) > wanted and guard < 40:
        guard += 1
        n = count(report, photo_field)
        if not ui.click(report.page, f'[fn="{desc_field}"]', "", n - 1, settle=1.0):
            break
        if not ui.click(report.page, ".button-guidance-remove", "- Remove Exhibit", 0, settle=1.8):
            break
        if count(report, photo_field) >= n:
            break
    return count(report, photo_field)


def remove_row_group(report, group_key: str, instance: int = 0) -> dict:
    """Remove a repeatable row with the data set's own method (E-050).

    Used for the subject's listing-history row when the subject was not listed:
    its cells have no display rule and are always validated otherwise.  The
    section's own "+ Add ..." button re-creates it, so this is reversible.
    """
    return json.loads(report.page.evaluate("""((k, i) => {
      const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
      const before = (d.GetDataGroups(k) || []).length;
      d.RemoveFieldDataGroup(k, i);
      return JSON.stringify({before, after: (d.GetDataGroups(k) || []).length}); })(%s, %d)"""
                                           % (json.dumps(group_key), instance)))


def settle_neutral(report, section: str = "assignment") -> None:
    """Leave the form on a section that renders every party (E-035, UAD-1542):
    the Order section replaces the assignment's contact controls, and the
    exporter builds the party list from what is rendered."""
    report.goto(section, settle=1.2)
    time.sleep(0.4)
