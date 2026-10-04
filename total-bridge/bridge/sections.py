"""TOTAL's section manager, read and written as data.

Some of what the delivery carries is not in the data layer at all.  A
structure's identifier is the clearest case: the code that writes the MISMO
document reads it off the *section*, not off a field --

    this.commonReportInfo.LivingUnitExcludingADUCount > 1 && sectionIdentifier?.length > 0
        && (structureDetail.StructureIdentifier = sectionIdentifier)

-- so ``DE1_SECTION_DESCRIPTION`` can hold a value all day and
``StructureIdentifier`` never appears, and H-1 UAD1091 keeps asking for it.

The section manager is a module of TOTAL's own bundle.  This asks the bundle's
own loader for it, which is how TOTAL's code gets it too: nothing is patched,
nothing is bypassed, and every value written here is one the section panel can
write itself.
"""
from __future__ import annotations

import json

#: Capture the bundle's module loader by registering an empty chunk -- the
#: documented shape for a webpack runtime, and the only way in from outside a
#: module.  It is cached on the window so a session pays for it once.
_LOADER = r"""(() => {
  if (window.__uadReq) return true;
  const name = Object.keys(window).find(k => /^webpackChunk/.test(k));
  if (!name) return false;
  try {
    window[name].push([['uad-bridge'], {}, req => { window.__uadReq = req; }]);
  } catch (e) { return false; }
  return !!window.__uadReq;
})()"""

#: The manager is whichever export owns GetSections.  Found by asking, not by
#: hard-coding a module number: a bundle renumbers on every build.
_FIND = r"""(() => {
  const req = window.__uadReq;
  if (!req) return null;
  if (window.__uadSectionManager) return true;
  for (const id of Object.keys(req.m || {})) {
    let mod;
    try { mod = req(id); } catch (e) { continue; }
    if (!mod) continue;
    for (const key of Object.keys(mod)) {
      const value = mod[key];
      if (value && typeof value.GetSections === 'function') {
        window.__uadSectionManager = value;
        return true;
      }
    }
  }
  return false;
})()"""


def manager(report) -> bool:
    """Make TOTAL's section manager reachable.  True when it is."""
    if not report.page.evaluate(_LOADER):
        raise RuntimeError("no webpack loader on the page")
    if not report.page.evaluate(_FIND):
        raise RuntimeError("no section manager in the bundle")
    return True


_READ = r"""((key) => {
  const list = window.__uadSectionManager.GetSections(key) || [];
  return list.map(s => ({
    identifier: s.SectionIdentifier ?? '',
    caption: s.sectionCaption ?? '',
    description: s.Description ?? '',
    instance: s.sectionInstance ?? s.SectionInstance ?? 0,
    guid: String(s.sectionGuid || s.SectionGuid || '')
  }));
})"""


def read(report, key: str) -> list[dict]:
    """Every section TOTAL holds under that key, as plain data."""
    manager(report)
    return report.page.evaluate(f"({_READ})({json.dumps(key)})") or []


_SET = r"""((args) => {
  const list = window.__uadSectionManager.GetSections(args.key) || [];
  const done = [];
  for (const s of list) {
    const instance = s.sectionInstance ?? s.SectionInstance ?? 0;
    if (args.instance != null && instance !== args.instance) continue;
    s.SectionIdentifier = args.value;
    done.push({instance, identifier: s.SectionIdentifier});
  }
  return done;
})"""


def set_identifier(report, key: str, value: str, instance: int | None = None) -> list:
    """Name a structure or unit, as the Units and Structures panel does.

    H-1 asks for a structure identifier once a structure holds more than one
    living unit (UAD1091), and for a unit identifier on each unit.
    """
    manager(report)
    args = {"key": key, "value": value, "instance": instance}
    return report.page.evaluate(f"({_SET})({json.dumps(args)})") or []
