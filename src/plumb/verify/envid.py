"""The cheap environment key (spec 7.4).

``env_key``: sha256 of the LF-normalized ``uv.lock`` (or ``no-lock``), the Python version,
the platform and the ``home`` of ``pyvenv.cfg``. Cheap enough to compute on every run.
The content identity (lock, interpreter bytes, distributions) is the SHOULD item VS3 and is
not part of this build; payloads omit the ``identity`` key.
"""

from __future__ import annotations

import platform
import sys
from pathlib import Path
from typing import Any

from plumb.normalize import canonical_json, sha256_bytes, sha256_text


def python_version() -> str:
    return f"{platform.python_implementation()} {platform.python_version()}"


def platform_name() -> str:
    return f"{sys.platform} {platform.machine()}"


def venv_home(prefix: str | None = None) -> str:
    cfg = Path(prefix or sys.prefix) / "pyvenv.cfg"
    try:
        for line in cfg.read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().lower() == "home":
                return value.strip()
    except OSError:
        pass
    return "none"


def env_parts(root: Path) -> dict[str, Any]:
    lock = Path(root) / "uv.lock"
    try:
        lock_hash = sha256_text(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        lock_hash = "no-lock"
    return {"lock": lock_hash, "python": python_version(), "platform": platform_name(),
            "home": venv_home()}


def env_key(root: Path) -> str:
    return sha256_bytes(canonical_json(env_parts(root)))
