"""Is `fmid` the UAD 3.6 Report Field ID, and how is a field wired for input?"""
import sys
sys.path.insert(0, "_work")

import cdp

PROBE = r"""
(() => {
  const out = {};
  const els = Array.from(document.querySelectorAll('[fn]'))
      .filter(e => !e.getAttribute('fn').startsWith('LABEL_'));
  out.total = els.length;
  out.withFmid = els.filter(e => e.getAttribute('fmid')).length;
  out.fields = els.map(e => ({
    fn: e.getAttribute('fn'),
    fmid: e.getAttribute('fmid') || '',
    instance: e.getAttribute('instance') || '',
    tag: e.tagName.toLowerCase(),
    type: e.getAttribute('type') || '',
    editable: e.isContentEditable === true,
  }));

  // How is a field wired?  jQuery keeps its handlers where we can read them.
  const jq = window.jQuery || window.$;
  out.jquery = jq ? (jq.fn && jq.fn.jquery) : null;
  const sample = els.find(e => e.isContentEditable);
  if (sample && jq && jq._data) {
    const ev = jq._data(sample, 'events') || {};
    out.sampleFn = sample.getAttribute('fn');
    out.handlers = Object.keys(ev).map(k => `${k} x${ev[k].length}`);
  }
  // Are handlers instead delegated from an ancestor?
  if (jq && jq._data) {
    const delegated = [];
    let node = sample ? sample.parentElement : null;
    for (let i = 0; node && i < 8; i++, node = node.parentElement) {
      const ev = jq._data(node, 'events') || {};
      const keys = Object.keys(ev);
      if (keys.length) delegated.push(`${node.tagName}.${(node.className||'').toString().slice(0,26)} -> ${keys.join(',')}`);
    }
    out.delegated = delegated;
  }
  return out;
})()
"""

page = cdp.open_form(1)
info = page.evaluate(PROBE)
print(f"fields: {info['total']}   carrying fmid: {info['withFmid']}")
print(f"jQuery: {info.get('jquery')}")
print(f"\nhandlers bound directly to {info.get('sampleFn')}: {info.get('handlers')}")
print("delegated from ancestors:")
for d in info.get("delegated", []):
    print("   ", d)
print("\nfn -> fmid:")
for f in info["fields"]:
    kind = "contenteditable" if f["editable"] else (f["type"] or f["tag"])
    print(f"   {f['fn']:<30} fmid={f['fmid']:<12} inst={f['instance']:<3} {kind}")
page.close()
