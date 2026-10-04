"""A heads-up display inside TOTAL, so it is obvious the bridge is attached.

A terminal-styled glass panel in the top right corner of the form's own page.
It reports which report the bridge is looking at, whether that report can be
written to, and it carries the import the product's menus do not: choose a UAD
3.6 file and the page hands it to TOTAL's own deserializer.

That import runs entirely in the page.  Once the panel is installed nothing
outside TOTAL has to be running for it to work, which is the difference between
a tool you have to remember to start and a feature of the application.

Red is the bridge being attached and able to act.  Amber is a report it will
not touch -- signed, and therefore somebody's legal instrument.  That is the
one piece of state worth reading across the room, so it drives the whole
palette rather than sitting in a word somewhere.

Three things the panel is careful about:

* **It does not move the form.**  Fixed and out of the flow -- a form whose
  fields have all shifted is worse than no panel at all.  It sits in the
  corner, can be dragged, and collapses to a pill.
* **It re-installs itself.**  The form rebuilds its DOM whenever a section
  changes, which would take the panel with it; a MutationObserver puts it back.
* **It never offers to write to a signed report.**  The import is disabled, the
  panel goes amber, and the reason is on it.

Closing a report and opening another gives TOTAL a new page, and a panel
installed in the old one goes with it.  ``watch`` exists for that: it keeps
looking, and puts the panel on each report as it opens.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

PANEL_ID = "uad36-bridge-hud"

# One self-contained installer.  It returns a summary so the caller can report
# what it found rather than assume it worked.  Literal percent signs are
# doubled: this string is interpolated.
_INSTALL = r"""
(() => {
  const ID = "%(id)s";
  const VERSION = "%(version)s";
  if (window.__uad36Hud && window.__uad36Hud.version === VERSION) {
    window.__uad36Hud.refresh(); return {already: true};
  }
  // A panel from other code (an older bridge) is replaced, never reused: its
  // handlers are that code's -- an old import button once did a bare import
  // (CATALOG E-043).
  if (window.__uad36Hud) { try { window.__uad36Hud.remove(); } catch (err) {} delete window.__uad36Hud; }

  // An earlier panel can outlive its own bookkeeping: the page reloads, the
  // handle on window goes with it, and the node and its timer are left behind
  // still rewriting the display.  Clear anything wearing this id before
  // installing, or two builds fight over the same text.
  document.querySelectorAll("#" + ID + ", #" + ID + "-css")
          .forEach(n => n.remove());

  const css = `
  #${ID}{position:fixed;top:14px;right:16px;z-index:2147483600;width:306px;
    font:12px/1.5 "Cascadia Mono","Cascadia Code","JetBrains Mono","Fira Code",
      Consolas,"Courier New",monospace;
    color:#ffc2c8;background:rgba(26,26,30,.38);
    -webkit-backdrop-filter:blur(26px) saturate(150%%);
    backdrop-filter:blur(26px) saturate(150%%);
    border:1px solid rgba(255,43,61,.34);border-radius:4px;
    box-shadow:0 0 0 1px rgba(0,0,0,.6),0 10px 34px rgba(0,0,0,.66),
               0 0 26px rgba(255,43,61,.14),
               inset 0 1px 0 rgba(255,255,255,.10);
    padding:0;overflow:hidden;-webkit-user-select:none;user-select:none;
    transition:width .16s linear}


  #${ID} .hd{display:flex;align-items:center;gap:8px;cursor:grab;
    padding:7px 10px;border-bottom:1px solid rgba(255,43,61,.22);
    background:linear-gradient(180deg,rgba(255,43,61,.10),rgba(255,43,61,.02))}
  #${ID} .hd:active{cursor:grabbing}
  #${ID} .led{width:8px;height:8px;flex:none;border-radius:1px;
    background:#ff2b3d;box-shadow:0 0 10px #ff2b3d,0 0 3px #ff2b3d;
    animation:${ID}-pulse 1.9s ease-in-out infinite}
  #${ID} .ttl{flex:1 1 auto;font-size:11px;font-weight:700;letter-spacing:2px;
    text-transform:uppercase;color:#ffc9cf;white-space:nowrap;
    text-shadow:0 0 9px rgba(255,43,61,.55)}
  #${ID} .ic{width:20px;height:20px;flex:none;cursor:pointer;
    border:1px solid rgba(255,43,61,.3);border-radius:2px;color:#ff8f9b;
    background:transparent;font:700 12px/1 inherit}
  #${ID} .ic:hover{color:#1b0206;background:#ff2b3d;border-color:#ff2b3d}

  #${ID} .body{padding:9px 10px 0;display:flex;flex-direction:column;gap:3px}
  #${ID} .row{display:flex;align-items:baseline;gap:8px;padding:4px 7px;border-radius:3px;background:rgba(0,0,0,.22)}
  #${ID} .k{flex:none;width:66px;font-size:10px;letter-spacing:1.4px;
    text-transform:uppercase;color:#b0606a}
  #${ID} .k::before{content:"> ";color:#8d4650}
  #${ID} .v{flex:1 1 auto;min-width:0;font-size:12px;font-weight:700;
    color:#ffe3e6;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

  #${ID} .go{margin:10px 10px 0;width:calc(100%% - 20px);cursor:pointer;
    border:1px solid #ff2b3d;border-radius:2px;padding:8px 10px;
    font:700 11.5px/1 inherit;letter-spacing:1.6px;text-transform:uppercase;
    color:#ff2b3d;background:rgba(255,43,61,.07);
    text-shadow:0 0 8px rgba(255,43,61,.5)}
  #${ID} .go:hover{color:#1b0206;background:#ff2b3d;text-shadow:none;
    box-shadow:0 0 18px rgba(255,43,61,.5)}
  #${ID} .go[disabled]{cursor:not-allowed;color:#ffb02e;border-color:#ffb02e;
    background:rgba(255,176,46,.08);text-shadow:0 0 8px rgba(255,176,46,.45)}

  #${ID} .bar{margin:9px 10px 0;height:2px;background:rgba(255,43,61,.12);
    overflow:hidden;display:none}
  #${ID} .bar.on{display:block}
  #${ID} .bar i{display:block;height:100%%;width:34%%;background:#ff2b3d;
    box-shadow:0 0 10px #ff2b3d;animation:${ID}-slide 1s linear infinite}

  #${ID} .msg{padding:8px 10px 10px;font-size:11px;line-height:1.45;
    color:#b0606a;min-height:1.45em;word-break:break-word;max-height:4.4em;
    overflow:hidden}
  #${ID} .msg::before{content:"$ ";color:#8d4650}
  #${ID} .msg.ok{color:#fff;text-shadow:0 0 10px rgba(255,43,61,.75)}
  #${ID} .msg.bad{color:#ffb02e;text-shadow:0 0 8px rgba(255,176,46,.5)}

  /* locked: the report is signed, and the panel says so in one colour */
  #${ID}.lock{color:#ffeccd;border-color:rgba(255,176,46,.44);
    box-shadow:0 0 0 1px rgba(0,0,0,.6),0 10px 34px rgba(0,0,0,.66),
               0 0 26px rgba(255,176,46,.16),
               inset 0 1px 0 rgba(255,255,255,.10)}
  #${ID}.lock .hd{border-bottom-color:rgba(255,176,46,.26);
    background:linear-gradient(180deg,rgba(255,176,46,.12),rgba(255,176,46,.02))}
  #${ID}.lock .led{background:#ffb02e;box-shadow:0 0 10px #ffb02e}
  #${ID}.lock .ttl{color:#ffdca8;text-shadow:0 0 9px rgba(255,176,46,.55)}
  #${ID}.lock .k{color:#a87c3a} #${ID}.lock .k::before{color:#8a6430}
  #${ID}.lock .v{color:#fff2de}
  #${ID}.lock .ic{color:#ffc86e;border-color:rgba(255,176,46,.34)}
  #${ID}.lock .ic:hover{color:#1a1202;background:#ffb02e;border-color:#ffb02e}

  #${ID}.min{width:auto}
  #${ID}.min .body,#${ID}.min .go,#${ID}.min .msg,#${ID}.min .bar{display:none}
  #${ID}.min .hd{border-bottom:0}

  #${ID} .dg{display:none;max-height:260px;overflow:auto;margin:6px 10px 2px;
    border-top:1px solid rgba(255,43,61,.22);padding-top:4px}
  #${ID} .dg.on{display:block}
  #${ID} .dh{color:#ffc2c8;opacity:.8;margin-bottom:3px}
  #${ID} .di{cursor:pointer;padding:1px 5px;margin:1px 0;border-left:2px solid #6a6a78;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  #${ID} .di:hover{background:rgba(255,43,61,.12)}
  #${ID} .di.fatal,#${ID} .di.severe{border-color:#ff2b3d}
  #${ID} .di.warning{border-color:#ffb020}
  #${ID} .di.nofield{cursor:default;opacity:.75}
  #${ID} .min .dg{display:none}
  .${ID}-hl{outline:2px solid #ff2b3d !important;outline-offset:2px}
  @keyframes ${ID}-pulse{0%%,100%%{opacity:1}50%%{opacity:.35}}
  @keyframes ${ID}-slide{0%%{margin-left:-34%%}100%%{margin-left:100%%}}
  @media (prefers-reduced-motion:reduce){
    #${ID},#${ID} .led,#${ID} .bar i{transition:none;animation:none}}
  `;
  const style = document.createElement("style");
  style.id = ID + "-css";
  style.textContent = css;
  document.head.appendChild(style);

  const el = document.createElement("div");
  el.id = ID;
  el.innerHTML = `
    <div class="hd" id="${ID}-hd">
      <span class="led" id="${ID}-led"></span>
      <span class="ttl" id="${ID}-ttl">UAD36://BRIDGE</span>
      <button class="ic" id="${ID}-min" title="Collapse">&minus;</button>
    </div>
    <div class="body">
      <div class="row"><span class="k">target</span>
        <span class="v" id="${ID}-name">scanning</span></div>
      <div class="row"><span class="k">access</span>
        <span class="v" id="${ID}-state">--</span></div>
      <div class="row"><span class="k">report</span>
        <span class="v" id="${ID}-kind">--</span></div>
      <div class="row"><span class="k">config</span>
        <span class="v" id="${ID}-cfg">--</span></div>
      <div class="row"><span class="k">fields</span>
        <span class="v" id="${ID}-fields">--</span></div>
    </div>
    <div class="dg" id="${ID}-dg"></div>
    <button class="go" id="${ID}-go">&gt;&gt; inject uad 3.6 xml</button>
    <div class="bar" id="${ID}-bar"><i></i></div>
    <div class="msg" id="${ID}-msg">link established</div>
    <input type="file" accept=".xml,text/xml,application/xml" id="${ID}-file" hidden>
  `;
  document.body.appendChild(el);

  // Held by reference, not looked up by id on every tick.  A timer left over
  // from an earlier install resolves the same ids and would happily rewrite
  // this panel's text with its own older wording; holding the nodes means a
  // stale timer can only touch the nodes it was born with, which are detached.
  const own = {};
  for (const node of el.querySelectorAll("[id]")) {
    own[node.id.slice(ID.length)] = node;
  }
  const $ = s => own[s] || document.getElementById(ID + s);
  const busy = on => { $("-bar").className = "bar" + (on ? " on" : ""); };
  const say = (text, kind) => {
    const m = $("-msg");
    m.textContent = text || "";
    m.className = "msg" + (kind ? " " + kind : "");
  };

  const state = () => {
    const e = window.engine;
    if (!e || !e.ReportInfo) return null;
    let signed = null;
    try { signed = e.IsSigned ? e.IsSigned() : null; } catch (err) {}
    return {name: e.ReportInfo.Description || "(unnamed)",
            form: e.ReportInfo.MajorFormKey || "", signed: !!signed,
            title: (e.currentForm && e.currentForm.title) || "",
            id: e.ReportInfo.Proj2000ID || ""};
  };

  const refresh = () => {
    const s = state();
    if (!s) {
      $("-name").textContent = "no report";
      $("-state").textContent = "offline";
      return;
    }
    el.classList.toggle("lock", s.signed);
    $("-ttl").textContent = s.signed ? "UAD36://LOCKED" : "UAD36://BRIDGE";
    $("-name").textContent = s.name;
    $("-name").title = s.name + "   " + s.form;
    $("-state").textContent = s.signed ? "DENIED / SIGNED" : "GRANTED / RW";
    $("-fields").textContent =
        document.querySelectorAll("[fn]:not([fn^=LABEL_])").length;
    // what kind of report this is: pushed by the bridge's detection
    // (bridge/detect.py) for this report only; until then, the form's own name
    const c = window.__uad36HudCtx;
    const mine = c && (!c.id || c.id === s.id);
    $("-kind").textContent = mine ? c.kind : (s.title || s.form || "--");
    $("-kind").title = mine ? c.detail : s.form;
    $("-cfg").textContent = mine ? c.config : "run: bridge hud --watch";
    $("-cfg").title = mine ? c.detail : "";
    $("-go").disabled = s.signed;
    $("-go").textContent = s.signed
        ? ">> locked -- report is signed" : ">> inject uad 3.6 xml";
    $("-go").title = s.signed
        ? "This report is signed. Unsign it in TOTAL to import."
        : "Choose a UAD 3.6 MISMO XML file";
  };

  // The diagnostics list (bridge/diagnose.py), pushed for this report only.
  // A click goes to the item's field with TOTAL's own three navigation calls
  // (set the section key, let visibility decide, re-render), then scrolls to
  // the control and outlines it.  Nothing is written.
  const go = it => {
    const e = window.engine;
    try {
      const keys = e.GetAllSectionKeys() || [];
      const key = keys.includes(it.section) ? it.section
                : keys.find(k => it.section && k.startsWith(it.section));
      if (key && key !== e.currentActiveSectionKey) {
        e.currentActiveSectionKey = key; e.UpdateSectionVisibility(); e.RefreshReport();
      }
    } catch (err) {}
    setTimeout(() => {
      const sel = '[fn="' + String(it.field).replace(/"/g, '') + '"]';
      const el = document.querySelector(sel + '[instance="' + (it.instance || 0) + '"]')
              || document.querySelector(sel);
      if (!el) { say("not on screen: " + it.field + " (" + (it.section || "?") + ")", "bad"); return; }
      el.scrollIntoView({block: "center"});
      try { el.focus({preventScroll: true}); } catch (err) {}
      el.classList.add(ID + "-hl");
      setTimeout(() => el.classList.remove(ID + "-hl"), 2600);
      say(it.field + ": " + String(it.message || "").slice(0, 110));
    }, 1100);
  };
  const showDiagnostics = () => {
    const list = window.__uad36HudDiag, box = $("-dg"), s = state();
    if (!list || (list.id && s && list.id !== s.id)) { box.className = "dg"; return; }
    const count = {};
    for (const it of list.items) count[it.severity] = (count[it.severity] || 0) + 1;
    box.innerHTML = "";
    const head = document.createElement("div");
    head.className = "dh";
    head.textContent = list.items.length + " item(s): " +
        Object.entries(count).map(([k, n]) => n + " " + k).join(", ") + "  (" + list.when + ")";
    box.appendChild(head);
    for (const it of list.items.slice(0, 200)) {
      const row = document.createElement("div");
      row.className = "di " + it.severity + (it.field ? "" : " nofield");
      row.textContent = (it.field ? it.field + "  " : "") + it.message;
      row.title = [it.layer, it.severity, it.section, it.field && (it.field + "#" + it.instance),
                   it.data_point, it.uid, it.fid, it.cause, it.fix].filter(Boolean).join("\n");
      if (it.field) row.addEventListener("click", () => go(it));
      box.appendChild(row);
    }
    box.className = "dg on";
  };

  // Drag by the header, so the panel can be moved off anything it covers.
  (() => {
    let ox = 0, oy = 0, on = false;
    $("-hd").addEventListener("mousedown", ev => {
      if (ev.target.closest("button")) return;
      const r = el.getBoundingClientRect();
      ox = ev.clientX - r.left; oy = ev.clientY - r.top; on = true;
      ev.preventDefault();
    });
    window.addEventListener("mousemove", ev => {
      if (!on) return;
      el.style.left = Math.max(4, ev.clientX - ox) + "px";
      el.style.top = Math.max(4, ev.clientY - oy) + "px";
      el.style.right = "auto";
    });
    window.addEventListener("mouseup", () => { on = false; });
  })();

  $("-go").addEventListener("click", () => $("-file").click());
  $("-min").addEventListener("click", () => {
    el.classList.toggle("min");
    $("-min").innerHTML = el.classList.contains("min") ? "&plus;" : "&minus;";
  });

  $("-file").addEventListener("change", async ev => {
    const file = ev.target.files && ev.target.files[0];
    ev.target.value = "";
    if (!file) return;
    const s = state();
    if (!s) { say("no report loaded", "bad"); return; }
    if (s.signed) { say("denied: report is signed", "bad"); return; }

    $("-go").disabled = true;
    busy(true);
    say("reading " + file.name);
    try {
      const xml = await file.text();
      if (!/<[^>]*MESSAGE/i.test(xml)) {
        say("rejected: not a MISMO document", "bad");
        return;
      }
      // Never a bare ImportMismoXml: without the Import Module's preparation,
      // pictures and reconciliation TOTAL loses values (CATALOG E-043).  The
      // file goes to the Import Module (`bridge hud --watch`), which checks it,
      // imports it with TOTAL's own importer and reports back here.
      const w = window.__uad36Watcher;
      if (!w || Date.now() - w > 15000) {
        say("Import Module not running: start  bridge hud --watch  -- a bare import loses values (E-043)", "bad");
        return;
      }
      window.__uad36HudRequest = {name: file.name, xml, at: Date.now()};
      say("handed to the Import Module: " + file.name + " (" + (xml.length / 1048576).toFixed(1) + " MB)");
      busy(true);
      return;
    } catch (err) {
      say("error: " + String((err && err.message) || err).slice(0, 180), "bad");
    } finally {
      if (!window.__uad36HudRequest) busy(false);
      refresh();
    }
  });

  // The form rebuilds its DOM on every section change, which would take the
  // panel with it.  Put it back rather than asking for a reinstall.
  const keep = new MutationObserver(() => {
    if (!document.getElementById(ID)) document.body.appendChild(el);
    else refresh();
  });
  keep.observe(document.body, {childList: true});

  const tick = setInterval(refresh, 2000);
  window.__uad36Hud = {version: VERSION, refresh, setContext: c => { window.__uad36HudCtx = c; refresh(); },
                       setDiagnostics: d => { window.__uad36HudDiag = d; showDiagnostics(); },
                       say: (text, kind) => say(text, kind), busy: on => busy(on),
                       remove: () => {
    clearInterval(tick); keep.disconnect(); el.remove(); style.remove();
    delete window.__uad36Hud;
  }};
  refresh();
  showDiagnostics();
  const s = state();
  return {already: false, report: s && s.name, signed: s && s.signed};
})()
"""

_REMOVE = """
(() => { if (window.__uad36Hud) { window.__uad36Hud.remove(); return true; }
         return false; })()
"""


#: the panel's code identity: a panel installed by any other version is replaced
VERSION = __import__("hashlib").sha1(_INSTALL.encode("utf-8")).hexdigest()[:12]


def install(page) -> dict:
    """Put the panel in the page, or refresh it if this version is already there."""
    return page.evaluate(_INSTALL % {"id": PANEL_ID, "version": VERSION}) or {}


def remove(page) -> bool:
    return bool(page.evaluate(_REMOVE))


_POLL = """(() => { window.__uad36Watcher = Date.now();
  const r = window.__uad36HudRequest || null; window.__uad36HudRequest = null; return r; })()"""


def serve_request(page, name: str, req: dict, on_event=None) -> dict:
    """The panel's import, done by the Import Module: refuse a signed or used
    report (P5), check the package first (preflight), then `bridge deliver`,
    then the after-import diagnostics into the panel.  Progress is shown in
    the panel as it goes."""
    import json
    import time as _t
    from . import cdp, deliver, detect, diagnose
    from .images import staging
    from .total import Report, without_schema_location

    live = cdp.Page(page.url)                   # long calls: the default, generous timeout
    report = Report(live, name, False)

    def say(text, kind=""):
        live.evaluate(f"window.__uad36Hud && window.__uad36Hud.say({json.dumps(text)}, {json.dumps(kind)})")
        if on_event:
            on_event("import", f"{name}: {text}")

    def done(result):
        live.evaluate("window.__uad36Hud && window.__uad36Hud.busy(false)")
        live.close()
        return result

    if live.evaluate("!!(window.engine.IsSigned && window.engine.IsSigned())"):
        say("refused: the report is signed", "bad")
        return done({"refused": "signed"})
    fresh = detect.freshness(report)
    if fresh["fresh"] is False:
        first = ", ".join(k for k, _i, _v in fresh["extra"][:4])
        say(f"refused: this report already holds {len(fresh['extra'])} value(s) a new report does not "
            f"({first} ...) -- import into a new report (P5, E-029)", "bad")
        return done({"refused": "not a new report", "extra": fresh["extra"][:50]})

    path = staging() / f"hud-{_t.strftime('%Y%m%d-%H%M%S')}-{Path(req['name']).name}"
    path.write_text(req["xml"], encoding="utf-8")
    say("checking the package before TOTAL ...")
    before = diagnose.before(path)
    blocking = [d for d in before if d.severity in ("fatal", "severe")]
    if blocking:
        push_diagnostics(live, before)
        say(f"refused: {len(blocking)} problem(s) in the package itself -- listed below; fix the package", "bad")
        return done({"refused": "package", "before": diagnose.as_json(before)})

    result = deliver.run(report, path, progress=lambda t: say(t))
    if result.get("import_error"):
        say("TOTAL's import failed: " + str(result["import_error"])[:160], "bad")
        return done(result)
    say("diagnosing the imported report ...")
    after = diagnose.after(report, package=without_schema_location(req["xml"]).encode("utf-8"),
                           progress=lambda t: say(t.strip()))
    push_diagnostics(live, before + after)
    severe = sum(d.severity in ("fatal", "severe") for d in after)
    say(f"imported {req['name']}: {severe} item(s) to clear -- listed below", "bad" if severe else "ok")
    push_context(live, name)
    return done(dict(result, diagnostics=diagnose.as_json(before + after)))


def _current(page) -> None:
    """This version's panel in the page (install replaces any other version)."""
    install(page)


def push_diagnostics(page, found) -> None:
    """Show bridge/diagnose.py's list in this report's panel, each item with a
    field clickable to it."""
    import json
    import time as _t
    from . import diagnose
    _current(page)
    report_id = page.evaluate("(window.engine && window.engine.ReportInfo || {}).Proj2000ID || ''")
    # H-1 rules the engine cannot execute are one line here, not 171: TOTAL's
    # own UAD run executes them after import (the full list is in the JSON)
    unrun = [d for d in found if d.layer == "generator-h1" and d.severity == "info"]
    shown = [d for d in found if d not in unrun]
    if unrun:
        shown.append(diagnose.Diagnostic("generator-h1", "info",
                                         f"{len(unrun)} H-1 rule(s) the engine cannot execute -- "
                                         "TOTAL's UAD rules run them after import", blocking="none"))
    payload = {"id": report_id, "when": _t.strftime("%H:%M:%S"), "items": diagnose.as_json(shown)}
    page.evaluate("window.__uad36Hud.setDiagnostics(" + json.dumps(payload) + ")")


def push_context(page, name: str = "") -> dict:
    """Tell the panel in this report what kind of report it is (form, legacy
    equivalent, buildings/units/ADUs, approaches) -- bridge/detect.py, reading
    only.  Each report's page has its own panel, so each gets its own."""
    import json
    from . import detect
    from .total import Report
    state = detect.describe(Report(page, name, False))
    page.evaluate("window.__uad36Hud && window.__uad36Hud.setContext("
                  + json.dumps(detect.hud_context(state)) + ")")
    return state

def watch(*, host=None, port=None, interval: float = 2.0, on_event=None,
          context_every: float = 30.0) -> None:
    """Keep the panel on whatever report is open, as reports come and go.

    Closing a report and opening another gives TOTAL a fresh page; a panel
    installed in the previous one went with it.  So rather than install once,
    this watches the debugging endpoint and installs into any UAD 3.6 page that
    does not have the panel yet.

    Pages are tracked by their own target id, not by the report's name -- the
    same report reopened is a different page and needs the panel again, and two
    reports can be open at once.
    """
    from . import cdp

    host = host or cdp.DEFAULT_HOST
    port = port or cdp.DEFAULT_PORT
    seen: dict[str, str] = {}          # target id -> report name
    told: dict[str, float] = {}        # target id -> when its panel was last told what it is

    while True:
        try:
            targets = cdp.pages(host, port)
        except cdp.NotRunning:
            # TOTAL is not up yet, or has been closed.  Keep waiting: the point
            # of watching is that it works without being restarted.
            if seen and on_event:
                on_event("closed", None)
            seen.clear()
            time.sleep(interval)
            continue

        live = set()
        for target in targets:
            ident = target.get("id") or target.get("webSocketDebuggerUrl", "")
            live.add(ident)
            page = None
            try:
                page = cdp.Page(target["webSocketDebuggerUrl"], timeout=20)
                info = page.evaluate(
                    "(() => { const e = window.engine; return e && e.ReportInfo"
                    " ? {name: e.ReportInfo.Description,"
                    "    has: !!window.__uad36Hud && window.__uad36Hud.version === '" + VERSION + "'}"
                    " : null; })()")
                if not info or not info.get("name"):
                    continue
                if not (ident in seen and info.get("has")):
                    install(page)
                    seen[ident] = info["name"]
                    told.pop(ident, None)
                    if on_event:
                        on_event("attached", info["name"])
                # the panel's import button: its file, for the Import Module
                req = page.evaluate(_POLL)
                if req and req.get("xml"):
                    if on_event:
                        on_event("import", f"{info['name']}: {req.get('name')} from the panel")
                    try:
                        serve_request(page, info["name"], req, on_event)
                    except Exception as exc:
                        page.evaluate("window.__uad36Hud && (window.__uad36Hud.busy(false),"
                                      f" window.__uad36Hud.say({json.dumps('import failed: ' + str(exc)[:160])}, 'bad'))")
                        if on_event:
                            on_event("import", f"{info['name']}: failed: {exc}")
                    told.pop(ident, None)
                if time.time() - told.get(ident, 0) > context_every:
                    try:
                        push_context(page, info["name"])
                    except Exception as exc:        # detection must never cost the panel
                        if on_event:
                            on_event("detect-failed", f"{info['name']}: {exc}")
                    told[ident] = time.time()
            except Exception:
                pass
            finally:
                if page is not None:
                    page.close()

        for ident in [i for i in seen if i not in live]:
            name = seen.pop(ident)
            if on_event:
                on_event("gone", name)

        time.sleep(interval)
