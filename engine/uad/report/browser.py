"""The headless browser the renderer measures and prints with -- when there is one.

Layout measurement, pagination and the PDF all run in Chromium through
Playwright.  A host without it (a Vercel serverless function, a slim container)
can still run everything else -- the editor, the API, the compliance review,
the MISMO XML -- so the import is optional: modules take ``sync_playwright``
from here, and calling it without a browser raises :class:`BrowserUnavailable`,
which the server answers with 503 and a plain explanation instead of failing
to start.
"""
from __future__ import annotations


class BrowserUnavailable(RuntimeError):
    """This host has no Chromium / Playwright: page layout and PDF are unavailable."""


MESSAGE = ("Page layout, the printed preview and the PDF need Chromium (Playwright), which this host "
           "does not have. Run the platform locally (python engine/app/main.py) to render the report; "
           "editing, the Review Master and the MISMO XML work here.")


try:                                                    # pragma: no cover - depends on the host
    from playwright.sync_api import sync_playwright     # noqa: F401
    AVAILABLE = True
except ImportError:                                     # pragma: no cover
    AVAILABLE = False

    def sync_playwright():                              # type: ignore[no-redef]
        raise BrowserUnavailable(MESSAGE)
