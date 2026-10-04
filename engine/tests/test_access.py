"""The passcode gate: right code in, wrong code out, and a session one instance
grants is honoured by every other instance (a serverless deployment runs many).

Run:  python engine/tests/test_access.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import access  # noqa: E402

FAILS: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'ok' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILS.append(name)


def main() -> int:
    for var in ("URAR_ACCESS_CODE", "URAR_OPEN", "URAR_SESSION_SECRET"):
        os.environ.pop(var, None)
    cfg = json.loads(access.CONFIG.read_text(encoding="utf-8"))
    check("access.json holds a verifier, not the passcode",
          "uad3.6" not in access.CONFIG.read_text() and cfg["algorithm"] == "pbkdf2_sha256")

    a, b = access.Access(), access.Access()          # two "instances"
    token = a.check("uad3.6", "t")
    check("the configured passcode uad3.6 unlocks", token is not None)
    check("surrounding whitespace is forgiven", a.check("  uad3.6 ", "t") is not None)
    check("a different case is refused (exact match)", a.check("UAD3.6", "t") is None)
    check("a retired passcode is refused", a.check("retired-code", "t") is None)
    check("a session from one instance is valid on another", b.valid(token or ""))
    check("the stored digest is not itself a session", not b.valid(cfg["session"]))
    check("an empty cookie is refused", not b.valid(""))

    for _ in range(access.MAX_FAILURES):
        a.check("wrong", "attacker")
    check("repeated failures throttle the address", a.throttled("attacker"))
    check("other addresses are not throttled", not a.throttled("someone-else"))

    os.environ["URAR_SESSION_SECRET"] = "s3cret"
    c, d = access.Access(), access.Access()
    t2 = c.check("uad3.6", "t") or ""
    check("with a session secret, tokens carry an expiry", "." in t2)
    check("...and are valid across instances", d.valid(t2))
    check("...and a tampered expiry is refused",
          not d.valid(str(int(t2.split('.')[0]) + 999) + "." + t2.split('.')[1]))
    os.environ.pop("URAR_SESSION_SECRET")

    os.environ["URAR_ACCESS_CODE"] = "another-code"
    e = access.Access()
    check("URAR_ACCESS_CODE overrides the file", e.check("another-code") is not None
          and e.check("uad3.6") is None)
    os.environ.pop("URAR_ACCESS_CODE")

    print(f"\n{'FAILED' if FAILS else 'all passed'}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
