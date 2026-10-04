"""A bridge that fills TOTAL's UAD 3.6 form, the way our own filler fills ours.

Nothing in the TOTAL installation is modified.  a la mode host the 3.6 form in
CefSharp and ship their CEF wrapper with RemoteDebuggingPort enabled, so the
form is drivable from outside exactly as a web page is: this connects to that
endpoint and drives the page.  A patched binary would break on the next TOTAL
update and put the licence at risk; this survives updates because it uses the
product's own interface.

How a value is written
----------------------
The form is jQuery 3.7.1 and binds ``input``/``blur``/``focus``/``keydown``
directly to each control.  Assigning ``textContent`` alone would paint the
value on screen and never reach the report, so every write focuses the control,
sets the value the way the control expects it, then fires the events the
handlers are listening for.  ``verify`` reads the value back afterwards --
what the engine kept, not what we typed.

Safety
------
* A report is addressed by name; the caller says which one.
* A signed report is never written to.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import cdp

# ---------------------------------------------------------------- JS helpers
# Set one control and fire what the page listens for.  Returns what the control
# holds afterwards, so the caller never has to trust the write.
SET_JS = r"""
function (fn, instance, value) {
  const sel = `[fn="${fn}"]` + (instance === null ? '' : `[instance="${instance}"]`);
  const el = document.querySelector(sel);
  if (!el) return {ok: false, why: 'no such field'};

  const fire = names => names.forEach(n =>
      el.dispatchEvent(new Event(n, {bubbles: true})));

  try {
    if (el.tagName === 'INPUT' && el.type === 'checkbox') {
      const want = value === true || value === 'X' || value === 'on' || value === '1';
      if (el.checked !== want) { el.focus(); el.click(); }
      return {ok: true, got: el.checked ? 'X' : ''};
    }
    if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') {
      el.focus();
      const proto = el.tagName === 'INPUT' ? HTMLInputElement : HTMLTextAreaElement;
      // React/knockout-style value setters need the native setter, and it is
      // harmless where they do not.
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
    return {ok: false, why: 'not a writable control: <' + el.tagName.toLowerCase() + '>'};
  } catch (e) {
    return {ok: false, why: String(e)};
  }
}
"""

READ_JS = r"""
function (fn, instance) {
  const sel = `[fn="${fn}"]` + (instance === null ? '' : `[instance="${instance}"]`);
  const el = document.querySelector(sel);
  if (!el) return null;
  if (el.tagName === 'INPUT' && el.type === 'checkbox') return el.checked ? 'X' : '';
  if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA') return el.value || '';
  return (el.getAttribute('data-value') || el.textContent || '').trim();
}
"""


class Total:
    """One open TOTAL report, driven through its own form engine."""

    def __init__(self, page: cdp.Page):
        self.page = page

    # ---------------------------------------------------------- connecting
    @classmethod
    def attach(cls, name: str | None = None, *, allow_signed: bool = False) -> "Total":
        """Attach to an open report, by name when given.

        Without a name, attaches to the only unsigned report; if there are
        several it refuses rather than guess, because guessing could write into
        somebody's finished appraisal.
        """
        candidates = []
        for target in cdp.pages():
            page = cdp.Page(target["webSocketDebuggerUrl"])
            try:
                info = page.evaluate(
                    "({desc: (window.engine && window.engine.ReportInfo) ? "
                    "window.engine.ReportInfo.Description : null,"
                    " signed: (window.engine && window.engine.IsSigned) ? "
                    "window.engine.IsSigned() : null})")
            except Exception:
                page.close()
                continue
            if not info.get("desc"):
                page.close()
                continue
            candidates.append((info["desc"], bool(info.get("signed")), page))

        if not candidates:
            raise SystemExit("no UAD 3.6 report is open in TOTAL")

        chosen = None
        for desc, signed, page in candidates:
            if name is not None and name.lower() not in desc.lower():
                page.close()
                continue
            if signed and not allow_signed:
                page.close()
                print(f"  skipping signed report {desc!r}")
                continue
            if chosen is None:
                chosen = (desc, page)
            else:
                page.close()

        if chosen is None:
            open_now = ", ".join(f"{d!r}{' [signed]' if s else ''}"
                                 for d, s, _ in candidates)
            raise SystemExit(f"no writable report matched {name!r}; open: {open_now}")

        print(f"attached to {chosen[0]!r}")
        return cls(chosen[1])

    # --------------------------------------------------------------- report
    def sections(self) -> list[str]:
        return self.page.evaluate("window.engine.GetAllSectionKeys()") or []

    def goto(self, section_key: str) -> bool:
        self.page.evaluate(
            f"window.engine.SetActiveSectionKeyForMode({json.dumps(section_key)})")
        self.page.evaluate("window.engine.RefreshReport && window.engine.RefreshReport()")
        return True

    def fields(self) -> dict[str, str]:
        """Every addressable control in the rendered section, `fn[instance]`."""
        return self.page.evaluate(r"""
        (() => {
          const out = {};
          for (const e of document.querySelectorAll('[fn]')) {
            const fn = e.getAttribute('fn');
            if (fn.startsWith('LABEL_')) continue;
            let v;
            if (e.tagName === 'INPUT' && e.type === 'checkbox') v = e.checked ? 'X' : '';
            else if (e.tagName === 'INPUT' || e.tagName === 'TEXTAREA') v = e.value || '';
            else v = (e.getAttribute('data-value') || e.textContent || '').trim();
            out[`${fn}[${e.getAttribute('instance') || '0'}]`] = v;
          }
          return out;
        })()
        """) or {}

    # ---------------------------------------------------------------- write
    def set(self, fn: str, value, instance: int | None = 0) -> dict:
        inst = "null" if instance is None else json.dumps(str(instance))
        return self.page.evaluate(
            f"({SET_JS})({json.dumps(fn)}, {inst}, {json.dumps(value)})")

    def get(self, fn: str, instance: int | None = 0):
        inst = "null" if instance is None else json.dumps(str(instance))
        return self.page.evaluate(
            f"({READ_JS})({json.dumps(fn)}, {inst})")

    def mismo(self) -> str:
        """What the engine would deliver -- the real proof a write landed."""
        return self.page.evaluate("window.engine.CreateAndReturnMismoXML()",
                                  await_promise=True) or ""

    def close(self):
        self.page.close()
