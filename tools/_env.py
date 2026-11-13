# -*- coding: utf-8 -*-
"""Read the project's root `.env` file.

Hand-written rather than using `python-dotenv` so the tooling runs straight
after a clone with nothing to install. The whole file does one job: load
key-value pairs into `os.environ` unless they are already set.

A variable already present in the environment always wins over the `.env`
file. That way, running in CI or trying a different key quickly needs only an
environment variable, with no file to edit:

    USDA_API_KEY=abc python tools/fill_gaps_usda.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path | None = None) -> dict[str, str]:
    """Load `.env` into `os.environ`. Returns the keys it added."""
    env_path = path or ROOT / ".env"
    loaded: dict[str, str] = {}

    if not env_path.exists():
        return loaded

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")

        if not key or not value:
            continue
        # Never override a variable already present in the environment.
        if key in os.environ:
            continue

        os.environ[key] = value
        loaded[key] = value

    return loaded


def require(name: str, hint: str = "") -> str:
    """Fetch a required variable, failing with a clear message if it is absent."""
    load_env()
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(
            f"Missing environment variable {name}.\n"
            f"Copy .env.example to .env and fill in the values."
            + (f"\n{hint}" if hint else "")
        )
    return value


def get(name: str, default: str = "") -> str:
    """Fetch an optional variable."""
    load_env()
    return os.environ.get(name, default).strip() or default


def use_utf8() -> None:
    """Make stdout accept non-ASCII output on Windows (it defaults to cp1252).

    Without this call, every checker that prints a check mark, a cross or a
    box-drawing character **dies mid-run** with `UnicodeEncodeError` rather
    than printing the wrong character. Running directly in a console may hide
    it, because a modern Windows console is already utf-8; the failure only
    appears once output is redirected through a pipe or into a file — which
    is to say exactly when running in CI.

    Still needed after the English refactor, because the **data** stays
    Vietnamese: food names, condition names and rule notes are printed
    verbatim. Same function as `ml.db.use_utf8`; it lives in both places
    because `ml/` does not depend on `tools/`.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
        except Exception:  # pragma: no cover - unusual console
            pass
