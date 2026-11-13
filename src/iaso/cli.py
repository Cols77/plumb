"""Command-line entry point for iaso (spec 12.3).

Kept import-light on purpose: hooks call this every turn, so start-up imports nothing beyond
``sys`` and the dispatcher until it knows the command. Each routed module exposes
``run(command: str, argv: list[str]) -> int``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence
from pathlib import Path

from iaso import __version__

ROUTES: dict[str, str] = {
    # CORE
    "init": "iaso.commands",
    "link": "iaso.commands", "unlink": "iaso.commands", "relink": "iaso.commands",
    "repin": "iaso.commands",
    "validate": "iaso.commands",
    "loops": "iaso.understand.loops",   # SR-390: every loop of the project in one list
    "debug": "iaso.debug",   # SR-220, SR-300: the debug workflow, standalone
    "check": "iaso.commands",
    # approve, confirm, relay, revoke: refused as gone, listed in no help line (SR-210)
    "approve": "iaso.commands", "confirm": "iaso.commands", "relay": "iaso.commands",
    "revoke": "iaso.commands",
    # PRESENT (sub-project 5): the owner's commands, plain words accepted
    "status": "iaso.present.cli", "brief": "iaso.present.cli", "drift": "iaso.present.cli",
    "show": "iaso.present.cli", "explain": "iaso.present.cli", "why": "iaso.present.cli",
    "impact": "iaso.present.cli", "resolve": "iaso.present.cli",
    "review": "iaso.present.cli", "context": "iaso.present.cli",
    "align": "iaso.present.cli",
    # VERIFY
    "tests": "iaso.verify.cli", "map": "iaso.verify.cli", "verify": "iaso.verify.cli",
    # HOST
    "hook": "iaso.hosts.claude_code.cli", "hooks": "iaso.hosts.claude_code.cli",
    "install": "iaso.hosts.claude_code.cli", "statusline": "iaso.hosts.claude_code.cli",
    # BRIDGE (trailers and claims, judgment, importer)
    "trailers": "iaso.claims", "claims": "iaso.claims",
    "fidelity": "iaso.judgment.cli",
    "judge": "iaso.judgment.cli", "judgment": "iaso.judgment.cli",
    # CAPTURE (sub-project 2)
    "capture": "iaso.capture.cli", "new": "iaso.capture.cli",
    "intent": "iaso.understand.cli",   # open|gate|done|status: the loop; else the INT capture
    "example": "iaso.capture.cli", "decide": "iaso.capture.cli",
    "escalate": "iaso.capture.cli", "spec": "iaso.capture.cli",
    "config": "iaso.capture.cli", "jev": "iaso.capture.cli",
    "clarify": "iaso.understand.cli",
    "question": "iaso.understand.cli",   # SR-362: reword judge questions
    "proof": "iaso.capture.proof",  # SR-127: a requirement's proof plan and evidence
    # SP8 UNDERSTAND: the model-backed layer (a thin router; listed only when importable)
    "understand": "iaso.understand.cli",
    "quotes": "iaso.understand.cli",
    # MERGE (sub-project 3)
    "merge-check": "iaso.boundary.cli",
    # SP6 LOGS: one file per log entry; the migration of the legacy JSONL lines
    "log": "iaso.logcmd",
    # IDS (sub-project 6)
    "merge-fix": "iaso.ids.cli", "ids": "iaso.ids.cli",
    # MERGEDRIVER (sub-project 6): record files merge field by field; intent conflicts
    "merge-driver": "iaso.mergedriver.cli", "conflict": "iaso.mergedriver.cli",
    "conflicts": "iaso.mergedriver.cli",
    # AWARENESS (sub-project 6, R17): intent other branches have in flight
    "inflight": "iaso.awareness.cli",
    # HOSTS (sub-project 4)
    "hosts": "iaso.hosts.cli", "turn": "iaso.hosts.cli",
    # PLUGIN (sub-project 7): the owner's "not here" list and the move from the old install
    "plugin": "iaso.plugin.cli",
    # SP7 MOD: the commands only iaso's panel runs (hello, draw, press; key on stdin)
    "mod": "iaso.mod.cli",
    "ui": "iaso.browser.cli",
    # INT-090: studies the owner reads in the room, and the understanding picture
    "study": "iaso.study.cli",
    "evaluate": "iaso.evaluate.cli",   # INT-105: the benchmark
    "heavy": "iaso.heavy", "landing": "iaso.landing",   # SR-386: sessions
}

_HELP = """usage: iaso <command> [options]

Keep agent work aligned with the owner's intent.

  ui           open the local browser issue workspace (--demo for an isolated example)

records and integrity:
  init         adopt this repository (make its records folder)
  show         print records in full (read-back, examples, assumptions, alternatives)
  link         add a hash-pinned link between a record and a record, file or test
  unlink       remove a link (--note why); the links after it move down by one
  relink       point a link at a new target (--note why), keeping its number and example
  repin        refresh link pins (never confirms); --after-tests: only when the linked tests
               pass and a model judges the meaning unchanged
  debug        the debug workflow: rerun each stale link once through tests and the
               meaning cascade, say what it did and what is missing (--dry-run)
  validate     check records, links and logs (--merge BASE: the merge boundary); alias check
  heavy        run a command under the one-heavy-job lock: iaso heavy -- <command...>
  landing      the landing queue and board: add|wait|ready|next|done <branch>
  status       counts, drift, what awaits you, judge approvals (--card: the card)
  brief        the short intent brief
  explain      why a behaviour, file or record exists, in plain terms (plain words, a path
               or an ID); alias why
  proof        a requirement's planned proof (how you will see it working) and its evidence
  drift        drift signals only
  log          migrate: move legacy JSONL log lines into one file per entry (digests kept)

intent capture:
  capture      record a whole read-back (INT, SR with examples, DEC) in one call, proposed
  new          one record of a kind (intent, requirement, decision, feature, nc)
  intent       the owner's words and your read-back as an INT; open | gate clarify|plan
               --intent ID --findings FILE | done --intent ID | status: the intent loop
  example      append a given/when/then example to a requirement
  decide       a decision: "I assumed A; B also fits" (--supersede for a confirmed one)
  clarify      the clarification depth and the questions that matter for a request
  loops        every loop of the project (intent, debug, evaluate), live first: its goal,
               progress, what is left and what it waits for (changes nothing)
  question     reword: your wording of the judge's questions (merged by principle)
  escalate     escalation suggestions; decline (the owner said no)
  spec         an escalated spec: show (every member in full, the set hash), state
  config       auto-approve on|off, evaluator always|ask and show (owner's terminal only)
  jev          status, setup (the credential variable's name only), calibrate
  study        propose | add | list | candidates | mark: at most one study idea per
               intent-loop step, written once the owner accepts it, read in the browser
               room; the understanding picture it corrects
  quotes       recover: find older records' words in past session transcripts (shown on
               the card as found, not verified; it confirms nothing)

development:
  evaluate     the benchmark: a cheap model works through a task with iaso
               (simple|complex; --model, --loop)

owner views (plain words, paths or IDs; none approves anything):
  resolve      what your words mean: records, files and tests, best first
  review       the deep review: what awaits you, approvals you did not type, drift,
               alignment, the merge state
  align        judge each edge from intent to evidence, weakest first; name the gaps
  impact       what a change would reach

agent views (the agent's, never shown to the owner):
  context      the full picture of one condition (session, prompt, edit, test, symptom,
               merge), unfiltered: what the hooks say in part

verification:  tests (map | select | run), map, verify
host:          hook, hooks, install, statusline
plugin:        plugin ignore | unignore | migrate (the Claude Code plugin)
hosts:         hosts (install|uninstall|status codex|hermes), turn (start|end: the
               CLI-only fallback)
bridge:        trailers, claims, fidelity, judge, judgment
merge:         merge-check (the merge boundary: one full run, claims, links, the glance;
               --install-pre-push: the git hook init installs)

record merges (parallel work):
  conflicts    the intent conflicts a merge left, as cards (both versions; nothing chosen)
  conflict     propose a combined version; choose a side (owner's terminal)
  merge-driver  git's merge driver for record files (git calls it; see iaso hooks install)

parallel work:
  merge-fix    renumber an ID a merge brought twice: the incoming record gets a new ID and
               every reference the incoming side added follows; history is never rewritten
  ids          the IDs reserved in refs/iaso/ids (sync rescans every local branch)
in flight:     inflight (what other branches are changing, from refs/iaso/claims; check
               a request for an early intent conflict; drop; sync)

Run `iaso <command> --help` for a command's options. Exit codes: 0 ok, 1 findings,
2 usage, 3 refused by the guard, 4 merge waits for the owner (a conflict or a question), 5 a
failing test or an unconfirmed proof holds the merge.
"""


def _available(command: str) -> bool:
    """A verb is listed only when its module is importable in this build (SR-068)."""
    import importlib.util

    module = ROUTES.get(command)
    if module is None:
        return False
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


_VERB_LINE = re.compile(r"^  ([a-z][a-z-]*)\s{2,}")
_LIST_LINE = re.compile(r"^([a-z][a-z ]*:)(\s+)(.*)$")


def help_text() -> str:
    """``_HELP`` without the verbs this build lacks: a verb line (``  verb  text``) and its
    continuation lines go; in a category line (``host: hook, hooks``) each verb is kept only
    when available. Nothing unavailable is advertised (sp5 6.4)."""
    out: list[str] = []
    dropping = False
    for line in _HELP.splitlines():
        verb = _VERB_LINE.match(line)
        if verb:
            dropping = not _available(verb.group(1))
            if not dropping:
                out.append(line)
            continue
        if dropping and line.startswith("    "):
            continue
        dropping = False
        listed = _LIST_LINE.match(line)
        if listed and "," in listed.group(3) or (listed and listed.group(3).split(" ")[0]
                                                 in ROUTES):
            kept = [item for item in listed.group(3).split(", ")
                    if _available(item.split(" ")[0])]
            if kept:
                out.append(listed.group(1) + listed.group(2) + ", ".join(kept))
            continue
        out.append(line)
    return "\n".join(out) + "\n"


def _not_available(command: str) -> int:
    print(f"iaso: '{command}' is not available in this build", file=sys.stderr)
    return 2


def utf8_output() -> None:
    """Make stdout and stderr UTF-8 (errors replaced), whatever the console or pipe encoding.

    The one choke point that lets every verb print iaso's glyphs (the card's ●, ▸, ✓):
    Python encodes a pipe in the locale code page (cp1252 on Windows) unless PYTHONUTF8 or
    PYTHONIOENCODING says otherwise, which is how an agent's shell tool runs iaso. Hooks and
    ``iaso turn`` set their own (strict) UTF-8 stdout on top of this."""
    for stream in (sys.stdout, sys.stderr):
        encoding = str(getattr(stream, "encoding", "") or "").lower().replace("-", "")
        reconfigure = getattr(stream, "reconfigure", None)
        if encoding == "utf8" or reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    """`iaso <command> ...`: import ROUTES[command] lazily and return its run()."""
    utf8_output()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(help_text())
        return 0
    if args[0] == "--version":
        print(f"iaso {__version__}")
        return 0
    command = args[0]
    module_name = ROUTES.get(command)
    if module_name is None:
        print(f"iaso: unknown command '{command}' (see iaso --help)", file=sys.stderr)
        return 2
    import importlib

    from iaso.convert import convert_if_old

    root = args[args.index("--root") + 1] if "--root" in args[:-1] else "."
    convert_if_old(Path(root))   # an old-name project is converted first (SR-432)
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as exc:
        missing = exc.name or ""
        if missing and (module_name == missing or module_name.startswith(missing + ".")):
            return _not_available(command)
        raise
    run = getattr(module, "run", None)
    if run is None:
        return _not_available(command)
    try:
        return int(run(command, args[1:]) or 0)
    except SystemExit as exc:  # a module's argparse --help or usage error
        code = exc.code
        return code if isinstance(code, int) else (0 if code is None else 2)
    except Exception as exc:
        # an error that carries its own exit code and owner-facing line (``IdBusy``: the
        # ID reservation stayed busy, exit 2) ends the command without a traceback
        code = getattr(exc, "exit_code", None)
        if not isinstance(code, int):
            raise
        print(str(exc), file=sys.stderr)
        return code
