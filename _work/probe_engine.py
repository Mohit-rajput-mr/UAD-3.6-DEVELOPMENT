"""What is window.engine / window.CefConnector, and can it set a field?"""
import sys
sys.path.insert(0, "_work")

import cdp

PROBE = r"""
(() => {
  const describe = (obj, name) => {
    if (obj === undefined) return {name, present: false};
    const out = {name, present: true, type: typeof obj};
    const seen = new Set();
    let o = obj;
    for (let depth = 0; o && depth < 3; depth++) {
      for (const k of Object.getOwnPropertyNames(o)) {
        if (k === 'constructor') continue;
        let kind = 'unknown';
        try { kind = typeof obj[k]; } catch (e) { kind = 'throws'; }
        seen.add(k + ':' + kind);
      }
      o = Object.getPrototypeOf(o);
    }
    out.members = Array.from(seen).sort().slice(0, 60);
    return out;
  };
  return {
    engine: describe(window.engine, 'engine'),
    cef: describe(window.CefConnector, 'CefConnector'),
    cefSharp: describe(window.cefSharp, 'cefSharp'),
  };
})()
"""

page = cdp.open_form(0)
info = page.evaluate(PROBE)
for key in ("engine", "cef", "cefSharp"):
    d = info[key]
    print(f"\n===== window.{d['name']}  present={d['present']} type={d.get('type')}")
    for m in d.get("members", []):
        print("   ", m)
page.close()
