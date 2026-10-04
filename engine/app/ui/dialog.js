/* The platform's own dialogs, in place of the browser's alert / confirm /
 * prompt ("uad36-form-filler.vercel.app says ...").  One component for the
 * editor, the report frame and the map tool: frames on this origin call
 * window.top.UADDialog.
 *
 *   UADDialog.alert(message, {title})                    -> Promise<void>
 *   UADDialog.confirm(message, {title, ok, cancel, danger}) -> Promise<boolean>
 *   UADDialog.prompt(message, {title, value, placeholder, ok}) -> Promise<string|null>
 *
 * A message with several lines shows its first line as the lead and the rest
 * as a list, so a list of reasons reads as one.  Enter confirms, Esc cancels,
 * focus stays inside the dialog while it is open.  It follows the editor's
 * light / dark theme (data-theme on <html>).
 */
(function () {
  'use strict';
  if (window.UADDialog) return;
  var CSS = ''
    + '.uadd-back{position:fixed;inset:0;z-index:2147483000;display:flex;align-items:center;justify-content:center;padding:20px;'
    + 'background:rgba(5,5,6,.55);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px);animation:uaddf .15s ease-out}'
    + '@keyframes uaddf{from{opacity:0}}@keyframes uaddp{from{opacity:0;transform:translateY(8px) scale(.985)}}'
    + '.uadd{width:min(100%,480px);max-height:calc(100vh - 40px);overflow:auto;border-radius:20px;padding:24px 24px 20px;'
    + 'font:400 14px/1.5 "Geist","Inter","Segoe UI",-apple-system,Roboto,Arial,sans-serif;-webkit-font-smoothing:antialiased;'
    + 'color:#f4f4f5;border:1px solid transparent;'
    + 'background:linear-gradient(#141416,#111113) padding-box,linear-gradient(135deg,rgba(255,255,255,.55),rgba(255,255,255,.07) 38%,rgba(255,255,255,.24) 72%,rgba(255,255,255,.05)) border-box;'
    + 'box-shadow:0 40px 90px rgba(0,0,0,.6);animation:uaddp .18s ease-out}'
    + '.uadd.light{color:#0b0b0c;background:#fff;border-color:#e4e4e4;box-shadow:0 30px 80px rgba(0,0,0,.18)}'
    + '.uadd .ey{display:flex;align-items:center;gap:9px;font-weight:500;font-size:10.5px;line-height:1;letter-spacing:.17em;text-transform:uppercase;color:#8c8c94}'
    + '.uadd .ey:before{content:"+";font-weight:300;font-size:17px;letter-spacing:0;color:currentColor}'
    + '.uadd h2{margin:12px 0 8px;font-weight:500;font-size:21px;line-height:1.2;letter-spacing:-.03em}'
    + '.uadd p{margin:0;color:#b9b9c0;white-space:pre-line}.uadd.light p{color:#4a4a50}'
    + '.uadd ul{margin:12px 0 0;padding:0;list-style:none;border-top:1px solid rgba(255,255,255,.09)}'
    + '.uadd.light ul{border-top-color:#ececec}'
    + '.uadd li{display:flex;gap:10px;padding:9px 0;border-bottom:1px solid rgba(255,255,255,.09);font-size:13px;color:#cdcdd2}'
    + '.uadd.light li{border-bottom-color:#ececec;color:#2c2c30}'
    + '.uadd li:before{content:"";flex:none;width:6px;height:6px;margin-top:7px;border-radius:50%;background:#f2787e}'
    + '.uadd input{width:100%;margin-top:14px;padding:12px 14px;border-radius:12px;border:1px solid rgba(255,255,255,.16);'
    + 'background:rgba(255,255,255,.05);color:inherit;font:inherit;box-sizing:border-box}'
    + '.uadd.light input{border-color:#dcdcdc;background:#fafafa}'
    + '.uadd input:focus{outline:none;border-color:rgba(255,255,255,.5)}.uadd.light input:focus{border-color:#0b0b0c}'
    + '.uadd .bar{display:flex;justify-content:flex-end;gap:8px;margin-top:22px}'
    + '.uadd button{appearance:none;cursor:pointer;border-radius:10px;padding:10px 16px;font-weight:500;font-size:13.5px;line-height:1;'
    + 'border:1px solid rgba(255,255,255,.18);background:transparent;color:inherit;transition:opacity .12s,background .12s}'
    + '.uadd.light button{border-color:#dcdcdc}'
    + '.uadd button:hover{background:rgba(255,255,255,.06)}.uadd.light button:hover{background:#f3f3f3}'
    + '.uadd button.go{background:#f4f4f5;border-color:#f4f4f5;color:#0a0a0b}'
    + '.uadd.light button.go{background:#0b0b0c;border-color:#0b0b0c;color:#fff}'
    + '.uadd button.go:hover{opacity:.88}'
    + '.uadd button.go.danger{background:#e5484d;border-color:#e5484d;color:#fff}'
    + '.uadd button:focus-visible{outline:1.5px solid currentColor;outline-offset:2px}';

  function theme() {
    try { return (window.top.document.documentElement.dataset.theme || 'dark'); } catch (e) { return 'dark'; }
  }
  function ensureStyle() {
    if (document.getElementById('uadd-css')) return;
    var st = document.createElement('style'); st.id = 'uadd-css'; st.textContent = CSS;
    document.head.appendChild(st);
  }
  function el(tag, cls, text) {
    var e = document.createElement(tag); if (cls) e.className = cls;
    if (text != null) e.textContent = text; return e;
  }

  function open(kind, message, o) {
    o = o || {};
    ensureStyle();
    return new Promise(function (resolve) {
      var before = document.activeElement;
      var back = el('div', 'uadd-back');
      var box = el('div', 'uadd' + (theme() === 'light' ? ' light' : ''));
      box.setAttribute('role', kind === 'alert' ? 'alertdialog' : 'dialog');
      box.setAttribute('aria-modal', 'true');
      var lines = String(message == null ? '' : message).split('\n').map(function (s) { return s.trim(); })
        .filter(function (s, i, a) { return s || (i && a[i - 1]); });
      var lead = lines.shift() || '';
      var rest = lines.filter(Boolean);
      box.appendChild(el('div', 'ey', o.eyebrow || (kind === 'confirm' ? 'Please confirm' : kind === 'prompt' ? 'Details' : 'Notice')));
      var h = el('h2', '', o.title || lead);
      h.id = 'uadd-h' + Date.now(); box.setAttribute('aria-labelledby', h.id);
      box.appendChild(h);
      if (o.title && lead) box.appendChild(el('p', '', lead));
      if (rest.length) {
        var ul = el('ul');
        rest.forEach(function (r) { ul.appendChild(el('li', '', r)); });
        box.appendChild(ul);
      }
      var input = null;
      if (kind === 'prompt') {
        input = el('input'); input.type = 'text';
        input.value = o.value || ''; input.placeholder = o.placeholder || '';
        box.appendChild(input);
      }
      var bar = el('div', 'bar');
      var cancel = null;
      if (kind !== 'alert') { cancel = el('button', '', o.cancel || 'Cancel'); cancel.type = 'button'; bar.appendChild(cancel); }
      var ok = el('button', 'go' + (o.danger ? ' danger' : ''), o.ok || (kind === 'alert' ? 'OK' : kind === 'prompt' ? 'Continue' : 'Confirm'));
      ok.type = 'button'; bar.appendChild(ok);
      box.appendChild(bar);
      back.appendChild(box);
      document.body.appendChild(back);

      function done(value) {
        document.removeEventListener('keydown', key, true);
        back.remove();
        try { if (before && before.focus) before.focus(); } catch (e) {}
        resolve(value);
      }
      function yes() {
        if (kind === 'prompt') {
          var v = input.value.trim();
          if (!v) { input.focus(); return; }
          return done(v);
        }
        done(kind === 'confirm' ? true : undefined);
      }
      function no() { done(kind === 'confirm' ? false : kind === 'prompt' ? null : undefined); }
      function key(e) {
        if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); no(); }
        else if (e.key === 'Enter' && (kind !== 'prompt' || e.target === input || e.target === ok)) { e.preventDefault(); e.stopPropagation(); yes(); }
        else if (e.key === 'Tab') {               // keep focus inside
          var f = [].slice.call(box.querySelectorAll('button,input'));
          var i = f.indexOf(document.activeElement);
          e.preventDefault(); f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
        }
      }
      ok.onclick = yes;
      if (cancel) cancel.onclick = no;
      back.addEventListener('mousedown', function (e) { if (e.target === back && kind !== 'alert') no(); });
      document.addEventListener('keydown', key, true);
      setTimeout(function () { (input || ok).focus(); }, 0);
    });
  }
  window.UADDialog = {
    alert: function (m, o) { return open('alert', m, o); },
    confirm: function (m, o) { return open('confirm', m, o); },
    prompt: function (m, o) { return open('prompt', m, o); },
  };
})();
