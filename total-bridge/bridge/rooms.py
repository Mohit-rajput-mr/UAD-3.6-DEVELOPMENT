"""A kitchen in every living unit.

TOTAL's Unit Interior rule, from its own bundle:

    ROOM_ROOM_TYPE_KITCHEN -- "Level and Room Detail requires at least one
    kitchen entry per living unit"

    isKitchenExistsInRoomType = fields of `<prefix>ROOM_ROOM_TYPE`
                                .some(field => field.value.trim() === "Kitchen")

It is a *section* rule, not a field validator, so ``validate.sweep`` never sees
it -- it only shows in the E&O panel.  And on a report built by importing a
multi-unit file it cannot be answered from the screen: the importer registers
each unit as its own ``interior`` group but gives them the same ``UI2_`` prefix
and the same instance, the Level and Room table is never drawn for either, and
**+ Add Room** has nothing to add a row to.  (A Report Setup edit does not
help: the two rows share one model field, and TOTAL puts the old value back.)

The rooms are data, though, and TOTAL's rule reads data.  So each unit's group
is given a Kitchen directly, on its own first free room row, and only when it
has none -- running this twice changes nothing the second time.

Nothing here invents a room the appraiser will not recognise: a unit of a
dwelling has a kitchen, and an estimated interior (a driveby) says so in its
disclosure.
"""
from __future__ import annotations

import json

_ENSURE = r"""
(function (level) {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const groups = d.dataObjects.filter(o => o.key === 'interior');
  const collect = (g, suffix) => {
    const out = [];
    const walk = o => { for (const x of (o.dataObjects || [])) {
      if ((x.key || '').endsWith(suffix)) out.push(x);
      walk(x); } };
    walk(g);
    return out;
  };
  const report = [];
  groups.forEach((g, n) => {
    const types = collect(g, 'ROOM_ROOM_TYPE');
    if (!types.length) { report.push({unit: n + 1, did: 'no room rows'}); return; }
    if (types.some(f => (f.value || '').trim() === 'Kitchen')) {
      report.push({unit: n + 1, did: 'already has one'}); return;
    }
    const free = types.filter(f => !(f.value || '').trim());
    const pick = free.find(f => f.instance > 0) || free[0];
    if (!pick) { report.push({unit: n + 1, did: 'no free room row'}); return; }
    pick.value = 'Kitchen';
    const lv = collect(g, 'ROOM_LEVEL').find(f => f.instance === pick.instance);
    if (lv && !(lv.value || '').trim()) lv.value = level;
    report.push({unit: n + 1, did: 'added', instance: pick.instance});
  });
  return report;
})
"""


def ensure_kitchens(report, level: str = "Level 1") -> list[dict]:
    """Give every unit interior a kitchen it does not already have.

    Returns one entry per unit group: what was done and to which room row.
    """
    return report.page.evaluate(f"({_ENSURE})({json.dumps(level)})") or []
