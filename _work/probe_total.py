"""Read-only: what is TOTAL's UAD 3.6 form actually made of?"""
import sys
sys.path.insert(0, "_work")

import cdp

PROBE = r"""
(() => {
  const out = {url: location.href, title: document.title};
  out.angular = !!document.querySelector('[ng-version]');
  const ngv = document.querySelector('[ng-version]');
  out.ngVersion = ngv ? ngv.getAttribute('ng-version') : null;
  out.react = !!Object.keys(window).find(k => k.startsWith('__REACT'));

  const els = Array.from(document.querySelectorAll('input, select, textarea'));
  out.count = els.length;

  // Which attributes do these controls actually carry?  That decides how a
  // field can be addressed without clicking it.
  const attrFreq = {};
  for (const e of els) for (const a of e.attributes)
      attrFreq[a.name] = (attrFreq[a.name] || 0) + 1;
  out.attrFreq = Object.entries(attrFreq).sort((a, b) => b[1] - a[1]).slice(0, 25);

  out.sample = els.slice(0, 14).map(e => {
    const a = {};
    for (const at of e.attributes) a[at.name] = at.value.slice(0, 70);
    return {tag: e.tagName.toLowerCase(), type: e.type || '',
            value: (e.value || '').slice(0, 40), attrs: a};
  });
  return out;
})()
"""

for i, target in enumerate(cdp.pages()):
    print(f"\n===== page {i}: {target['url'][:70]}")
    page = cdp.open_form(i)
    try:
        info = page.evaluate(PROBE)
    except Exception as exc:
        print("  probe failed:", exc)
        page.close()
        continue
    print(f"  title    : {info['title']}")
    print(f"  angular  : {info['angular']}  ngVersion={info['ngVersion']}  react={info['react']}")
    print(f"  controls : {info['count']}")
    print("  attributes these controls carry:")
    for name, n in info["attrFreq"]:
        print(f"      {name:<26} {n}")
    print("  first controls:")
    for s in info["sample"]:
        keep = {k: v for k, v in s["attrs"].items() if k != "class"}
        print(f"      <{s['tag']} type={s['type']}> value={s['value']!r}")
        print(f"          {keep}")
    page.close()
