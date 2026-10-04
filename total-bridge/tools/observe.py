"""Record the conversation between WinTOTAL and the form while the appraiser works.

Read-only observation for questions the form's code cannot answer alone --
e.g. what WinTOTAL asks for before it lets a report be signed or zipped
(knowledge/total/FINDINGS.md, U4).  It wraps the form's two message channels
so each call is also written to a log, then passes the call through unchanged:

  WinTOTAL -> form   TotalFormsEngineConnector.ExecuteReportAction(action, ...)
                     (with what the form answered)
  form -> WinTOTAL   TotalFormsEngineConnector.FireEvent(event, ...)

Nothing is blocked, altered or re-ordered.  Arguments are recorded shortened
(signatures and photos are base64 blobs; only their length is kept).

    python tools/observe.py --report "<report>" --seconds 900 --out observe.json

Stop early with Ctrl+C; the log so far is written.  Reloading the report in
TOTAL removes the wrappers.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bridge.total import Report      # noqa: E402

_INSTALL = r"""(() => {
  if (window.__obs) return 'already';
  window.__obs = [];
  const shorten = v => {
    if (typeof v === 'string') return v.length > 300 ? `<${v.length} chars> ` + v.slice(0, 120) : v;
    try { const s = JSON.stringify(v); return s && s.length > 300 ? `<${s.length} chars json> ` + s.slice(0, 120) : v; }
    catch (e) { return String(v); }
  };
  const push = row => { if (window.__obs.length < 5000) window.__obs.push(Object.assign({t: Date.now()}, row)); };
  const find = () => {
    for (const k of Object.getOwnPropertyNames(window)) {
      const v = window[k];
      if (v && v.connector && typeof v.connector.ExecuteReportAction === 'function') return v.connector;
    }
    return window.engine && window.engine.connector;
  };
  const c = find();
  if (!c) return 'no connector';
  const proto = Object.getPrototypeOf(c);
  const origAct = proto.ExecuteReportAction, origFire = proto.FireEvent;
  proto.ExecuteReportAction = async function (...a) {
    const row = {dir: 'wintotal->form', action: a[0], args: a.slice(1).map(shorten)};
    push(row);
    const r = await origAct.apply(this, a);
    row.result = shorten(r);
    return r;
  };
  proto.FireEvent = function (...a) {
    push({dir: 'form->wintotal', event: a[0], args: a.slice(1).map(shorten)});
    return origFire.apply(this, a);
  };
  window.__obsRestore = () => { proto.ExecuteReportAction = origAct; proto.FireEvent = origFire; };
  return 'installed';
})()"""


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True)
    ap.add_argument("--seconds", type=int, default=900)
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    out = Path(a.out)
    with Report.attach(a.report, allow_signed=True) as r:
        print("watcher:", r.page.evaluate(_INSTALL), flush=True)
        end = time.time() + a.seconds
        log = []
        try:
            while time.time() < end:
                time.sleep(3)
                log = r.page.evaluate("window.__obs || []")
                out.write_text(json.dumps(log, indent=1, ensure_ascii=False), encoding="utf-8")
        except KeyboardInterrupt:
            pass
        finally:
            try:
                r.page.evaluate("window.__obsRestore && window.__obsRestore(); delete window.__obs; delete window.__obsRestore;")
            except Exception:
                pass
        print(f"{len(log)} calls recorded -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
