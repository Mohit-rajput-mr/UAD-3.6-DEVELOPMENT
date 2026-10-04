"""Driving a UAD 3.6 report inside TOTAL.

The form is jQuery 3.7.1 and binds ``input``/``change``/``blur``/``focus``
directly to each control.  Assigning a value without firing those events paints
it on screen and never reaches the report, so every write here goes through the
same events a typed edit raises, and every write is read back.
"""
from __future__ import annotations

import json
import re
import time

from . import cdp

_SCHEMA_LOCATION = re.compile(r'\s+xsi:(?:noNamespace)?[Ss]chemaLocation\s*=\s*"[^"]*"')


_XL = "http://www.w3.org/1999/xlink"
_RENTAL_ARC = "RENTAL_INFORMATION_IsComparableFor_RENTAL_INFORMATION"


def _ordinal_labels(root, etree) -> dict:
    """old label -> TOTAL's label, for every element TOTAL's importer reads by label.

    TOTAL's importer takes meaning from xlink labels in exactly these places
    (web engine 0.0.1.3848; knowledge/total/FINDINGS.md §7, CATALOG E-032/E-036):

      rental comparable -> subject unit   relationship target ends ``_I<unit>``
      a rental comparable's detail for a unit                 ends ``_U<unit>``
      data source -> comparable      target contains the role and ends ``_P<n>``
      data source -> subject unit area                        ends ``_P<unit>``

    So those elements get TOTAL's own labels -- ``PROPERTY_<Role>_P<n>``,
    ``PROPERTY_UNIT_AREA_SubjectProperty_P<u>``,
    ``RENTAL_INFORMATION_SubjectProperty_I<u>``,
    ``RENTAL_INFORMATION_RentalComparable_P<n>_U<u>`` -- and nothing else changes.
    """
    L = f"{{{_XL}}}label"
    local = lambda e: etree.QName(e).localname if isinstance(e.tag, str) else ""
    props = [p for p in root.iter() if local(p) == "PROPERTY"]
    subject = next((p for p in props if p.get("ValuationUseType") == "SubjectProperty"), None)
    rename: dict[str, str] = {}

    def ordinal(prop, role):
        for e in prop.iter():
            if local(e) == "PropertyOrdinalNumber" and (e.text or "").strip().isdigit():
                return int(e.text.strip())
        same = [p for p in props if p.get("ValuationUseType") == role]
        return same.index(prop) + 1

    comp_index = {}
    for prop in props:
        role = prop.get("ValuationUseType") or ""
        if not role or role == "SubjectProperty":
            continue
        n = ordinal(prop, role)
        comp_index[id(prop)] = n
        old = prop.get(L)
        if old:
            rename[old] = f"PROPERTY_{role}_P{n}"

    subject_unit_of = {}                      # subject RENTAL_INFORMATION label -> unit number
    if subject is not None:
        units = [u for u in subject.iter() if local(u) == "PROPERTY_UNIT"]
        for u, unit in enumerate(units, start=1):
            for e in unit.iter():
                old = e.get(L)
                if not old:
                    continue
                if local(e) == "PROPERTY_UNIT_AREA":
                    rename[old] = f"PROPERTY_UNIT_AREA_SubjectProperty_P{u}"
                elif local(e) == "RENTAL_INFORMATION":
                    rename[old] = f"RENTAL_INFORMATION_SubjectProperty_I{u}"
                    subject_unit_of[old] = u

    # a rental comparable's RENTAL_INFORMATION records: which subject unit each
    # is compared with comes from the relationships
    unit_for_detail = {}
    for rel in root.iter():
        if local(rel) != "RELATIONSHIP" or not (rel.get(f"{{{_XL}}}arcrole") or "").endswith(_RENTAL_ARC):
            continue
        to = rel.get(f"{{{_XL}}}to")
        if to in subject_unit_of:
            unit_for_detail[rel.get(f"{{{_XL}}}from")] = subject_unit_of[to]
    for prop in props:
        if prop.get("ValuationUseType") != "RentalComparable":
            continue
        n = comp_index.get(id(prop), 0)
        infos = [e for e in prop.iter() if local(e) == "RENTAL_INFORMATION" and e.get(L)]
        for k, e in enumerate(infos, start=1):
            u = unit_for_detail.get(e.get(L), k)
            rename[e.get(L)] = f"RENTAL_INFORMATION_RentalComparable_P{n}_U{u}"

    # never merge two elements into one label: drop any rename that collides
    taken = {e.get(L) for e in root.iter() if isinstance(e.tag, str) and e.get(L)} - set(rename)
    seen: dict[str, str] = {}
    for old, new in list(rename.items()):
        if new == old:
            del rename[old]
        elif new in taken or new in seen:
            del rename[old]
        else:
            seen[new] = old
    return rename


def _comparable_functional_issues(root, etree) -> int:
    """A-1 puts a sales comparable's functional issue on the PROPERTY
    (1800.0121: PROPERTY/FUNCTIONAL_ISSUES/FUNCTIONAL_ISSUE); TOTAL's sales-grid
    importer reads it only inside the comparable's dwelling improvement
    (IMPROVEMENT/FUNCTIONAL_ISSUES/FUNCTIONAL_ISSUE) and drops it otherwise
    (CATALOG E-045).  Give TOTAL a copy where it reads; the property-level
    original stays.  Returns how many comparables got one."""
    import copy
    ns = "{http://www.mismo.org/residential/2009/schemas}"
    done = 0
    for prop in root.iter(f"{ns}PROPERTY"):
        if prop.get("ValuationUseType") != "SalesComparable":
            continue
        issues = prop.find(f"{ns}FUNCTIONAL_ISSUES")
        dwellings = prop.findall(f"{ns}IMPROVEMENTS/{ns}IMPROVEMENT")
        if issues is None or not dwellings:
            continue
        if dwellings[0].find(f"{ns}FUNCTIONAL_ISSUES") is None:
            dwellings[0].append(copy.deepcopy(issues))
            done += 1
    return done


def prepare_for_total(xml: str) -> str:
    """The file as TOTAL's importer needs it, with nothing it means changed.

    1. no xsi:schemaLocation (CATALOG E-028);
    2. the xlink labels TOTAL's importer reads meaning from, in TOTAL's own
       convention (`_ordinal_labels`; CATALOG E-032, E-036).  A label is only an
       identifier: renaming it, and every reference to it, changes no element,
       value or relationship in the report (tests/test_prepare.py proves it on
       the twelve D-1 samples);
    3. a comparable's functional issue also where TOTAL's importer reads it
       (`_comparable_functional_issues`, CATALOG E-045) -- a copy, not a move.
    """
    xml = without_schema_location(xml)
    if "xlink:label" not in xml and "FUNCTIONAL_ISSUES" not in xml:
        return xml
    from lxml import etree
    try:
        root = etree.fromstring(xml.encode("utf-8"), etree.XMLParser(huge_tree=True, remove_blank_text=False))
    except etree.XMLSyntaxError:
        return xml
    copied = _comparable_functional_issues(root, etree)
    rename = _ordinal_labels(root, etree) if "xlink:label" in xml else {}
    if not rename and not copied:
        return xml
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        for attr in (f"{{{_XL}}}label", f"{{{_XL}}}from", f"{{{_XL}}}to"):
            v = el.get(attr)
            if v in rename:
                el.set(attr, rename[v])
    head = '<?xml version="1.0" encoding="utf-8"?>\n' if xml.lstrip().startswith("<?xml") else ""
    return head + etree.tostring(root, encoding="unicode")


def without_schema_location(xml: str) -> str:
    """The file without xsi:schemaLocation on its elements.

    TOTAL's importer builds each element's XPath from every ancestor's
    attributes and cannot resolve the ``xsi`` prefix, so with this optional
    hint present it silently skips dozens of values (zoning, ratings, parcel,
    commentaries...).  Removing it changes nothing a schema validator needs.
    knowledge/errors/CATALOG.md E-028.
    """
    return _SCHEMA_LOCATION.sub("", xml)

# --------------------------------------------------------------------- JS
_SET = r"""
function (fn, instance, value) {
  const sel = '[fn="' + fn + '"]' + (instance === null ? '' : '[instance="' + instance + '"]');
  const el = document.querySelector(sel);
  if (!el) return {ok: false, why: 'no such control'};
  const fire = names => names.forEach(n => el.dispatchEvent(new Event(n, {bubbles: true})));
  try {
    if (el.tagName === 'INPUT' && el.type === 'checkbox') {
      const want = value === true || value === 'X' || value === 'on' || value === '1' || value === 'Yes';
      if (el.checked !== want) { el.focus(); el.click(); }
      return {ok: true, got: el.checked ? 'X' : ''};
    }
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.focus();
      const proto = el.tagName === 'INPUT' ? HTMLInputElement : HTMLTextAreaElement;
      const setter = Object.getOwnPropertyDescriptor(proto.prototype, 'value').set;
      setter.call(el, value);
      fire(['input', 'change', 'blur']);
      return {ok: true, got: el.value};
    }
    if (el.isContentEditable) {
      el.focus();
      el.textContent = value;
      fire(['input', 'change', 'blur']);
      return {ok: true, got: (el.textContent || '').trim()};
    }
    return {ok: false, why: 'not writable: <' + el.tagName.toLowerCase() + '>'};
  } catch (e) { return {ok: false, why: String(e)}; }
}
"""

_READ_ALL = r"""
(() => {
  const out = {};
  for (const e of document.querySelectorAll('[fn]')) {
    const fn = e.getAttribute('fn');
    if (fn.startsWith('LABEL_')) continue;
    let v;
    if (e.tagName === 'INPUT' && e.type === 'checkbox') v = e.checked ? 'X' : '';
    else if (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') v = e.value || '';
    else v = (e.getAttribute('data-value') || e.textContent || '').trim();
    out[fn + '[' + (e.getAttribute('instance') || '0') + ']'] = v;
  }
  return out;
})()
"""

_DESCRIBE = r"""
(() => {
  const rows = [];
  for (const e of document.querySelectorAll('[fn]')) {
    const fn = e.getAttribute('fn');
    let kind;
    if (e.tagName === 'INPUT' && e.type === 'checkbox') kind = 'checkbox';
    else if (e.tagName === 'INPUT') kind = 'text';
    else if (e.tagName === 'TEXTAREA') kind = 'textarea';
    else if (e.tagName === 'IMG') kind = 'image';
    else if (e.isContentEditable) kind = 'editable';
    else kind = 'readonly';
    rows.push({fn: fn, kind: kind, fmid: e.getAttribute('fmid') || '',
               instance: e.getAttribute('instance') || '0'});
  }
  return rows;
})()
"""

# A pick list is not a <select>.  Clicking the control opens a floating panel of
# options; choosing one means clicking the option, not typing its text into the
# control.  Typing into it looks accepted and saves nothing -- which is exactly
# how ATTACHMENT_TYPE, PROPRIGHTSAPPR and SPECIAL_TAX_ASSESSMENTS came out
# empty from a fill that reported success.
_PICK = r"""
function (fn, instance, wanted) {
  const sel = '[fn="' + fn + '"]' + (instance === null ? '' : '[instance="' + instance + '"]');
  const el = document.querySelector(sel);
  if (!el) return Promise.resolve({ok: false, why: 'no such control'});
  const before = (el.getAttribute('data-value') || el.textContent || '').trim();
  const norm = t => (t || '').replace(/\s+/g, ' ').trim().toLowerCase();
  el.focus();
  el.click();
  return new Promise(resolve => setTimeout(() => {
    // Options are whatever became visible carrying exactly this text.  The
    // deepest such node is the option itself rather than its container.
    const shown = Array.from(document.querySelectorAll('li,label,span,div,a'))
      .filter(n => n.offsetParent !== null && n.children.length <= 2
                   && norm(n.textContent) === norm(wanted));
    if (!shown.length) {
      el.blur();
      return resolve({ok: false, why: 'not offered: ' + wanted, got: before});
    }
    shown[shown.length - 1].click();
    setTimeout(() => {
      el.blur();
      resolve({ok: true,
               got: (el.getAttribute('data-value') || el.textContent || '').trim()});
    }, 260);
  }, 380));
}
"""


class Report:
    """One UAD 3.6 report open in TOTAL."""

    def __init__(self, page: cdp.Page, name: str, signed: bool):
        self.page = page
        self.name = name
        self.signed = signed

    # ------------------------------------------------------------ attach
    @staticmethod
    def open_reports(host=cdp.DEFAULT_HOST, port=cdp.DEFAULT_PORT) -> list[dict]:
        """Every UAD 3.6 report TOTAL currently has loaded."""
        found = []
        for target in cdp.pages(host, port):
            page = cdp.Page(target["webSocketDebuggerUrl"])
            try:
                info = page.evaluate(
                    "(() => { const e = window.engine; return e && e.ReportInfo"
                    " ? {name: e.ReportInfo.Description,"
                    "    signed: e.IsSigned ? e.IsSigned() : null,"
                    "    form: e.ReportInfo.MajorFormKey} : null; })()")
            except Exception:
                info = None
            if info and info.get("name"):
                found.append({**info, "ws": target["webSocketDebuggerUrl"]})
            page.close()
        return found

    @classmethod
    def attach(cls, name: str | None = None, *, allow_signed: bool = False,
               host=cdp.DEFAULT_HOST, port=cdp.DEFAULT_PORT) -> "Report":
        reports = cls.open_reports(host, port)
        if not reports:
            raise SystemExit("no UAD 3.6 report is open in TOTAL")

        if name is None:
            writable = [r for r in reports if not r["signed"]]
            if len(writable) != 1:
                listing = "\n".join(
                    f"    {r['name']!r}{'  [signed]' if r['signed'] else ''}"
                    for r in reports)
                raise SystemExit(
                    "several reports are open -- name the one to use with "
                    f"--report:\n{listing}")
            chosen = writable[0]
        else:
            # An exact name wins: with "18 north" and "18 north test" both
            # open, asking for "18 north" means that one, not an ambiguity.
            exact = [r for r in reports if r["name"].lower() == name.lower()]
            matches = exact or [r for r in reports
                                if name.lower() in r["name"].lower()]
            if not matches:
                listing = "\n".join(f"    {r['name']!r}" for r in reports)
                raise SystemExit(f"no open report matches {name!r}:\n{listing}")
            if len(matches) > 1:
                listing = "\n".join(f"    {r['name']!r}" for r in matches)
                raise SystemExit(f"{name!r} matches more than one report:\n{listing}")
            chosen = matches[0]

        if chosen["signed"] and not allow_signed:
            raise SystemExit(
                f"{chosen['name']!r} is signed. A signed appraisal is a legal "
                "instrument; unsign it in TOTAL first if you mean to change it.")

        return cls(cdp.Page(chosen["ws"]), chosen["name"], bool(chosen["signed"]))

    # ------------------------------------------------------------ reading
    def render_all(self, settle: float = 2.5) -> None:
        """Re-render whatever section is on screen."""
        self.page.evaluate("window.engine.RefreshReport()")
        time.sleep(settle)

    def sections(self) -> list[str]:
        return self.page.evaluate("window.engine.GetAllSectionKeys()") or []

    def goto(self, section_key: str, settle: float = 1.6) -> None:
        """Bring one section into the page.

        Three calls, and all three are needed.  Setting the key alone only
        records it; ``UpdateSectionVisibility`` is what decides which section
        the renderer is allowed to build, and ``RefreshReport`` is what makes
        it build.  Miss the middle one and every section returns the same
        controls -- the form looks navigable and never moves.
        """
        # The key does not always stick (seen 2026-10-01 on a 3-unit report:
        # a focused cell's leave handler puts the previous section back), so
        # the move is verified and repeated -- a write or a click into the
        # section we *think* is open lands in the wrong unit otherwise.
        # First the way a person does it: TOTAL's own navigation item
        # (#nav-section-key-<key>), which runs every handler the engine expects.
        from . import ui
        if ui.click(self.page, f"#nav-section-key-{section_key}", "", 0, settle=settle) and \
                self.page.evaluate("window.engine.currentActiveSectionKey") == section_key:
            return
        for attempt in range(4):
            if attempt:
                self.page.evaluate("document.activeElement && document.activeElement.blur && document.activeElement.blur()")
            self.page.evaluate(
                f"window.engine.currentActiveSectionKey = {json.dumps(section_key)}")
            self.page.evaluate("window.engine.UpdateSectionVisibility()")
            self.page.evaluate("window.engine.RefreshReport()")
            time.sleep(settle if not attempt else max(settle, 1.0))
            if self.page.evaluate("window.engine.currentActiveSectionKey") == section_key:
                return

    def walk(self, settle: float = 1.6):
        """Every section in turn, yielding (key, controls).

        The section on screen when this started is put back afterwards.
        """
        start = self.page.evaluate("window.engine.currentActiveSectionKey")
        try:
            for key in self.sections():
                self.goto(key, settle)
                yield key, self.controls(), self.values()
        finally:
            if start:
                self.goto(start, 0.4)

    def controls(self) -> list[dict]:
        return self.page.evaluate(_DESCRIBE) or []

    def values(self) -> dict[str, str]:
        return self.page.evaluate(_READ_ALL) or {}

    def get(self, fn: str, instance: int | None = 0):
        return self.values().get(f"{fn}[{instance if instance is not None else 0}]")

    def mismo(self) -> str:
        """What TOTAL would deliver -- the evidence a write actually landed."""
        return self.page.evaluate(
            "window.engine.CreateAndReturnMismoXML()", await_promise=True) or ""

    # ------------------------------------------------------------ writing
    def set(self, fn: str, value, instance: int | None = 0) -> dict:
        if self.signed:
            raise RuntimeError("refusing to write to a signed report")
        inst = "null" if instance is None else json.dumps(str(instance))
        return self.page.evaluate(
            f"({_SET})({json.dumps(fn)}, {inst}, {json.dumps(str(value))})")

    def pick(self, fn: str, value, instance: int | None = 0) -> dict:
        """Choose a value from a field's own pick list."""
        if self.signed:
            raise RuntimeError("refusing to write to a signed report")
        inst = "null" if instance is None else json.dumps(str(instance))
        return self.page.evaluate(
            f"({_PICK})({json.dumps(fn)}, {inst}, {json.dumps(str(value))})",
            await_promise=True)

    def import_mismo(self, xml: str, mode: str = "replace") -> str:
        """Hand a whole MISMO file to TOTAL's own deserializer.

        Returns the engine's error message, or "" when it reports success.
        """
        if self.signed:
            raise RuntimeError("refusing to write to a signed report")
        xml = prepare_for_total(xml)
        fn = {"replace": "ImportMismoXml",
              "merge": "ImportMismoKeepExisting",
              "partial": "ImportMismoPartial"}[mode]
        self.page.evaluate("window.__bridgeXml = '';")
        step = 60_000
        for i in range(0, len(xml), step):
            self.page.evaluate(
                f"window.__bridgeXml += {json.dumps(xml[i:i + step])};")
        sent = self.page.evaluate("window.__bridgeXml.length")
        if sent != len(xml):
            raise RuntimeError(f"transfer incomplete: {sent} of {len(xml)}")
        try:
            return self.page.evaluate(
                f"window.engine.{fn}(window.__bridgeXml)", await_promise=True) or ""
        finally:
            self.page.evaluate("delete window.__bridgeXml;")

    def close(self):
        self.page.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
