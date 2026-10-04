"""Attach to TOTAL's embedded Chromium (CefSharp) over the DevTools protocol.

TOTAL's UAD 3.6 form is a web app (https://uadwebengine.alamode.com) hosted in
CefSharp, and the host exposes CDP on 127.0.0.1:8088.  Attaching lets the form
be read and filled directly instead of through screenshots and pixel clicks.

Read-only here: this only reports what the page is made of.
"""
import sys

from playwright.sync_api import sync_playwright

CDP = "http://127.0.0.1:8088"

PROBE = """
() => {
  const out = {url: location.href, title: document.title};
  // What framework is driving this?
  out.react = !!document.querySelector('[data-reactroot]') ||
              !!Object.keys(window).find(k => k.startsWith('__REACT'));
  out.angular = !!window.ng || !!document.querySelector('[ng-version]');
  out.vue = !!window.__VUE__;
  const ngv = document.querySelector('[ng-version]');
  if (ngv) out.ngVersion = ngv.getAttribute('ng-version');

  const inputs = Array.from(document.querySelectorAll('input, select, textarea'));
  out.counts = {total: inputs.length,
                text: inputs.filter(e => e.tagName === 'INPUT').length,
                select: inputs.filter(e => e.tagName === 'SELECT').length,
                textarea: inputs.filter(e => e.tagName === 'TEXTAREA').length};

  // A sample of fields with whatever identifying attributes they carry.
  out.sample = inputs.slice(0, 25).map(e => {
    const a = {};
    for (const at of e.attributes) a[at.name] = at.value.slice(0, 60);
    return {tag: e.tagName, value: (e.value || '').slice(0, 40), attrs: a};
  });
  return out;
}
"""


def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP)
        print(f"connected: {len(browser.contexts)} context(s)")
        for ci, ctx in enumerate(browser.contexts):
            for pi, page in enumerate(ctx.pages):
                print(f"\n--- context {ci} page {pi}: {page.url[:70]}")
                try:
                    info = page.evaluate(PROBE)
                except Exception as exc:
                    print(f"    evaluate failed: {exc}")
                    continue
                print(f"    title   : {info['title']}")
                print(f"    react={info['react']} angular={info['angular']} "
                      f"vue={info['vue']} ngVersion={info.get('ngVersion')}")
                print(f"    controls: {info['counts']}")
                for s in info["sample"][:12]:
                    keep = {k: v for k, v in s["attrs"].items()
                            if k in ("id", "name", "formcontrolname", "class",
                                     "type", "placeholder", "aria-label", "data-testid")}
                    print(f"      <{s['tag'].lower()}> value={s['value']!r}")
                    print(f"          {keep}")
        browser.close()


if __name__ == "__main__":
    sys.exit(main())
