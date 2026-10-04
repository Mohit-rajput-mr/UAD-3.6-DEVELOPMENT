"""Locations of the reference documents shipped with this workspace."""
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _spec_root() -> Path:
    """UAD_SPEC_ROOT, else the documentation folder, else specs/official.

    The two folders hold the same official files (the engine reads the first,
    the WinTOTAL MOD the second); a checkout or a deployment that carries only
    one of them still finds its samples and the subschema.
    """
    env = os.environ.get("UAD_SPEC_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    for p in (PROJECT_ROOT / "3.6 DEVELOPMENT, BLUEPRINT, DOCUMENTATION",
              PROJECT_ROOT / "specs" / "official"):
        if p.exists():
            return p.resolve()
    return (PROJECT_ROOT / "3.6 DEVELOPMENT, BLUEPRINT, DOCUMENTATION").resolve()


SPEC_ROOT = _spec_root()
