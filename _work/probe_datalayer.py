"""How does a value actually reach TOTAL's report?

Painting text into a contenteditable div would look right and save nothing.
This finds the path a genuine edit takes, so the bridge can use the same one.
"""
import sys
sys.path.insert(0, "_work")

import cdp

PROBE = r"""
(() => {
  const members = (obj, depth = 3) => {
    if (!obj) return null;
    const seen = new Set();
    let o = obj;
    for (let d = 0; o && d < depth; d++) {
      for (const k of Object.getOwnPropertyNames(o)) {
        if (k === 'constructor') continue;
        let t = 'unknown';
        try { t = typeof obj[k]; } catch (e) { t = 'throws'; }
        seen.add(k + ':' + t);
      }
      o = Object.getPrototypeOf(o);
    }
    return Array.from(seen).sort();
  };

  const out = {};
  out.dataLayer = members(window.engine && window.engine.dataLayer);

  // The render controllers are what bind a DOM node to a data item.
  out.engineOwn = Object.getOwnPropertyNames(window.engine || {})
      .filter(k => /control|render|field|data|set|value|node/i.test(k)).sort();

  // Take one real editable field and see what is attached to it.
  const el = document.querySelector('[fn]:not([fn^="LABEL_"])');
  if (el) {
    out.sampleFn = el.getAttribute('fn');
    out.sampleTag = el.tagName;
    out.sampleAttrs = {};
    for (const a of el.attributes) out.sampleAttrs[a.name] = a.value.slice(0, 60);
    // Framework/controller handles hung off the element
    out.sampleKeys = Object.keys(el).slice(0, 30);
    const own = [];
    for (const k in el) if (!(k in HTMLElement.prototype) && !(k in Element.prototype)) own.push(k);
    out.sampleExtra = own.slice(0, 30);
  }
  return out;
})()
"""

page = cdp.open_form(1)
info = page.evaluate(PROBE)

print("=== engine.dataLayer members")
for m in (info.get("dataLayer") or [])[:50]:
    print("   ", m)

print("\n=== engine own members matching control/render/field/data/set/value/node")
for m in info.get("engineOwn", []):
    print("   ", m)

print(f"\n=== a sample field: {info.get('sampleFn')} <{info.get('sampleTag')}>")
print("    attrs:", info.get("sampleAttrs"))
print("    non-standard keys on the element:", info.get("sampleExtra"))
page.close()
