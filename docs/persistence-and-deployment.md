# Persistence, deployment and access

## Case storage

- **One server with a real disk** (desktop, Docker): cases live under
  `URAR_WORK`. Sign-off state is in SQLite (WAL mode).
- **Many short-lived copies** (Vercel): `engine/app/durable.py` keeps every
  case in one shared store.
  - Each case's bundle is at `cases/<id>/case.zip`; each image is stored once at `cases/<id>/img/<name>`.
  - Before a request, the copy makes a conditional GET on the bundle's ETag (304 when current).
  - After a change, the copy pushes the new bundle. The last write in time order is kept.
- **Backends:**
  - **Vercel Blob** (private store `uad36-cases`), enabled by `BLOB_READ_WRITE_TOKEN`.
  - A shared directory, enabled by `URAR_DURABLE_DIR`.
  - A Postgres backend (Supabase or Neon) would implement the same five `Backend` methods and need no other change.
- Tests: `engine/tests/test_durable.py`. A two-copy round-robin test is described in `_work/HANDOFF.md`.

## The browser side

IndexedDB holds two caches. Both are stale-while-revalidate: shown at once, then checked.

| Store | Holds |
|---|---|
| `uad36-layout` | Laid-out pages per case and kind |
| `uad36-editor` | Case, sections, review, media, prefs |

So a reload is instant.

## Access: the passcode

- One shared passcode guards every route except the unlock form, `/healthz` and
  the two font files (`engine/app/access.py`, `OPEN_PATHS`).
- The passcode is stored only as a **PBKDF2 verifier** in
  `engine/app/access.json`. It appears in no client code, log or commit.
- Sessions are **stateless**: an HMAC token in an `httponly`, `samesite=lax`
  cookie (`urar_access`), lasting 12 hours, valid on every server copy.
  Changing the passcode revokes every session.
- Failed attempts are throttled per client address.
- Tests sign in with `access.sign_in(client)` and never with the passcode.

## Deployment

| Target | How | Notes |
|---|---|---|
| **Vercel** (live) | Pushing to GitHub `main` deploys production (`api/index.py`, `vercel.json`) | No browser, so layout runs in the user's browser and the PDF is drawn from that layout (`uad/report/pdfdraw.py`, E-163); PDF and ZIP download in parts under the 4.5 MB response limit. The `UAD_BUILD` env var is the build-time prune step that keeps the function under 225 MB; keep it. See `DEPLOY_VERCEL.md`. |
| **Docker** | `docker build -t uad36 . && docker run -p 8765:8765 -v uad36-cases:/data uad36` | Chromium is included, so the server lays out the report and prints the PDF. See `DEPLOY_DOCKER.md`. |
| **Local** | `python engine/app/main.py` | `http://127.0.0.1:8765` |

## The API

Everything the UI does is a REST call under `/api` (`engine/app/api.py`); the
UI has no private path. The main groups:

- **cases**: list, create (`template`, `blank`), get, delete, restore, bundle.
- **fields**:
  - `GET /fields?slim=1`;
  - `PATCH /fields/{fid}`;
  - `PATCH /cells/{fid}` (table cells);
  - `PATCH /extra/{uid}` (non-printing points).
- **comparables, media, images, maps, market**: see `comps-images-maps.md`.
- **review**: `/review`, `/rules`, `/integrity`, `/package/check`, `/acknowledge`.
- **render**:
  - `/render/{kind}`;
  - `/layout/{kind}/galley`;
  - `POST /layout/{kind}/pages`;
  - `/preview`.
- **export**: `mismo.xml`, `portable.xml`, `report.pdf`, `package.zip`.
- **import**: `POST /import`.
