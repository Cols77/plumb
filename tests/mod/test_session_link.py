"""SR-125: the session-start hook says which interpreter runs plumb (``host.json``) before any
step its budget can cut, so plumb's panel can always reach plumb; the brief's decision
(``brief.json``) is made at the same moment and a cut later in the hook changes neither.

EX-1 the check cut by its budget (a raised budget and the watchdog's hard exit): host.json
names the interpreter. EX-2 the older per-repository hooks run the same handler with the
repository's interpreter, which host.json then names. EX-3 host.json cannot be written: the
hook still answers."""

from __future__ import annotations

import io
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from mod.helpers import DIGEST, SESSION, run_mod
from plumb.hosts.claude_code import hookio, session_start
from plumb.mod import handshake

pytestmark = pytest.mark.sr("SR-264")


def _host(root: Path) -> dict | None:
    path = root / ".plumb" / "session" / SESSION / "host.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _brief(root: Path) -> dict | None:
    path = root / ".plumb" / "session" / SESSION / "brief.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def _start(root: Path, hook_input) -> str:
    out = io.StringIO()
    payload = hook_input("SessionStart", session_id=SESSION, source="startup")
    assert session_start.main(stdin=io.StringIO(payload), stdout=out, root=root,
                              verify=None) == 0
    return out.getvalue()


def _cut(monkeypatch, *, keep: list[str] | None = None) -> None:
    """The hook's slow part cut by its budget, after keeping ``keep`` (the records brief)."""

    def cut(ctx, verify, timer):
        if keep:
            ctx.keep(keep)
        raise hookio.BudgetExceeded("tests")

    monkeypatch.setattr(session_start, "_handle", cut)


def test_a_check_cut_by_its_budget_still_names_the_interpreter(repo, monkeypatch,
                                                                hook_input) -> None:
    _cut(monkeypatch, keep=["plumb: the records brief"])
    out = _start(repo, hook_input)
    assert hookio.SKIP_BUDGET in out and "the records brief" in out  # the cut, as before
    host = _host(repo)
    assert host is not None and host["python"] == sys.executable
    assert _brief(repo) == {"injected": True}


def test_the_watchdog_hard_exit_still_leaves_host_json(repo, hook_input) -> None:
    """The hook process killed by its watchdog (``os._exit``) mid-check, as on a slow start."""
    script = textwrap.dedent(f"""
        import io, sys, time
        from plumb.hosts.claude_code import hookio, session_start
        hookio.HARD_LIMIT_S = 1.5  # past the steps before the handler, even on a loaded machine
        def slow(ctx, verify, timer):
            ctx.keep(["plumb: the records brief"])
            time.sleep(30)
        session_start._handle = slow
        payload = {hook_input("SessionStart", session_id=SESSION, source="startup")!r}
        session_start.main(stdin=io.StringIO(payload), root={str(repo)!r}, watchdog=True,
                           verify=None)
        print("not cut")
    """)
    ran = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                         timeout=60, check=False)
    assert ran.returncode == 0
    assert hookio.SKIP_BUDGET in ran.stdout and "not cut" not in ran.stdout
    host = _host(repo)
    assert host is not None and Path(host["python"]).exists()
    assert _brief(repo) == {"injected": True}


@pytest.mark.sr("SR-266")
def test_a_cut_still_prints_the_brief_while_the_panel_owns_the_background(
        repo, monkeypatch, capsys, hook_input) -> None:
    assert run_mod(monkeypatch, capsys, repo, "hello", stdin={"key_digest": DIGEST})[0] == 0
    held = handshake.registration(repo, SESSION)
    (repo / ".plumb" / "session" / SESSION / "mod.json").write_text(
        json.dumps({**dict(held or {}), "background": True}), encoding="utf-8")
    _cut(monkeypatch, keep=["plumb: the records brief"])
    out = _start(repo, hook_input)
    assert "the records brief" in out              # SR-266 EX-1: the agent keeps the brief
    assert _brief(repo) == {"injected": True}
    assert _host(repo) is not None


def test_the_interpreter_named_is_the_one_the_hook_runs_with(repo, monkeypatch,
                                                             hook_input) -> None:
    """EX-2: the older per-repository hooks run this handler with the repository's interpreter;
    host.json names whichever interpreter ran the hook."""
    venv_python = repo / ".venv" / "Scripts" / "python.exe"
    monkeypatch.setattr(sys, "executable", str(venv_python))
    _start(repo, hook_input)
    assert _host(repo)["python"] == str(venv_python)


def test_host_json_that_cannot_be_written_fails_nothing(repo, monkeypatch, hook_input) -> None:
    real = handshake.files.write_json_atomic

    def refuse(path, data):
        if Path(path).name == "host.json":
            raise PermissionError("read-only")
        return real(path, data)

    monkeypatch.setattr(handshake.files, "write_json_atomic", refuse)
    out = _start(repo, hook_input)
    assert out.strip() and hookio.SKIP_ERROR not in out  # the brief, as without the panel
    assert _host(repo) is None
    assert _brief(repo) == {"injected": True}
