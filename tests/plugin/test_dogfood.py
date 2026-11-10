"""SR-315: in iaso's own repository (or one of its worktrees) the plugin's hooks run that
checkout's code; elsewhere they run the plugin's packaged copy."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.plugin.helpers import (
    hook_data,
    needs_sh,
    ready_home,
    recording_python,
    run_hook,
    slashes,
    write_script,
    env_with,
)

pytestmark = [needs_sh, pytest.mark.sr("SR-315")]


def iaso_checkout(root: Path) -> Path:
    """A folder shaped like iaso's own repository: records, iaso's source and the plugin."""
    (root / ".iaso").mkdir(parents=True)
    (root / ".iaso" / "config.yaml").write_text("{}\n", encoding="utf-8")
    (root / "src" / "iaso").mkdir(parents=True)
    (root / "src" / "iaso" / "__main__.py").write_text("", encoding="utf-8")
    (root / "plugin" / ".claude-plugin").mkdir(parents=True)
    (root / "plugin" / ".claude-plugin" / "plugin.json").write_text("{}", encoding="utf-8")
    return root


def checkout_python(venv: Path, log: Path) -> Path:
    """The checkout's own interpreter, faked: records its arguments and PYTHONPATH."""
    return write_script(venv / "bin" / "python", (
        f'printf "argv:%s\\n" "$*" >> "{slashes(log)}"\n'
        f'printf "pythonpath:%s\\n" "$PYTHONPATH" >> "{slashes(log)}"\n'
        "cat > /dev/null\n"))


def bundled(tmp_path: Path) -> tuple[dict[str, str], Path]:
    log = tmp_path / "bundled.log"
    python = recording_python(tmp_path / "env" / "python", log)
    home = ready_home(tmp_path / "home", python)
    return env_with(IASO_HOME=slashes(home)), log


def test_ex3_own_checkout_runs_its_own_code(tmp_path: Path) -> None:
    root = iaso_checkout(tmp_path / "iaso")
    log = tmp_path / "checkout.log"
    checkout_python(root / ".venv", log)
    env, bundled_log = bundled(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    run_hook("prompt", root, hook_data("prompt"), env)
    text = log.read_text(encoding="utf-8")
    assert "argv:-m iaso hook prompt" in text
    assert f"pythonpath:{slashes(root / 'src')}" in text
    assert not bundled_log.exists()


def test_ex4_worktree_runs_the_worktrees_code(tmp_path: Path) -> None:
    main = iaso_checkout(tmp_path / "iaso")
    log = tmp_path / "checkout.log"
    checkout_python(main / ".venv", log)
    (main / ".git" / "worktrees" / "wt").mkdir(parents=True)
    tree = iaso_checkout(tmp_path / "wt")
    (tree / ".git").write_text(f"gitdir: {slashes(main / '.git' / 'worktrees' / 'wt')}\n",
                               encoding="utf-8")
    env, bundled_log = bundled(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = slashes(tree)
    run_hook("stop", tree, hook_data("stop"), env)
    text = log.read_text(encoding="utf-8")
    assert "argv:-m iaso hook stop" in text
    assert f"pythonpath:{slashes(tree / 'src')}" in text
    assert not bundled_log.exists()


def test_ex5_another_project_runs_the_packaged_copy(tmp_path: Path) -> None:
    root = tmp_path / "app"
    (root / ".iaso").mkdir(parents=True)
    (root / ".iaso" / "config.yaml").write_text("{}\n", encoding="utf-8")
    log = tmp_path / "checkout.log"
    checkout_python(root / ".venv", log)
    env, bundled_log = bundled(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    run_hook("prompt", root, hook_data("prompt"), env)
    assert "argv:-m iaso hook prompt" in bundled_log.read_text(encoding="utf-8")
    assert not log.exists()


@pytest.mark.parametrize("event", ["session-start", "prompt"])
def test_ex6_checkout_without_an_environment_falls_back_and_says_so(tmp_path: Path,
                                                                     event: str) -> None:
    root = iaso_checkout(tmp_path / "iaso")
    env, bundled_log = bundled(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    result = run_hook(event, root, hook_data(event), env)
    assert f"argv:-m iaso hook {event}" in bundled_log.read_text(encoding="utf-8")
    assert "packaged copy" in result.stdout


def test_ex6_checkout_that_cannot_start_falls_back_and_says_so(tmp_path: Path) -> None:
    root = iaso_checkout(tmp_path / "iaso")
    write_script(root / ".venv" / "bin" / "python",
                 'echo "partial" ; echo "ImportError" >&2 ; cat > /dev/null ; exit 1')
    env, bundled_log = bundled(tmp_path)
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    result = run_hook("prompt", root, hook_data("prompt"), env)
    assert result.returncode == 0
    assert "argv:-m iaso hook prompt" in bundled_log.read_text(encoding="utf-8")
    assert "packaged copy" in result.stdout
    assert "partial" not in result.stdout


def broken_checkout(tmp_path: Path) -> Path:
    root = iaso_checkout(tmp_path / "iaso")
    write_script(root / ".venv" / "bin" / "python", "cat > /dev/null ; exit 1")
    return root


def printing_bundled(tmp_path: Path, output: str) -> dict[str, str]:
    """A packaged copy that prints ``output``."""
    python = write_script(tmp_path / "env" / "python",
                          f"cat > /dev/null\nprintf '%s\\n' '{output}'")
    home = ready_home(tmp_path / "home", python)
    return env_with(IASO_HOME=slashes(home))


def test_ex6_the_notice_joins_the_packaged_copys_text(tmp_path: Path) -> None:
    root = broken_checkout(tmp_path)
    env = printing_bundled(tmp_path, "iaso: two records waiting")
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    out = run_hook("prompt", root, hook_data("prompt"), env).stdout
    assert "iaso: two records waiting" in out and "packaged copy" in out


def test_ex6_the_notice_joins_the_packaged_copys_json(tmp_path: Path) -> None:
    import json

    root = broken_checkout(tmp_path)
    env = printing_bundled(tmp_path, json.dumps({"hookSpecificOutput": {
        "hookEventName": "UserPromptSubmit", "additionalContext": "iaso: SR-1 changed"}}))
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    out = json.loads(run_hook("prompt", root, hook_data("prompt"), env).stdout)
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "packaged copy" in context and "iaso: SR-1 changed" in context


def test_ex6_the_notice_joins_a_json_answer_without_context(tmp_path: Path) -> None:
    import json

    root = broken_checkout(tmp_path)
    env = printing_bundled(tmp_path, json.dumps({"decision": "block", "reason": "stale"}))
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    out = json.loads(run_hook("stop", root, hook_data("stop"), env).stdout)
    assert out["decision"] == "block" and "packaged copy" in out["systemMessage"]


def test_ex6_no_packaged_copy_either_still_says_so(tmp_path: Path) -> None:
    root = broken_checkout(tmp_path)
    env = env_with(IASO_HOME=slashes(tmp_path / "empty-home"))
    env["CLAUDE_PROJECT_DIR"] = slashes(root)
    out = run_hook("prompt", root, hook_data("prompt"), env).stdout
    assert "failed to start" in out and "not ready" in out
