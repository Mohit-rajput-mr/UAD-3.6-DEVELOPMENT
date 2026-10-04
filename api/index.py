"""Vercel entry point: the UAD 3.6 report platform (engine/app) as one ASGI function.

Vercel's Python runtime serves the module-level ``app``.  Everything else --
what works without a browser, where cases live, the passcode -- is decided in
engine/app/main.py from the ``VERCEL`` environment variable.  See DEPLOY_VERCEL.md.
"""
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1] / "engine"
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from app.main import app  # noqa: E402,F401
