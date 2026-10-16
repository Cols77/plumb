"""The guard: what the agent's shell and edit tools may never do (concept 4.6 check 2; SP7 4.3,
re-aligned with SP8 in ``docs/specs/sp7-realign-sp8.md`` slice 6).

One table, three readers that agree by construction:

- the plugin's ``pre-tool`` command hook (``plumb.hosts.claude_code.pretool``) denies with
  ``denied(tool, tool_input)``;
- the legacy per-repository install writes ``permissions.deny`` rules from the rows marked
  ``legacy`` (``install.deny_rules``);
- the mod's ``tool.call`` hook (SP7 5.9) reads ``plugin/hooks/guard.gen.ts``, generated from
  this table by ``scripts/build_plugin.py``.

A row names a plumb command by its words. Some commands are the owner's only with their proof:
``conflict choose`` and ``owner`` carry ``--prompt <digest>`` of the owner's typed command (the
command re-checks that digest) and the owner's relayed words. Without the proof they are
denied; with it they reach the command, which re-checks it. ``mod hello|press|typed`` are
the mod's alone (the key never leaves it).
Every launcher spelling counts: ``plumb``, ``plumb.exe``, ``plumb.cmd``, ``<path>/bin/plumb``,
``uv run [--no-sync] plumb``, ``python -m plumb`` and ``<path>/python(.exe) -m plumb``, also
inside ``sh -c``/``bash -c`` strings, ``$( )``, backquotes and after ``env``/``exec``.

Standard library only: the hook imports it on every guarded tool call."""

from __future__ import annotations

import re
import shlex
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

MARKER_NAME = "PLUMB_AGENT_SESSION"
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
PROOF = "--prompt"


@dataclass(frozen=True)
class Row:
    """One guarded command: ``words`` after the launcher (the first is the verb, the others
    must follow it), ``first_of`` alternatives for the word after the verb, ``unless`` the
    option that carries the owner's proof (``None``: always denied), ``legacy`` whether the
    per-repository install writes a ``permissions.deny`` rule for it."""

    words: tuple[str, ...]
    why: str
    unless: str | None = None
    legacy: bool = False
    first_of: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        tail = ("|".join(self.first_of),) if self.first_of else ()
        return " ".join((*self.words, *tail))


_OWNER = "only the owner can do this, in their own terminal or by a button"
_TYPED = ("only the owner's typed command does this: run it with --prompt and the digest of "
          "the owner's message that is exactly that command")
_MOD = "this is the plumb panel's own step; only a press in the panel runs it"
_LOG = "the prompt hook logs the owner's messages itself"

TABLE: tuple[Row, ...] = (
    Row(("ui",), _OWNER, legacy=True),
    Row(("approve",), _OWNER, legacy=True),
    Row(("revoke",), _OWNER, legacy=True),
    Row(("tests", "waive"), _OWNER, legacy=True),
    Row(("triage", "--approve"), _OWNER, legacy=True),
    Row(("spec", "approve"), _OWNER, legacy=True),
    Row(("config", "auto-approve"), _OWNER, legacy=True),
    Row(("config", "show"), _OWNER, legacy=True),
    Row(("turn", "start"), _LOG, legacy=True),
    Row(("hook", "prompt"), _LOG, legacy=True),
    # the legacy rule denies it outright (a prefix rule cannot see --prompt); the hook lets the
    # owner's relayed choice through to the command, which re-checks it (sp6 8.4)
    Row(("conflict", "choose"), _TYPED, unless=PROOF, legacy=True),
    # SP7 7.2's one choke point for owner actions, the agent's form carrying the owner's words
    Row(("owner",), _TYPED, unless=PROOF),
    # SP7 5.5, 5.7: the mod's handshake, its button press and its log of a typed command
    Row(("mod",), _MOD, legacy=True, first_of=("hello", "press", "typed")),
)

REASON = ("plumb: refused: `{form}` {why}. The agent never runs it for the owner; tell the owner "
          "what it would do and let them do it.")
MARKER_REASON = ("plumb: refused: the command names the agent session marker; the agent never "
                 "reads, changes or removes it.")
LOG_REASON = ("plumb: refused: plumb's log under .plumb/log/ is written by plumb alone; the agent "
              "never edits it.")

# --------------------------------------------------------------------------- launchers

_PY = re.compile(r"^(?:python(?:3(?:\.\d+)?)?|py)(?:\.exe)?$", re.IGNORECASE)
_PLUMB = re.compile(r"^plumb(?:\.exe|\.cmd|\.bat)?$", re.IGNORECASE)
_SHELLS = re.compile(r"^(?:ba|z|da|k)?sh(?:\.exe)?$", re.IGNORECASE)
_PWSH = re.compile(r"^(?:powershell|pwsh)(?:\.exe)?$", re.IGNORECASE)
_PREFIX_WORDS = {"env", "exec", "command", "nohup", "time", "sudo", "builtin", "nice"}
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def _base(word: str) -> str:
    return re.split(r"[\\/]", word)[-1].strip("\"'")


def plumb_args(words: Sequence[str]) -> list[str] | None:
    """The arguments a command passes to plumb (after the launcher), or ``None`` when it does
    not run plumb. ``words`` is one simple command, already split."""
    rest = list(words)
    while rest and (_ASSIGN.match(rest[0]) or rest[0] in _PREFIX_WORDS
                    or (rest[0].startswith("-") and rest[0] != "-")):
        rest.pop(0)
    if not rest:
        return None
    head = _base(rest[0])
    if _PLUMB.match(head):
        return rest[1:]
    if head in ("uv", "uv.exe", "uvx", "uvx.exe"):
        tail = rest[1:]
        if tail and tail[0] == "run":
            tail = tail[1:]
        while tail and tail[0].startswith("-"):
            option = tail.pop(0)
            if option in ("--with", "--python", "-p", "--project", "--directory", "--group",
                          "--extra", "--env-file", "--from") and tail:
                tail.pop(0)
        if tail and _PLUMB.match(_base(tail[0])):
            return tail[1:]
        return plumb_args(tail) if tail else None
    if _PY.match(head):
        tail = rest[1:]
        while tail and tail[0].startswith("-") and tail[0] != "-m":
            tail.pop(0)
        if tail[:1] == ["-m"] and len(tail) > 1 and tail[1] in ("plumb", "plumb.cli",
                                                                 "plumb.__main__"):
            return tail[2:]
        if tail[:1] and tail[0].startswith("-mplumb"):
            return tail[1:]
    return None


def _words(segment: str) -> list[str]:
    try:
        return shlex.split(segment, posix=True)
    except ValueError:
        return segment.split()


def _inner_scripts(words: Sequence[str]) -> list[str]:
    """``sh -c "..."`` and friends: the script string, read as a command of its own."""
    out = []
    rest = [w for w in words if not _ASSIGN.match(w)]
    while rest and rest[0] in _PREFIX_WORDS:
        rest.pop(0)
    if rest and rest[0] == "eval":
        return [" ".join(rest[1:])]
    if rest and _PWSH.match(_base(rest[0])):
        for n, word in enumerate(rest[1:], 1):
            if word.lower() in ("-command", "-c") and n + 1 < len(rest):
                return [" ".join(rest[n + 1:])]
        return []
    if rest and _SHELLS.match(_base(rest[0])):
        for n, word in enumerate(rest[1:], 1):
            if word.startswith("-") and "c" in word.lstrip("-") and n + 1 < len(rest):
                out.append(rest[n + 1])
                break
    return out


_HEREDOC = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")


def _without_heredocs(text: str) -> str:
    """The command line without here-document bodies (a commit message is data, not a
    command)."""
    out: list[str] = []
    waiting: list[tuple[str, bool]] = []
    for line in text.split("\n"):
        if waiting:
            delim, strip_tabs = waiting[0]
            if (line.lstrip("\t") if strip_tabs else line).strip() == delim:
                waiting.pop(0)
            continue
        out.append(line)
        for match in _HEREDOC.finditer(line):
            waiting.append((match.group(2), match.group(0).startswith("<<-")))
    return "\n".join(out)


def _segments(text: str) -> list[str]:
    """Split a command line into simple commands at ``;``, ``&&``, ``||``, ``|``, ``&``,
    newlines and parentheses outside quotes, and at ``$( )`` and backquotes anywhere but
    single quotes (their content is a command of its own)."""
    segments: list[str] = []
    current: list[str] = []
    # the stack of contexts: "'" or '"' (quoted), "(" ($( ) substitution), "`" (backquote)
    stack: list[str] = []

    def cut() -> None:
        segments.append("".join(current))
        current.clear()

    i = 0
    while i < len(text):
        char = text[i]
        top = stack[-1] if stack else ""
        if top == "'":
            if char == "'":
                stack.pop()
            current.append(char)
            i += 1
            continue
        if char == "\\" and i + 1 < len(text):
            current.append(text[i:i + 2])
            i += 2
            continue
        if top == '"':
            if char == '"':
                stack.pop()
                current.append(char)
            elif text.startswith("$(", i):
                stack.append("(")
                cut()
                i += 2
                continue
            elif char == "`":
                stack.append("`")
                cut()
            else:
                current.append(char)
            i += 1
            continue
        # unquoted, or inside a substitution
        if char in "'\"":
            stack.append(char)
            current.append(char)
        elif text.startswith("$(", i):
            stack.append("(")
            cut()
            i += 2
            continue
        elif char == "`":
            if top == "`":
                stack.pop()
            else:
                stack.append("`")
            cut()
        elif char == ")" and top == "(":
            stack.pop()
            cut()
        elif text.startswith(("&&", "||"), i):
            cut()
            i += 2
            continue
        elif char in ";|&\n(){}":
            cut()
        else:
            current.append(char)
        i += 1
    cut()
    return [s for s in segments if s.strip()]


def commands(text: str, depth: int = 0) -> list[list[str]]:
    """Every simple command in a shell command line, split into words (also those inside
    ``$( )``, backquotes and ``sh -c`` strings)."""
    found: list[list[str]] = []
    for segment in _segments(_without_heredocs(text or "")):
        words = _words(segment)
        if not words:
            continue
        found.append(words)
        if depth < 3:
            for script in _inner_scripts(words):
                found.extend(commands(script, depth + 1))
    return found


def _has_option(args: Sequence[str], option: str) -> bool:
    return any(a == option or a.startswith(option + "=") for a in args)


def _row_for(args: Sequence[str]) -> Row | None:
    if not args:
        return None
    for row in TABLE:
        verb, *more = row.words
        if args[0] != verb:
            continue
        tail = list(args[1:])
        if any(word not in tail for word in more):
            continue
        if row.first_of:
            after = [a for a in tail if not a.startswith("-")]
            if not after or after[0] not in row.first_of:
                continue
        return row
    return None


def denied_command(text: str) -> str | None:
    """The plain reason the shell command ``text`` is refused, or ``None``."""
    if MARKER_NAME in (text or ""):
        return MARKER_REASON
    for words in commands(text):
        args = plumb_args(words)
        if args is None:
            continue
        row = _row_for(args)
        if row is None:
            continue
        if row.unless and _has_option(args, row.unless):
            continue
        chosen = [a for a in args[1:] if a in row.first_of][:1]
        form = "plumb " + " ".join((*row.words, *chosen))
        return REASON.format(form=form, why=row.why)
    return None


def _paths(tool_input: Mapping[str, Any]) -> Iterable[str]:
    for key in ("file_path", "notebook_path", "path"):
        value = tool_input.get(key)
        if isinstance(value, str):
            yield value
    for edit in tool_input.get("edits") or ():
        if isinstance(edit, Mapping) and isinstance(edit.get("file_path"), str):
            yield edit["file_path"]


def _under_log(path: str) -> bool:
    norm = "/" + path.replace("\\", "/")
    return "/.plumb/log/" in norm or norm.endswith("/.plumb/log")


def denied(tool: str, tool_input: Mapping[str, Any] | None) -> str | None:
    """The plain reason the tool call is refused, or ``None`` (allowed): the one function the
    ``pre-tool`` hook asks."""
    tool_input = tool_input if isinstance(tool_input, Mapping) else {}
    if tool == "Bash" or tool == "PowerShell":
        return denied_command(str(tool_input.get("command") or ""))
    if tool in EDIT_TOOLS:
        if any(_under_log(p) for p in _paths(tool_input)):
            return LOG_REASON
    return None


# --------------------------------------------------------------------------- legacy rules


def legacy_forms() -> list[str]:
    """The command forms the legacy ``permissions.deny`` rules name (``approve``, ``mod
    hello``, ...), in table order."""
    out: list[str] = []
    for row in TABLE:
        if not row.legacy:
            continue
        if row.first_of:
            out += [" ".join((*row.words, word)) for word in row.first_of]
        else:
            out.append(" ".join(row.words))
    return out


def table_data() -> list[dict[str, Any]]:
    """The table as plain data (``guard.gen.ts``)."""
    return [{"words": list(r.words), "firstOf": list(r.first_of), "unless": r.unless,
             "legacy": r.legacy, "why": r.why} for r in TABLE]
