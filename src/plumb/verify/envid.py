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


# -- the content identity (VS3) ----------------------------------------------------------
# Simplified from pi-agent-factory's ``environment_content_identity``: the lock, the base
# interpreter's bytes, and each installed distribution's name, version and normalized
# RECORD digest. Unknown (None) when the environment is not a venv or cannot be read.


def _site_packages(prefix: Path) -> list[Path]:
    win = prefix / "Lib" / "site-packages"
    if win.is_dir():
        return [win]
    return sorted(p for p in (prefix / "lib").glob("python*/site-packages") if p.is_dir())


def _base_interpreter(home: str) -> str | None:
    import hashlib

    base = Path(home)
    for name in ("python.exe", "python3", "python"):
        exe = base / name
        if exe.is_file():
            digest = hashlib.sha256()
            for part in [exe, *sorted(base.glob("python3*.dll"))]:  # Windows: the runtime DLL
                digest.update(part.name.encode() + b"\x00")
                with open(part, "rb") as handle:
                    for block in iter(lambda h=handle: h.read(1 << 20), b""):
                        digest.update(block)
            return "sha256:" + digest.hexdigest()
    return None


def _metadata(info: Path) -> tuple[str, str] | None:
    name = version = None
    with open(info / "METADATA", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line.strip():
                break
            key, sep, value = line.partition(":")
            if sep and key == "Name":
                name = value.strip()
            elif sep and key == "Version":
                version = value.strip()
    if not name or not version:
        return None
    return name.lower().replace("_", "-").replace(".", "-"), version


def _record_digest(info: Path) -> str:
    rows = []
    for line in (info / "RECORD").read_text(encoding="utf-8").splitlines():
        path = line.split(",", 1)[0].replace("\\", "/")
        if not path or path.endswith(".pyc") or "/__pycache__/" in f"/{path}":
            continue
        rows.append(line.replace("\\", "/"))
    return sha256_bytes(canonical_json(sorted(rows)))


def content_identity(root: Path, prefix: str | None = None) -> str | None:
    """Content identity of the running environment, or None when it is unknown."""
    venv = Path(prefix or sys.prefix)
    home = venv_home(str(venv))
    if home == "none":
        return None
    try:
        base = _base_interpreter(home)
        if base is None:
            return None
        sites = _site_packages(venv)
        if not sites:
            return None
        dists: dict[str, list[str]] = {}
        for site in sites:
            for info in sorted(site.glob("*.dist-info")):
                meta = _metadata(info)
                if meta is None:
                    return None
                dists[meta[0]] = [meta[1], _record_digest(info)]
    except (OSError, UnicodeError):
        return None
    lock = env_parts(Path(root))["lock"]
    return sha256_bytes(canonical_json({"lock": lock, "base_interpreter": base,
                                        "distributions": dists}))


def _cache_key(key: str) -> str:
    """The env key plus the site-packages directory mtimes, so an install that leaves the
    lock untouched still invalidates the cached identity."""
    stamps = []
    for site in _site_packages(Path(sys.prefix)):
        try:
            stamps.append(str(site.stat().st_mtime_ns))
        except OSError:
            stamps.append("?")
    return key + "|" + ",".join(stamps)


def cached_identity(core: Any, key: str, *, compute: bool = False) -> str | None:
    """The identity cached under ``key`` in ``.plumb/cache/env_identity.json``; computed
    (about a second) only when ``compute`` is set, which happens when evidence is recorded."""
    import json

    path = core.paths.env_identity
    ckey = _cache_key(key)
    try:
        cache = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(cache, dict):
            cache = {}
    except (OSError, ValueError):
        cache = {}
    if ckey in cache:
        return cache[ckey]
    if not compute:
        return None
    value = content_identity(Path(core.root))
    cache = {ckey: value}  # one environment at a time; older keys are dropped
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return value
