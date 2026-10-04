/* The case vault: this browser's copy of every case it works on.
 *
 * A serverless deployment runs several short-lived copies of the server, each
 * with its own disk.  A case created on one copy is unknown to the next, and a
 * copy that goes idle takes its disk with it.  The vault keeps each case's
 * bundle (app/cases.py Store.bundle) in IndexedDB and works with the server's
 * vault middleware (app/main.py):
 *
 *   * every request about a case says it takes part (X-UAD-Vault) and which
 *     revision this browser holds (X-UAD-Rev);
 *   * every change answers with the case's fresh bundle (`_vault` in the JSON),
 *     which is kept here -- so the copy is never behind the server that made
 *     the change;
 *   * a server copy that lacks the case (404) or holds an older revision (409)
 *     gets the vault's copy (POST /api/cases/restore) and the request is made
 *     again, once.
 *
 * Photographs uploaded from this browser are kept too and put back after a
 * restore.  On a server with a durable disk the vault is a quiet extra backup.
 */
(function () {
  'use strict';
  const DB = 'uad36-vault', VER = 1;
  let dbp = null;
  function db() {
    if (dbp) return dbp;
    dbp = new Promise((res, rej) => {
      let req;
      try { req = indexedDB.open(DB, VER); } catch (e) { rej(e); return; }
      req.onupgradeneeded = () => {
        const d = req.result;
        if (!d.objectStoreNames.contains('cases')) d.createObjectStore('cases', { keyPath: 'id' });
        if (!d.objectStoreNames.contains('media')) d.createObjectStore('media', { keyPath: 'key' });
      };
      req.onsuccess = () => res(req.result);
      req.onerror = () => rej(req.error);
    });
    return dbp;
  }
  const p = r => new Promise((res, rej) => { r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  async function get(store, key) {
    const d = await db(); return p(d.transaction(store).objectStore(store).get(key));
  }
  async function all(store) {
    const d = await db(); return p(d.transaction(store).objectStore(store).getAll());
  }
  async function put(store, value) {
    const d = await db(); return p(d.transaction(store, 'readwrite').objectStore(store).put(value));
  }
  async function del(store, key) {
    const d = await db(); return p(d.transaction(store, 'readwrite').objectStore(store).delete(key));
  }
  function b64blob(b64) {
    const bin = atob(b64), u = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i);
    return new Blob([u], { type: 'application/zip' });
  }

  const revs = {};                 // case -> newest revision this browser holds
  const restoring = {};
  const V = { enabled: typeof indexedDB !== 'undefined' };

  V.ready = (async () => {
    if (!V.enabled) return;
    try { (await all('cases')).forEach(r => { revs[r.id] = r.updated; }); } catch (e) { V.enabled = false; }
  })();

  /* Keep a bundle the server handed back, unless a newer one is already kept. */
  V.ingest = async function (v) {
    if (!V.enabled || !v || !v.case_id || !v.bundle) return;
    if (revs[v.case_id] && revs[v.case_id] > v.updated) return;
    revs[v.case_id] = v.updated;
    try {
      await put('cases', { id: v.case_id, blob: b64blob(v.bundle), updated: v.updated,
                           name: v.name || '', saved: Date.now() });
    } catch (e) {}
  };
  /* For a case this browser has not held before: ask its server for a copy. */
  V.adopt = async function (id) {
    if (!V.enabled || !id || revs[id]) return;
    try {
      const r = await origFetch('/api/cases/' + id + '/bundle?images=0');
      if (!r.ok) return;
      const blob = await r.blob(), updated = r.headers.get('X-Case-Updated') || '';
      if (revs[id] && revs[id] >= updated) return;
      revs[id] = updated;
      await put('cases', { id, blob, updated, name: '', saved: Date.now() });
    } catch (e) {}
  };
  V.keepMedia = async function (id, mediaId, file) {
    if (!V.enabled || !file) return;
    try { await put('media', { key: id + '/' + mediaId, id, mediaId, blob: file }); } catch (e) {}
  };
  V.has = id => !!revs[id];
  V.list = async () => (V.enabled ? (await all('cases').catch(() => [])) : []);
  V.forget = async function (id) {
    delete revs[id];
    try {
      await del('cases', id);
      for (const m of (await all('media')).filter(m => m.id === id)) await del('media', m.key);
    } catch (e) {}
  };
  /* Put this browser's copy on the server copy that answered; `replace` when
     that copy holds an older revision.  One restore per case at a time. */
  V.restore = function (id, replace) {
    if (restoring[id]) return restoring[id];
    restoring[id] = (async () => {
      try {
        const rec = await get('cases', id);
        if (!rec) return false;
        const fd = new FormData();
        fd.append('file', rec.blob, id + '.uadcase.zip');
        const r = await origFetch('/api/cases/restore' + (replace ? '?replace=true' : ''),
                                  { method: 'POST', body: fd });
        if (r.status === 409) return true;          // already there
        if (!r.ok) return false;
        const info = await r.json();
        const want = new Set(info.missing_media || []);
        if (want.size) {
          for (const m of (await all('media')).filter(m => m.id === id && want.has(m.mediaId))) {
            await origFetch('/api/cases/' + id + '/media/' + m.mediaId + '/file',
                            { method: 'PUT', body: m.blob }).catch(() => {});
          }
        }
        return true;
      } catch (e) { return false; }
      finally { setTimeout(() => { delete restoring[id]; }, 300); }
    })();
    return restoring[id];
  };

  const CASE = /^\/api\/cases\/([0-9a-f]{12})(\/|$)/;
  let origFetch = window.fetch.bind(window);

  /* Wrap a window's fetch so every caller -- the editor, the report frame,
     the layout bootstrap -- takes part without knowing. */
  V.install = function (win) {
    if (!win || win.__uadVault) return;
    win.__uadVault = true;
    const orig = win.fetch.bind(win);
    if (win === window) origFetch = orig;
    win.fetch = async function (input, init) {
      init = Object.assign({}, init || {});
      const url = new URL(typeof input === 'string' ? input : input.url, win.location.href);
      if (!V.enabled || url.origin !== win.location.origin || !url.pathname.startsWith('/api/')) {
        return orig(input, init);
      }
      await V.ready;
      const m = url.pathname.match(CASE);
      const id = m && m[1];
      const method = (init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
      const send = () => {
        const h = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
        h.set('X-UAD-Vault', '1');
        if (id && revs[id]) h.set('X-UAD-Rev', revs[id]);
        return orig(input, Object.assign({}, init, { headers: h }));
      };
      let r = await send();
      if (id && revs[id] && (r.status === 404 || r.status === 409)) {
        let stale = r.status === 409;
        if (stale) { try { stale = !!(await r.clone().json()).stale; } catch (e) { stale = false; } }
        if (r.status === 404 || stale) {
          if (await V.restore(id, stale)) r = await send();
        }
      }
      if (r.ok && method !== 'GET' && (r.headers.get('content-type') || '').includes('json')) {
        try {
          const d = await r.clone().json();
          if (d && d._vault) await V.ingest(d._vault);
          if (id && method === 'POST' && /\/media$/.test(url.pathname) && init.body instanceof FormData) {
            const f = [...init.body.values()].find(v => v instanceof Blob);
            if (f && d && d.media_id) V.keepMedia(id, d.media_id, f);
          }
        } catch (e) {}
        if (id && method === 'DELETE' && url.pathname === '/api/cases/' + id) V.forget(id);
      }
      if (id && method === 'GET' && r.ok && !revs[id] && url.pathname === '/api/cases/' + id) V.adopt(id);
      return r;
    };
  };
  window.UADVault = V;
  V.install(window);
})();
