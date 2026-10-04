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

| Works | Does not work on Vercel (needs a machine with Chromium) |
|---|---|
| Passcode gate, case list, the 12 D-1 templates | Page layout / printed preview |
| Create, open, edit cases through the API | The PDF (`report.pdf`) and the ZIP package |
| Review Master: schema + 728 H-1 compliance rules | |
| MISMO XML export / import | |

The browser-only actions answer **503 with an explanation**, never a crash
(`engine/uad/report/browser.py`).

## Limits you must know

* **Cases are temporary.** Vercel's only writable disk is `/tmp`, per instance;
  a case disappears when the instance is recycled. Use the deployment to show or
  check the platform, not to keep work. Real work: run it locally
  (`python engine/app/main.py`, http://127.0.0.1:8765) or on a server with a disk.
* **Fonts.** The report face (Adobe Myriad Pro) is licensed for embedding in
  documents, not for redistribution, so it is not in this repository. Locally,
  put the licensed `.otf`/`.ttf` files in `engine/assets/fonts/` (see
  `engine/uad/report/fonts.py`) before rendering PDFs.
* **The WinTOTAL MOD (`total-bridge/`) does not run on Vercel** — it drives the
  copy of a la mode TOTAL installed on the appraiser's PC over CDP. See
  `START_HERE.md`.
* Function size: ~30 MB of code/specs + ~120 MB of dependencies (limit 250 MB).

## Local, with PDF

    pip install -r requirements.txt playwright uvicorn
    playwright install chromium
    python engine/app/main.py
