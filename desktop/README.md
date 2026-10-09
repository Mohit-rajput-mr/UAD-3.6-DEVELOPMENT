# UAD 3.6 desktop (Windows)

The same platform as the web edition, installed on the appraiser's own PC.
Reports, photos and signatures stay on that PC. The editor, the compliance
review, the PDF and the delivery ZIP all run there, and it works offline;
only the address lookup and map tiles use the internet.

## For the appraiser

1. Get the installer:
   - Go to **Download product** on the web platform: the button in the
     editor's header, the link on the sign-in page, or `/download`.
   - Enter the licence key. The installer downloads in parts, each one
     checksum-verified.
2. Open `UAD36-Desktop-Setup-<version>.exe`. Windows may say *"Windows
   protected your PC"*: choose **More info → Run anyway**. The installer is
   not code-signed yet (see *Signing* below).
3. Enter the licence key again. The app installs for your Windows user only,
   so no administrator rights are needed. It goes in
   `%LOCALAPPDATA%\Programs\UAD36`.
4. Start **UAD 3.6** from the Start menu or the desktop. It opens in its own
   window (Edge in app mode). Closing the window stops it.

Reports live in `%LOCALAPPDATA%\UAD36\cases`. Updating keeps them.
Uninstalling (Settings → Apps) asks whether to delete them, and the answer
defaults to **No**. The log is `%LOCALAPPDATA%\UAD36\logs\desktop.log`.

## How it works

| Piece | What it is |
|---|---|
| `launcher.py` | What the shortcut runs (`python\pythonw.exe -I app\desktop\launcher.py`). It allows one copy at a time. It starts the server on `127.0.0.1` (port 27536 or the next free one) and opens the Edge app window. It stops once the window has been gone for 90 s; the editor checks in every 30 s. |
| `engine/app/desktop.py` | The window's one-time key: `/desktop/unlock?k=…` sets the session. The web passcode never applies here, and no other program can use the local server. It also handles activation: an install without a valid activation record asks for the key once. |
| `engine/app/license.py` | The licence key as a PBKDF2-SHA256 verifier (`license.json`). It is used by the web download, the installer (`license.py check <file>`) and the app. The key itself is in no file. |
| `engine/uad/report/cdp.py` | Drives the Edge already on the PC over the DevTools protocol, replacing Playwright and its 150 MB Chromium. Measurements, page checks and the PDF are identical (tests/test_desktop.py: 230 blocks, 20 pages, pixel for pixel). |
| `installer.nsi` | NSIS, 64-bit, per-user. The key page runs the bundled Python's `license.py` before anything is installed. Silent install: `/S /KEY=<key>`. |
| `build.py` | Builds the installer on Linux or Windows (see below). |
| `downloads/desktop/` | The built installer in parts under 4 MB, plus `manifest.json`. The web's Download product serves these (`engine/app/download.py`), because a Vercel function answers at most 4.5 MB. |

The window lays the report out itself (`URAR_CLIENT_LAYOUT=1`, as on the
web), so no headless browser runs after each edit. Edge headless is started
only for the PDF and the ZIP.

## Building

```bash
apt install nsis            # or NSIS for Windows from nsis.sourceforge.io
python desktop/build.py     # ~2 minutes; writes desktop/dist/ and downloads/desktop/
```

What `build.py` does:

- **Python.** It downloads the Python Software Foundation's own Windows
  package (NuGet `python` 3.11.9). The download is checked against
  `python.sha256`.
- **Libraries.** It installs the pinned Windows wheels from
  `requirements.txt`. These are the versions the test suite passes with.
- **App files.** It packs only git-tracked files: `engine/` without its
  tests, the runtime specification files, and the launcher. New files must
  be `git add`-ed before building.
- **Shelving.** It cuts the installer into parts for the web download.
  Commit `downloads/desktop/` to publish it.

Bump `VERSION` for each release.

**Changing the licence key:** run `python engine/app/license.py set-key`
(it prompts and echoes nothing), then rebuild and commit. The old key then
stops working for downloads, new installs and new activations. Copies that
are already activated keep working, because their record holds the old
ticket. To stop those too, delete their `activation.json`; they will then
ask for the new key.

**Tested** on this build machine under Wine 9 (64-bit):
- a wrong key and a missing key were refused, and nothing was installed;
- the right key installed the app with its shortcuts and activation record;
- the installed app served the editor;
- a 3-unit report was created and edited, and the edit saved to the XML;
- activation asked for the key when the record was removed;
- uninstalling kept the reports.

Not yet tested on a physical Windows PC. The Edge window and the Edge-made
PDF there are the parts Wine cannot show. The same driver was checked
against Chromium here.

## Signing

Windows SmartScreen warns about any unsigned installer until it has a
reputation. To remove the warning, buy a code-signing certificate (OV or EV)
and sign `desktop/dist/*.exe` with `signtool` (or `osslsigncode` on Linux)
before running the shelving step.
