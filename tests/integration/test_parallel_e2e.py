"""End-to-end: parallel work in two real worktrees (SP6 spec 14 items 2 and 3, R10, R17).

A temporary repository is adopted with ``iaso init``, which also sets up the record merge
driver and the quick merge check in git. It holds one feature, one intent and one confirmed
requirement, SR-001 "relay checks". Two worktrees, ``feat-a`` and ``feat-b``, then work at
once, driven through iaso's CLI and its real hook commands (each its own process, with the
JSON Claude Code sends):

1. each proposes a new requirement: the IDs are distinct (``refs/iaso/ids``);
2. each changes SR-001's statement differently and adds its own link from it; the
   session-start hook and the prompt hook of each worktree warn, in the owner's terms, that
   SR-001 is also being changed on the other branch;
3. ``main`` merges ``feat-a`` (the owner confirmed its records there), then ``feat-b``: the
   new requirement and both links land on their own; the two statements become one intent
   conflict, which git's pre-merge-commit hook holds (no merge commit). Once the agent has
   repinned the links whose source the merge changed, ``iaso merge-check`` reports exit 4
   with the conflict card: the merge waits for the owner, and nothing is chosen for him.
   The owner's choice, in his own terminal, then settles it: the check no longer lists it.

A second scenario covers clones (spec 14 item 3): a clone and its origin both create
SR-002; the merge stops on the add/add, and ``iaso merge-fix`` renumbers the incoming
record, carries the clone owner's ok of its unchanged words and leaves history untouched.

Every owner-visible SP6 text captured here names no bare ``iaso <verb>`` (spec 11.1, R14).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from iaso.present.owner_text import bare_cli_verbs

pytestmark = [pytest.mark.sr(sr) for sr in (
    "SR-070", "SR-071", "SR-072", "SR-073", "SR-075", "SR-076", "SR-077", "SR-078",
    "SR-079")]

BASE_STATEMENT = "A relay pins every stated record."
A_STATEMENT = "A relay pins only the records the owner's words affirm."
B_STATEMENT = "A relay pins the stated group, named by its title."
OVERLAP_A = 'SR-001 "relay checks" is also being changed on branch feat-a'
OVERLAP_B = 'SR-001 "relay checks" is also being changed on branch feat-b'


def _env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "IASO_AGENT_SESSION"}
    env["PYTHONUTF8"] = "1"
    return env


def git(root: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                            encoding="utf-8", errors="replace", env=_env())
    if check and result.returncode != 0:
        raise AssertionError(f"git {' '.join(args)}: {result.stdout}{result.stderr}")
    return result


def iaso(root: Path, *args: str, stdin: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "iaso", *args], cwd=root, input=stdin,
                          capture_output=True, text=True, encoding="utf-8", env=_env())


def ok(root: Path, *args: str) -> str:
    result = iaso(root, *args)
    assert result.returncode == 0, f"iaso {' '.join(args)}: {result.stdout}{result.stderr}"
    return result.stdout


def hook(root: Path, event: str, name: str, **fields: object) -> str:
    """One hook command as Claude Code runs it: its own process, the event JSON on stdin."""
    data = {"session_id": f"session-{root.name}", "transcript_path": "", "cwd": str(root),
            "hook_event_name": name, **fields}
    result = iaso(root, "hook", event, "--root", str(root), stdin=json.dumps(data))
    assert result.returncode in (0, 2), f"{event}: {result.stdout}{result.stderr}"
    return result.stdout + result.stderr


def commit(root: Path, message: str) -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "--no-verify", "-m", message)


def new_requirement(root: Path, title: str, statement: str) -> str:
    out = json.loads(ok(root, "new", "requirement", "--title", title, "--statement", statement,
                        "--feature", "FEAT-001", "--json"))
    return str(out.get("id") or out["record"]["id"])


def change_statement(root: Path, statement: str) -> None:
    """The agent edits SR-001 with its Edit tool; the PostToolUse hook notes the path."""
    path = root / ".iaso" / "requirements" / "SR-001.md"
    path.write_text(path.read_text(encoding="utf-8").replace(BASE_STATEMENT, statement),
                    encoding="utf-8")
    hook(root, "post-edit", "PostToolUse", tool_name="Edit",
         tool_input={"file_path": str(path)})


def frontmatter(path: Path) -> dict:
    from iaso.model import load_yaml, split_frontmatter

    return load_yaml(split_frontmatter(path.read_text(encoding="utf-8"))[0])


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "main"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    for key, value in (("user.email", "test@example.com"), ("user.name", "Test"),
                       ("core.autocrlf", "false")):
        git(root, "config", key, value)
    init = ok(root, "init")
    assert "record merge driver" in init or "merged field by field" in init, init
    assert "no test run" in init, init                       # the quick merge check (R17)
    assert bare_cli_verbs(init) == []
    ok(root, "new", "feature", "--title", "Relays", "--description", "Relaying the owner's ok")
    ok(root, "new", "intent", "--title", "relay intent", "--quote", "relay my ok",
       "--readback", "Relay the owner's ok to the records it names.")
    ok(root, "new", "requirement", "--title", "relay checks", "--statement", BASE_STATEMENT,
       "--feature", "FEAT-001")
    from iaso.api import open_core
    from iaso.approvals import approve

    approve(open_core(root), ["SR-001"])                     # the owner, in the terminal
    commit(root, "relay records\n\nSR: SR-001")
    return root


def test_two_worktrees_propose_change_and_merge(repo: Path, tmp_path: Path) -> None:
    wt_a = tmp_path / "wt-a"
    wt_b = tmp_path / "wt-b"
    git(repo, "worktree", "add", "-q", "-b", "feat-a", str(wt_a))
    git(repo, "worktree", "add", "-q", "-b", "feat-b", str(wt_b))
    hook(wt_a, "session-start", "SessionStart", source="startup")
    hook(wt_b, "session-start", "SessionStart", source="startup")

    # 1. both propose a new requirement at once: never one ID twice (SR-070)
    sr_a = new_requirement(wt_a, "relay names records by title", "A relay names each record.")
    sr_b = new_requirement(wt_b, "relay shows the group", "A relay shows the stated group.")
    assert {sr_a, sr_b} == {"SR-002", "SR-003"}, (sr_a, sr_b)

    # 2. both change SR-001 and each adds its own link from it
    change_statement(wt_a, A_STATEMENT)
    ok(wt_a, "link", "SR-001", "relates_to", sr_a)
    stop_a = hook(wt_a, "stop", "Stop", stop_hook_active=True)   # publishes what a changes
    change_statement(wt_b, B_STATEMENT)
    ok(wt_b, "link", "SR-001", "relates_to", sr_b)
    stop_b = hook(wt_b, "stop", "Stop", stop_hook_active=True)

    # the awareness warnings, once per session, in the owner's terms (SR-078)
    brief_b = hook(wt_b, "session-start", "SessionStart", source="startup")
    assert OVERLAP_A in brief_b, brief_b
    prompt_a = hook(wt_a, "prompt", "UserPromptSubmit", prompt="tighten SR-001 relay checks")
    assert OVERLAP_B in prompt_a + stop_a, prompt_a + stop_a
    again = hook(wt_a, "prompt", "UserPromptSubmit", prompt="and SR-001 once more")
    assert OVERLAP_B not in again, again                    # said once, until it changes
    awareness = [line for line in (brief_b + prompt_a + stop_a + stop_b).splitlines()
                 if "also being changed" in line]
    assert awareness and all(bare_cli_verbs(line) == [] for line in awareness), awareness
    status = ok(wt_b, "status")
    assert "feat-a" in status, status

    from iaso.api import open_core
    from iaso.approvals import approve

    approve(open_core(wt_a), ["SR-001", sr_a])               # the owner confirms feat-a's work
    # no SR trailers: the records are touched by their files, and a trailer would deliver
    # requirements whose proofs hold a merge into main (SR-260, DEC-256)
    commit(wt_a, "relay affirms")
    commit(wt_b, "relay groups")

    # 3. merge feat-a: clean, and git records it (the quick check holds nothing)
    merged_a = git(repo, "merge", "--no-ff", "--no-edit", "feat-a", check=False)
    assert merged_a.returncode == 0, merged_a.stdout + merged_a.stderr
    before = git(repo, "rev-parse", "HEAD").stdout.strip()

    # merge feat-b: the record driver merges field by field; the statements clash
    merged_b = git(repo, "merge", "--no-ff", "--no-edit", "feat-b", check=False)
    output = merged_b.stdout + merged_b.stderr
    assert merged_b.returncode != 0, output                  # held before git records it
    assert git(repo, "rev-parse", "HEAD").stdout.strip() == before
    assert git(repo, "rev-parse", "-q", "--verify", "MERGE_HEAD").stdout.strip()
    assert "/iaso conflicts" in output and "no test run" in output, output
    assert bare_cli_verbs(output) == [], output
    assert git(repo, "ls-files", "-u", "--", ".iaso").stdout == ""   # nothing unmerged

    records = repo / ".iaso" / "requirements"
    assert (records / f"{sr_a}.md").is_file() and (records / f"{sr_b}.md").is_file()
    sr1 = frontmatter(records / "SR-001.md")
    targets = {(link.get("kind"), link.get("to")) for link in sr1.get("links") or []}
    assert {("relates_to", sr_a), ("relates_to", sr_b)} <= targets, sr1.get("links")
    feature = frontmatter(repo / ".iaso" / "features" / "FEAT-001.md")
    assert {sr_a, sr_b} <= set(feature.get("requirements") or [sr_a, sr_b])
    assert "conflict" in sr1, sr1                            # the clash, an intent conflict

    # SR-001's content changed in the merge, so its links' pins and the early decision's
    # pin on it show stale (spec 7.3); the agent reviews them and repins (never a
    # confirmation). The conflict is the owner's.
    held = iaso(repo, "merge-check", "main", "--no-run")
    assert held.returncode == 1 and "stale link SR-001" in held.stdout, held.stdout
    ok(repo, "repin", "--all-stale", "--note", "reviewed after the merge")
    check = iaso(repo, "merge-check", "main", "--no-run")
    assert check.returncode == 4, check.stdout + check.stderr   # waits for the owner
    assert "intent conflicts wait for your choice (/iaso conflicts):" in check.stdout
    assert "IC-001 on \"relay checks\"" in check.stdout and "on SR-001" not in check.stdout, check.stdout
    assert A_STATEMENT in check.stdout and B_STATEMENT in check.stdout, check.stdout
    data = json.loads(iaso(repo, "merge-check", "main", "--no-run", "--json").stdout)
    data = data.get("merge", data)
    assert [c["record"] for c in data["intent_conflicts"]] == ["SR-001"]
    assert data["id_collisions"] == [] and data["unmerged"] == []
    conflict_lines = [line for line in check.stdout.splitlines()
                      if "conflict" in line.lower() or line.startswith("  Say")]
    assert all(bare_cli_verbs(line) == [] for line in conflict_lines), conflict_lines

    conflicts = ok(repo, "conflicts")
    assert "awaits the owner's choice" in conflicts, conflicts
    assert bare_cli_verbs(conflicts) == [], conflicts
    status = open_core(repo).status(["SR-001"])["SR-001"]
    assert status.confirmation != "confirmed"                # no side is chosen for the owner

    # the owner chooses a side in his own terminal (spec 14 item 2): the conflict is gone
    from iaso import cli

    assert cli.main(["conflict", "choose", "IC-001", "--take", "feat-b",
                     "--root", str(repo)]) == 0
    sr1 = frontmatter(records / "SR-001.md")
    assert "conflict" not in sr1 and sr1["statement"] == B_STATEMENT, sr1
    after = json.loads(iaso(repo, "merge-check", "main", "--no-run", "--json").stdout)
    after = after.get("merge", after)
    assert after["intent_conflicts"] == [], after["intent_conflicts"]


def test_clone_collision_is_renumbered_at_merge(tmp_path: Path) -> None:
    """Spec 14 item 3: a clone and its origin both create SR-002; the merge stops on the
    add/add; merge-fix renumbers the incoming record, carries the clone owner's ok of its
    unchanged words, and the merge boundary shows no collision, all through the CLI."""
    from ids import scenario

    s = scenario.build(tmp_path)                             # merge stopped on SR-002
    held = iaso(s.origin, "merge-check", "main", "--no-run", "--json")
    data = json.loads(held.stdout)
    data = data.get("merge", data)
    assert [c["id"] for c in data["id_collisions"]] == ["SR-002"], data["id_collisions"]
    fixed = iaso(s.origin, "merge-fix")
    assert fixed.returncode == 0, fixed.stdout + fixed.stderr
    assert '"export csv"' in fixed.stdout and "SR-003" in fixed.stdout, fixed.stdout
    assert "approval carried" in fixed.stdout, fixed.stdout
    assert bare_cli_verbs(fixed.stdout) == [], fixed.stdout
    from iaso.api import open_core

    core = open_core(s.origin)
    assert core.index()["SR-003"].title == "export csv"
    assert core.status(["SR-003"])["SR-003"].carried_from == "SR-002"
    after = json.loads(iaso(s.origin, "merge-check", "main", "--no-run", "--json").stdout)
    after = after.get("merge", after)
    assert after["id_collisions"] == [] and after["unmerged"] == []
    assert git(s.clone, "log", "--format=%H %B", "main").stdout == s.clone_log  # history
