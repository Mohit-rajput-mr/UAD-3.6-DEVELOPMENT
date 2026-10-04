"""Read back what TOTAL currently holds, without changing anything."""
import sys
sys.path.insert(0, "_work")

import cdp

READ = r"""
(() => {
  const vals = {};
  for (const e of document.querySelectorAll('[fn]')) {
    const fn = e.getAttribute('fn');
    if (fn.startsWith('LABEL_')) continue;
    let v = '';
    if (e.tagName === 'INPUT' && e.type === 'checkbox') v = e.checked ? 'X' : '';
    else if (e.tagName === 'INPUT') v = e.value || '';
    else v = (e.getAttribute('data-value') || e.textContent || '').trim();
    const inst = e.getAttribute('instance') || '0';
    vals[`${fn}[${inst}]`] = v.slice(0, 44);
  }
  return {section: window.engine.GetActiveSectionKeyForMode
                   ? window.engine.GetActiveSectionKeyForMode() : '?',
          filled: Object.entries(vals).filter(([k, v]) => v !== '').length,
          total: Object.keys(vals).length,
          vals};
})()
"""

page = cdp.open_form(0)
info = page.evaluate(READ)
print(f"active section : {info['section']}")
print(f"fields filled  : {info['filled']} of {info['total']}\n")
for k, v in info["vals"].items():
    if v:
        print(f"  {k:<36} {v!r}")
page.close()
