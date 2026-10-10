# Deploying the UAD 3.6 platform on Vercel

This repository deploys the **web platform** (`engine/app`, the editor + REST API)
as one Python serverless function. Tested 2026-10-04 under Vercel conditions
(`VERCEL=1`, no Playwright, no fonts, only the files `vercel.json` bundles):
17/17 checks pass.

## Steps

1. vercel.com → **Add New… → Project** → import this GitHub repository.
2. Framework preset: **Other**. Leave build/output settings empty (Vercel finds
   `api/index.py` and `requirements.txt` itself).
3. **Environment Variables** → add `URAR_ACCESS_CODE` = the passcode you want.
   Without it the gate generates a random code and the site stays locked.
4. Deploy. Open the URL, enter the passcode.

## What works on Vercel

| Works on Vercel | How, without a browser on the server |
|---|---|
| Passcode gate, case list, the 12 D-1 templates, editing | the API (`engine/app/api.py`) |
| Page layout / printed preview | the appraiser's browser measures, the server paginates (`CLIENT_LAYOUT_HTML`) |
| The PDF (`report.pdf`) and the ZIP package | drawn from the browser's layout (`engine/uad/report/pdfdraw.py`, E-163), downloaded in parts under the 4.5 MB response limit |
| Review Master: schema + 728 H-1 compliance rules | server-side |
| MISMO XML export / import | server-side |

Server-side printing with Chromium (`flow.to_pdf`) is used wherever Chromium
exists (local, Docker, desktop); Vercel uses the browser-drawn PDF.

## Limits you must know

* **Cases live in the shared Blob store.** Each server copy's `/tmp` is
  temporary; with `BLOB_READ_WRITE_TOKEN` set (a connected Vercel Blob store)
  every case, its images and its drawn PDF are kept there
  (`engine/app/durable.py`), and the browser keeps a copy as well
  (`engine/app/ui/vault.js`).
* **Fonts.** The report face (Adobe Myriad Pro) is licensed for embedding in
  documents, not for redistribution, so it is not in this repository. Locally,
  put the licensed `.otf`/`.ttf` files in `engine/assets/fonts/` (see
  `engine/uad/report/fonts.py`) before rendering PDFs.
* **The WinTOTAL MOD (`total-bridge/`) does not run on Vercel** — it drives the
  copy of a la mode TOTAL installed on the appraiser's PC over CDP. See
  `START_HERE.md`.
* Function size: the repository holds ~1.3 GB of reference material
  (specification folders, owner notes, zips); `.vercelignore` keeps all of it
  out, so the function carries ~84 MB of code/specs/installer plus ~120 MB of
  dependencies (limit 250 MB). No build script is needed: a fresh project that
  imports this repository builds as is (checked 2026-10-10 by copying exactly
  what `.vercelignore` keeps and serving it with `VERCEL=1`).

## Local, with PDF

    pip install -r requirements.txt playwright uvicorn
    playwright install chromium
    python engine/app/main.py
