"""Read-only: which import/export entry points does the TOTAL host carry?

The UAD 3.6 form is a web app, but the CefSharp host exposes a bridge object
(CefConnector) to it.  Whatever the host is willing to do for the form is
named in these assemblies.  .NET stores literals as UTF-16, so both encodings
are scanned.
"""
import re
import sys
from pathlib import Path

BIN = Path(r"C:\Program Files (x86)\a la mode\TOTAL\bin")

TARGETS = [
    "alamode.WinTOTAL.WebFormsEngineView.dll",
    "alamode.Common.CEFWrapper.dll",
    "alamode.DaVinci.Forms.dll",
    "alamode.DaVinci.Forms.Core.dll",
    "alamode.webapi.client.dll",
]

WANT = re.compile(
    r"(importMismo\w*|ImportMismo\w*|createAndReturnMismoXML|CreateAndReturnMismoXML|"
    r"\w*MismoXml\w*|\w*MismoDeserial\w*|uadwebengine[\w./-]*|"
    r"remote-debugging-port|RemoteDebuggingPort|"
    r"UAD-3\.6[\w.-]*|CefConnector|addRepeatableObject|createAppraisalReportZip)",
    re.I)


def strings_of(data: bytes):
    """ASCII and UTF-16LE runs of printable characters."""
    for m in re.finditer(rb"[\x20-\x7e]{6,}", data):
        yield m.group().decode("ascii", "replace")
    for m in re.finditer(rb"(?:[\x20-\x7e]\x00){6,}", data):
        yield m.group().decode("utf-16-le", "replace")


for name in TARGETS:
    path = BIN / name
    if not path.exists():
        print(f"\n=== {name}: not present")
        continue
    data = path.read_bytes()
    hits = sorted({m.group(0) for s in strings_of(data) for m in [WANT.search(s)] if m})
    print(f"\n=== {name}  ({len(data) / 1e6:.1f} MB)  {len(hits)} match(es)")
    for h in hits[:30]:
        print("   ", h)
