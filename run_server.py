"""Start the review server for a packet."""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "engine"))

import uvicorn
from app import server

if len(sys.argv) < 2:
    raise SystemExit("usage: run_server.py <packet.pdf> [effective-date]")
PACKET = sys.argv[1]
EFFECTIVE = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date(2026, 9, 13)

if __name__ == "__main__":
    print(f"Loading packet: {PACKET}")
    server.load(PACKET, EFFECTIVE)

    print()
    print("  Review server   http://0.0.0.0:8000")
    if server.ACCESS.open:
        print("  Passcode        DISABLED (URAR_OPEN=1) - do not expose publicly")
    else:
        print(f"  Passcode        {server.ACCESS.code}")
        print("                  share this with the link")
    print()
    # Bind on all interfaces so a tunnel can reach it.
    uvicorn.run(server.app, host="0.0.0.0", port=8000, log_level="warning")
