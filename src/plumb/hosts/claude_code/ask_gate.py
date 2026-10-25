"""SR-361 EX-6: the ask gate. While judge questions are open and the agent has not asked them,
edits and writing shell commands are refused until it asks them through the question tool;
reads, the question tool and ``plumb question reword|pushback`` / ``plumb clarify`` stay open,
so the agent can still read and put the questions in the owner's words.

It never stalls a turn: it opens once the agent called the question tool (answered or
dismissed), and it never closes where the tool is missing: a subagent's call (``agent_id``),
or a session nobody attends (``CLAUDE_CODE_SESSION_ATTENDED`` not ``1``: headless)."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

WRITE_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
REASON = ("plumb: {n} judge question{s} wait for the owner and {verb} not been asked: run "
          "`plumb clarify --wait --json` and ask them now with the question tool (reword, merge, "
          "push back; never drop one). Reading stays open; edits and writing commands wait.")

READ_COMMANDS = frozenset({
    "cat", "head", "tail", "less", "ls", "dir", "pwd", "echo", "printf", "grep", "rg", "egrep",
    "wc", "sort", "uniq", "cut", "tr", "diff", "file", "stat", "which", "type", "true", "date",
    "basename", "dirname", "realpath", "tree", "jq", "env", "test", "[", "sleep"})
GIT_READ = frozenset({"status", "log", "diff", "show", "rev-parse", "ls-files", "blame", "grep",
                      "branch", "describe", "shortlog", "cat-file", "ls-tree", "merge-base",
                      "remote", "config", "worktree"})
GIT_WRITE_FLAGS = frozenset({"-d", "-D", "-m", "-M", "--delete", "--move", "add", "remove",
                             "prune", "set-url", "--unset", "--add", "--replace-all"})
PLUMB_READ = frozenset({"status", "show", "explain", "brief", "drift", "impact", "resolve",
                        "inflight", "conflicts", "review", "stale", "align", "clarify", "why"})
_REDIRECT = re.compile(r"(?<![0-9&])>(?!&)|[0-9]>(?!&|/dev/null)")


def applies(data: dict[str, Any]) -> bool:
    """The question tool is there: the main agent of a session someone attends."""
    return not data.get("agent_id") and os.environ.get("CLAUDE_CODE_SESSION_ATTENDED") == "1"


def _reads(words: list[str]) -> bool:
    from plumb.guard import plumb_args

    while words and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[0]):
        words = words[1:]                      # FOO=bar cmd
    if words[:1] == ["rtk"]:
        words = words[1:]
    if not words:
        return True
    name = Path(words[0]).name.lower()
    if name in READ_COMMANDS:
        return True
    if name == "sed":
        return not any(w.startswith("-i") or w == "--in-place" for w in words[1:])
    if name == "find":
        return not {"-exec", "-execdir", "-delete", "-ok", "-fprint"} & set(words)
    if name == "git":
        args = words[1:]
        while args[:1] == ["-C"]:              # git -C <dir> ...
            args = args[2:]
        sub = next((w for w in args if not w.startswith("-")), "")
        return sub in GIT_READ and not GIT_WRITE_FLAGS & set(args[args.index(sub) + 1:] if sub
                                                             else [])
    args = plumb_args(words)
    if args is None:
        return False
    sub = next((a for a in args if not a.startswith("-")), "")
    if sub == "question":
        return any(a in ("reword", "pushback") for a in args)
    return sub in PLUMB_READ


def reads_only(command: str) -> bool:
    """A shell command that only reads (or rewords and pushes back questions): no redirection
    into a file, no command substitution, every piece a known reading command."""
    from plumb.guard import commands

    if "`" in command or "$(" in command or _REDIRECT.search(command):
        return False
    command = re.sub(r"[0-9]?>&[0-9]|[0-9]>/dev/null", " ", command)   # stderr, harmless
    return all(_reads(words) for words in commands(command))


def decide(root: Path | str, session: str, tool: str, tool_input: dict[str, Any],
           data: dict[str, Any]) -> str:
    """The deny reason while the gate holds this call, else "". Never raises."""
    if not session or not applies(data):
        return ""
    if tool not in (*WRITE_TOOLS, "Bash", "AskUserQuestion"):
        return ""
    from plumb.understand import judge

    if not judge.questions_path(root, session).exists():
        return ""                      # the fast path: this session's judge never asked
    try:
        from plumb.api import open_core

        core = open_core(Path(root))
        if tool == "AskUserQuestion":
            judge.note_asked(core, session)
            return ""
        if tool == "Bash" and reads_only(str(tool_input.get("command") or "")):
            return ""
        asked = set(judge.asked_keys(root, session))
        left = [q for q in judge.to_ask(core, session) if str(q.get("key")) not in asked]
    except Exception:  # noqa: BLE001 - the gate never blocks on its own failure
        return ""
    if not left:
        return ""
    many = len(left) > 1
    return REASON.format(n=len(left), s="s" if many else "", verb="have" if many else "has")
