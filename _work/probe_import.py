"""Read the import functions' source before calling any of them."""
import sys
sys.path.insert(0, "_work")

import cdp

NAMES = ["ImportMismoXml", "ImportMismoPartial", "ImportMismoKeepExisting",
         "ImportMismoAnalytics", "OpenReportXml", "LoadData",
         "CreateAndReturnMismoXML", "GetAllSectionKeys", "GetSectionCounts"]

SRC = """
(() => {
  const out = {};
  for (const n of %s) {
    try {
      const f = window.engine[n];
      out[n] = (typeof f === 'function')
          ? {args: f.length, src: f.toString().slice(0, 700)}
          : {args: null, src: 'not a function: ' + typeof f};
    } catch (e) { out[n] = {args: null, src: 'error: ' + e.message}; }
  }
  try { out['_cef_import'] = Object.getOwnPropertyNames(window.CefConnector)
        .filter(k => /import|xml|load|open/i.test(k)); } catch (e) {}
  return out;
})()
""" % (str(NAMES).replace("'", '"'),)

page = cdp.open_form(0)
info = page.evaluate(SRC)
for name in NAMES:
    d = info.get(name, {})
    print(f"\n===== engine.{name}  (arity {d.get('args')})")
    print(d.get("src", "")[:700])
print("\n===== CefConnector members matching import/xml/load/open:")
print(info.get("_cef_import"))
page.close()
