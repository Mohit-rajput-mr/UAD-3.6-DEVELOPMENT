"""Every addressable field in the section TOTAL currently has rendered."""
import sys
sys.path.insert(0, "_work")

import cdp

FIELDS = r"""
(() => {
  const out = {};
  const els = Array.from(document.querySelectorAll('[fn]'));
  out.count = els.length;
  out.fields = els.map(e => ({
    fn: e.getAttribute('fn'),
    instance: e.getAttribute('instance'),
    tag: e.tagName.toLowerCase(),
    type: e.getAttribute('type') || '',
    dataValue: (e.getAttribute('data-value') || '').slice(0, 50),
    value: (e.value !== undefined ? String(e.value) : '').slice(0, 50),
    text: (e.textContent || '').trim().slice(0, 50),
    checked: e.checked === true,
    editable: e.isContentEditable === true,
  }));
  // Anything on window that looks like the app's own model or API?
  out.windowKeys = Object.keys(window).filter(k =>
      /uad|report|form|field|engine|app|model|store|data|alamode|cef/i.test(k)
  ).slice(0, 40);
  return out;
})()
"""

page = cdp.open_form(0)
info = page.evaluate(FIELDS)
print(f"{info['count']} elements carry an fn attribute\n")
for f in info["fields"]:
    ident = f"{f['fn']}[{f['instance']}]" if f["instance"] not in (None, "") else f["fn"]
    bits = [f"<{f['tag']}", f["type"]]
    if f["editable"]:
        bits.append("contenteditable")
    val = f["value"] or f["dataValue"] or f["text"]
    mark = "CHECKED" if f["checked"] else ""
    print(f"  {ident:<34} {' '.join(b for b in bits if b):<26} {mark:<8} {val!r}")

print("\nwindow keys that might be the app's own API:")
for k in info["windowKeys"]:
    print("   ", k)
page.close()
