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


def test_interpreter(root: Path | str, configured: str = "") -> str:
    """The interpreter that runs the repository's tests: ``verify.python`` when set, else the
    repository's ``.venv`` when it exists, else the one plumb runs in. Under the plugin that
    last one is plumb's private environment, which has no pytest and none of the project's
    test dependencies, so a project with a ``.venv`` is run there."""
    if configured:
        local = Path(root) / configured
        return str(local) if not Path(configured).is_absolute() and local.exists() else configured
    for rel in ("Scripts/python.exe", "bin/python"):
        venv = Path(root) / ".venv" / rel
        if venv.exists():
            return str(venv)
    return sys.executable


def python_version() -> str:
    return f"{platform.python_implementation()} {platform.python_version()}"


def platform_name(root: Path | None = None) -> str:
    """``"<sys.platform> <machine>"``. ``platform.machine()`` runs a WMI query on Windows
    (about 0.2 s), so the answer is cached in ``.plumb/cache/platform.json`` per interpreter
    when ``root`` is an adopted repository."""
    import json

    key = f"{sys.executable}|{sys.version}"
    cache = Path(root) / ".plumb" / "cache" / "platform.json" if root is not None else None
    if cache is not None:
        try:
            data = json.loads(cache.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("key") == key and data.get("name"):
                return str(data["name"])
        except (OSError, ValueError):
            pass
    name = f"{sys.platform} {platform.machine()}"
    if cache is not None and cache.parent.parent.is_dir():
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"key": key, "name": name}), encoding="utf-8")
        except OSError:
            pass
    return name


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


def env_prefix(interpreter: str | None) -> str | None:
    """The venv directory of the TEST interpreter when it is not the one plumb runs in, else
    None. The tests run in that interpreter, so their evidence belongs to its environment: a
    hook that reaches plumb through another interpreter (the plugin launcher) must see the
    evidence a direct run recorded, and the reverse."""
    if not interpreter:
        return None
    try:
        exe = Path(interpreter).resolve()
        if exe == Path(sys.executable).resolve():
            return None
        prefix = exe.parent.parent
        return str(prefix) if (prefix / "pyvenv.cfg").is_file() else None
    except OSError:
        return None


def _cfg_value(prefix: str, *names: str) -> str | None:
    try:
        for line in (Path(prefix) / "pyvenv.cfg").read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep and key.strip().lower() in names and value.strip():
                return value.strip()
    except OSError:
        pass
    return None


def env_parts(root: Path, interpreter: str | None = None) -> dict[str, Any]:
    lock = Path(root) / "uv.lock"
    try:
        lock_hash = sha256_text(lock.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError):
        lock_hash = "no-lock"
    prefix = env_prefix(interpreter)
    version = _cfg_value(prefix, "version_info", "version") if prefix else None
    if prefix and version:
        implementation = _cfg_value(prefix, "implementation") or platform.python_implementation()
        python = f"{implementation} {version}"
    else:
        python = python_version()
    return {"lock": lock_hash, "python": python, "platform": platform_name(root),
            "home": venv_home(prefix)}


def env_key(root: Path, interpreter: str | None = None) -> str:
    return sha256_bytes(canonical_json(env_parts(root, interpreter)))


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


def _cache_key(key: str, prefix: str | None = None) -> str:
    """The env key plus the site-packages directory mtimes, so an install that leaves the
    lock untouched still invalidates the cached identity."""
    stamps = []
    for site in _site_packages(Path(prefix or sys.prefix)):
        try:
            stamps.append(str(site.stat().st_mtime_ns))
        except OSError:
            stamps.append("?")
    return key + "|" + ",".join(stamps)


def cached_identity(core: Any, key: str, *, compute: bool = False,
                    interpreter: str | None = None) -> str | None:
    """The identity cached under ``key`` in ``.plumb/cache/env_identity.json``; computed
    (about a second) only when ``compute`` is set, which happens when evidence is recorded."""
    import json

    path = core.paths.env_identity
    prefix = env_prefix(interpreter)
    ckey = _cache_key(key, prefix)
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
    value = (content_identity(Path(core.root), prefix) if prefix
             else content_identity(Path(core.root)))
    cache = {ckey: value}  # one environment at a time; older keys are dropped
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass
    return value
