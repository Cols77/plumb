"""Record texts and small git repositories for the MERGEDRIVER lane's tests (not a conftest).

The phase-0 ``tests/gitrepo.py`` was not on ``main`` when this lane started; these helpers
are the lane's own (sp6 plan 2) and never touch the iaso repository itself.
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
    from iaso.model import load_yaml, split_frontmatter

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
    """A git repository adopted by iaso, with one commit on ``main``."""
    from iaso.commands import init_repo

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
    path = root / ".iaso" / KIND_DIRS[record_id.split("-")[0]] / f"{record_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def install_driver(root: Path) -> None:
    from iaso.mergedriver import install

    install(root, launcher_for(sys.executable))


def launcher_for(interpreter: str) -> str:
    return f'"{interpreter.replace(chr(92), "/")}" -m iaso'


def iaso(root: Path, *args: str, stdin: str | None = None,
          env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    """Run ``python -m iaso`` in a subprocess (UTF-8, no agent marker)."""
    base = {k: v for k, v in os.environ.items() if k != "IASO_AGENT_SESSION"}
    base["PYTHONUTF8"] = "1"
    base.update(env or {})
    return subprocess.run([sys.executable, "-m", "iaso", *args], cwd=root, input=stdin,
                          capture_output=True, text=True, encoding="utf-8", env=base)


# --------------------------------------------------------------------------- conflicts

OURS_STATEMENT = "A relay pins only the records the owner's words affirm."
THEIRS_STATEMENT = "A relay pins the stated group, named by its title."
BASE_STATEMENT = "A relay pins every stated record."


def conflicted(root: Path, *, ours: str | None = None, theirs: str | None = None,
               base: str | None = None, labels: tuple[str, str] = ("main", "feat-x")) -> str:
    """Write SR-005 holding an intent conflict (the driver's output) into ``root``; returns
    the IC. Defaults: the statement changed differently on both sides, theirs adds a link."""
    from iaso.mergedriver import merge_texts

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
    path = root / ".iaso" / "session" / "prompts.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {"digest": digest, "session": "test-session", "at": at, "text": text}
    if via is not None:
        entry["via"] = via
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry) + "\n")
    return digest


def write_stated_conflicts(root: Path, entries: list[dict], *,
                           at: str = "2026-10-07T09:59:00Z") -> None:
    import json

    path = root / ".iaso" / "session" / "stated.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"at": at, "records": [], "conflicts": entries}),
                    encoding="utf-8")


def shown(root: Path) -> None:
    """The stop hook showed every open conflict card in the reply before the prompt."""
    from iaso.api import open_core
    from iaso.mergedriver import open_conflicts, stated_entries

    core = open_core(root)
    write_stated_conflicts(root, stated_entries(core, [c.ic for c in open_conflicts(core)]))


def events(root: Path, kind: str) -> list[dict]:
    from iaso.api import open_core

    return [e.payload for e in open_core(root).log_read("events", [kind])]


def reads(monkeypatch: Any, root: Path, answer: str, evidence: str, change: str | None = None,
          *, record_id: str = "SR-005", confidence: float = 0.95) -> None:
    """A stubbed model reading of the owner's message against the conflict card: ''answer''
    (accepted, rejected, change, open), ''change'' and the words that carry it."""
    import json

    script = root.parent / "reading.json"
    script.write_text(json.dumps({"read": {"entries": [{
        "id": record_id, "hash": "", "answer": answer, "change": change,
        "evidence": evidence, "confidence": confidence}]}}), encoding="utf-8")
    monkeypatch.setenv("IASO_FAKE_DISPATCH", str(script))


def unreachable(monkeypatch: Any, root: Path) -> None:
    """The model that reads the owner's words cannot be reached."""
    import json

    script = root.parent / "reading.json"
    script.write_text(json.dumps({"read": {"error": "the model could not be reached"}}),
                      encoding="utf-8")
    monkeypatch.setenv("IASO_FAKE_DISPATCH", str(script))


def reads_keep(monkeypatch: Any, root: Path, take: str, evidence: str) -> None:
    """A stubbed model reading of the owner's words as keeping one side of the open conflict
    (``ours`` or ``theirs``), with no change asked."""
    from iaso.api import open_core
    from iaso.mergedriver import open_conflicts

    (conflict,) = open_conflicts(open_core(root))
    label = conflict.labels[0 if take == "ours" else 1]
    reads(monkeypatch, root, "change", evidence, f"Keep {label}'s version",
          record_id=conflict.record)
