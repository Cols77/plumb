"""Record texts and small git repositories for the MERGEDRIVER lane's tests (not a conftest).

The phase-0 ``tests/gitrepo.py`` was not on ``main`` when this lane started; these helpers
are the lane's own (sp6 plan 2) and never touch the plumb repository itself.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

KIND_DIRS = {"INT": "intents", "SR": "requirements", "DEC": "decisions", "FEAT": "features",
             "NC": "ncs"}


def record(record_id: str = "SR-005", title: str = "relay checks", body: str = "",
           **fields: Any) -> str:
    data = {"id": record_id, "title": title, **fields}
    return "---\n" + yaml.safe_dump(data, sort_keys=False, allow_unicode=True) + "---\n" + body


def parse(text: str) -> tuple[dict[str, Any], str]:
    from plumb.model import load_yaml, split_frontmatter

    head, body = split_frontmatter(text)
    return load_yaml(head), body


def ex(n: int, given: str = "g", when: str = "w", then: str = "t") -> dict[str, str]:
    return {"id": f"EX-{n}", "given": given, "when": when, "then": then}


def link(kind: str, *, to: str | None = None, path: str | None = None,
         example: str | None = None, pin: str | None = None) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": kind}
    if to:
        out["to"] = to
    if path:
        out["path"] = path
    if example:
        out["example"] = example
    if pin:
        out["pin"] = {"from": f"sha256:{pin}", "to": f"sha256:{pin}"}
    return out


class Counter:
    """A ``reserve_ic`` that hands out IC-001, IC-002, ..."""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"IC-{self.n:03d}"


def run_git(root: Path, *args: str, check: bool = True,
            env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=env)
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stdout}{result.stderr}")
    return result


def make_repo(path: Path) -> Path:
    """A git repository adopted by plumb, with one commit on ``main``."""
    from plumb.commands import init_repo

    path.mkdir(parents=True, exist_ok=True)
    run_git(path, "init", "-q", "-b", "main")
    run_git(path, "config", "user.email", "test@example.com")
    run_git(path, "config", "user.name", "Test")
    run_git(path, "config", "core.autocrlf", "false")
    init_repo(path)
    (path / "README.md").write_text("test repo\n", encoding="utf-8")
    commit_all(path, "initial")
    return path


def commit_all(root: Path, message: str) -> str:
    run_git(root, "add", "-A")
    run_git(root, "commit", "-q", "--no-verify", "-m", message)
    return run_git(root, "rev-parse", "HEAD").stdout.strip()


def write_record(root: Path, text: str) -> Path:
    record_id = parse(text)[0]["id"]
    path = root / ".plumb" / KIND_DIRS[record_id.split("-")[0]] / f"{record_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def install_driver(root: Path) -> None:
    from plumb.mergedriver import install

    install(root, launcher_for(sys.executable))


def launcher_for(interpreter: str) -> str:
    return f'"{interpreter.replace(chr(92), "/")}" -m plumb'


def plumb(root: Path, *args: str, stdin: str | None = None,
          env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run ``python -m plumb`` in a subprocess (UTF-8, no agent marker)."""
    base = {k: v for k, v in os.environ.items() if k != "PLUMB_AGENT_SESSION"}
    base["PYTHONUTF8"] = "1"
    base.update(env or {})
    return subprocess.run([sys.executable, "-m", "plumb", *args], cwd=root, input=stdin,
                          capture_output=True, text=True, encoding="utf-8", env=base)


# --------------------------------------------------------------------------- conflicts

OURS_STATEMENT = "A relay pins only the records the owner's words affirm."
THEIRS_STATEMENT = "A relay pins the stated group, named by its title."
BASE_STATEMENT = "A relay pins every stated record."


def conflicted(root: Path, *, ours: str | None = None, theirs: str | None = None,
               base: str | None = None, labels: tuple[str, str] = ("main", "feat-x")) -> str:
    """Write SR-005 holding an intent conflict (the driver's output) into ``root``; returns
    the IC. Defaults: the statement changed differently on both sides, theirs adds a link."""
    from plumb.mergedriver import merge_texts

    base = base or record(statement=BASE_STATEMENT, examples=[ex(1)])
    ours = ours or record(statement=OURS_STATEMENT, examples=[ex(1)])
    theirs = theirs or record(statement=THEIRS_STATEMENT, examples=[ex(1)],
                              links=[link("verified_by", path="tests/test_relay.py")])
    result = merge_texts(base, ours, theirs, labels=labels, reserve_ic=Counter())
    write_record(root, result.text)
    return str(result.conflict)


def log_prompt(root: Path, text: str, *, at: str = "2026-10-07T10:00:00Z",
               via: str | None = "hook") -> str:
    import hashlib
    import json

    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    path = root / ".plumb" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"digest": digest, "session": "test-session", "at": at, "text": text}
    if via is not None:
        entry["via"] = via
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry) + "\n")
    return digest


def events(root: Path, kind: str) -> list[dict]:
    from plumb.api import open_core

    return [e.payload for e in open_core(root).log_read("events", [kind])]
