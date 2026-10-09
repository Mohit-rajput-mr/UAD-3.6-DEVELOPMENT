"""The desktop edition's licence key -- held as a verifier, never in plain text.

Three places ask for the key and all three read the same verifier,
``engine/app/license.json`` (PBKDF2-SHA256: salt, iterations, two digests):

* the web platform's **Download product** button: the key, checked on the
  server, earns a download ticket (``check`` below; ``app/download.py``);
* the Windows **installer**: it runs this file with its own Python before
  anything is installed -- ``python license.py check <file holding the key>``
  -- and goes no further unless the key matches;
* the **desktop app** at start: the installer leaves an activation record,
  and a copy without one asks for the key again (``app/desktop.py``).

Only the standard library is used, because the installer runs this file
before anything else is installed.

The ticket is ``HMAC(PBKDF2(key), "download-v1")``: only someone who knew the
key can make it, and the verifier keeps only its SHA-256, so any server copy
can accept it without shared state (the same scheme as app/access.py).

    python engine/app/license.py set-key      prompts; rewrites license.json
"""
from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
from pathlib import Path

CONFIG = Path(__file__).resolve().parent / "license.json"
ITERATIONS = 600_000            # OWASP 2023 guidance for PBKDF2-HMAC-SHA256
MAX_FAILURES, WINDOW = 8, 15 * 60


def _derive(key: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", key.encode("utf-8"), salt, iterations)


def _ticket_from(derived: bytes) -> str:
    return hmac.new(derived, b"download-v1", hashlib.sha256).hexdigest()


def make_config(key: str, iterations: int = ITERATIONS) -> dict:
    """The verifier for ``key``: what license.json stores instead of the key."""
    salt = secrets.token_bytes(16)
    derived = _derive(key, salt, iterations)
    return {"algorithm": "pbkdf2_sha256", "iterations": iterations, "salt": salt.hex(),
            "check": hashlib.sha256(b"check" + derived).hexdigest(),
            "ticket": hashlib.sha256(_ticket_from(derived).encode()).hexdigest()}


def load(path: Path | None = None) -> dict:
    return json.loads(Path(path or CONFIG).read_text(encoding="utf-8"))


def normalise(key: str) -> str:
    """What the appraiser typed, as compared: surrounding spaces dropped."""
    return (key or "").strip()


def check(key: str, config: dict | None = None) -> str | None:
    """The download / activation ticket when ``key`` is the licence key, else None."""
    config = config or load()
    derived = _derive(normalise(key), bytes.fromhex(config["salt"]), int(config["iterations"]))
    good = hmac.compare_digest(hashlib.sha256(b"check" + derived).hexdigest(), config["check"])
    return _ticket_from(derived) if good else None


def ticket_valid(ticket: str, config: dict | None = None) -> bool:
    if not ticket or len(ticket) != 64:
        return False
    config = config or load()
    return hmac.compare_digest(hashlib.sha256(ticket.encode()).hexdigest(), config["ticket"])


class Throttle:
    """Wrong keys per client address, so the key cannot be guessed online."""

    def __init__(self) -> None:
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, who: str) -> bool:
        now = time.time()
        with self._lock:
            recent = [t for t in self._failures.get(who, []) if now - t < WINDOW]
            self._failures[who] = recent
            return len(recent) >= MAX_FAILURES

    def failed(self, who: str) -> None:
        with self._lock:
            self._failures.setdefault(who, []).append(time.time())

    def cleared(self, who: str) -> None:
        with self._lock:
            self._failures.pop(who, None)


def _main(argv: list[str]) -> int:
    if argv[:1] == ["check"] and len(argv) >= 2:
        # the installer: the key is in a file (never on a command line, where
        # other programs could read it); the ticket is written beside it so
        # the installer can leave the activation record
        key_file = Path(argv[1])
        config_file = Path(argv[2]) if len(argv) > 2 else CONFIG
        try:
            raw = key_file.read_bytes()
            # the installer writes UTF-16 with a byte-order mark (NSIS
            # FileWriteUTF16LE /BOM); anything else is read as UTF-8
            key = (raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff")
                   else raw.decode("utf-8-sig"))
        finally:
            try:
                key_file.unlink()
            except OSError:
                pass
        ticket = check(key, load(config_file))
        if ticket is None:
            return 1
        key_file.with_name("ticket.txt").write_text(ticket, encoding="ascii")
        return 0
    if argv[:1] == ["set-key"]:
        import getpass
        first = getpass.getpass("New licence key: ")
        if first != getpass.getpass("Again: ") or not normalise(first):
            print("the keys did not match")
            return 2
        CONFIG.write_text(json.dumps(make_config(normalise(first)), indent=2) + "\n",
                          encoding="utf-8")
        print(f"wrote {CONFIG}")
        return 0
    print("usage: license.py set-key | check <key file> [license.json]")
    return 2


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
