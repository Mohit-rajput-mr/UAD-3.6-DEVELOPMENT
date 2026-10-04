"""Where the official GSE specification files live.

``UAD36_SPECS`` overrides; otherwise this repository's ``specs/official``
(the portable-XML repository ships them); otherwise the original development
location.  Nothing else may hard-code the path.
"""
from __future__ import annotations

import os
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
_DEV = Path(r"C:\3.6 uad zips\_UNZIPPED_ALL")


def specs_root() -> Path:
    env = os.environ.get("UAD36_SPECS")
    if env:
        return Path(env)
    here = REPO / "specs" / "official"
    return here if here.exists() else _DEV
