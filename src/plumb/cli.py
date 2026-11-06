"""Command-line entry point for plumb (spec 12.3).

Kept import-light on purpose: hooks call this every turn, so start-up imports nothing beyond
``sys`` and the dispatcher until it knows the command. Each routed module exposes
``run(command: str, argv: list[str]) -> int``.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Sequence

from plumb import __version__

ROUTES: dict[str, str] = {
    # CORE
    "init": "plumb.commands",
    "link": "plumb.commands", "unlink": "plumb.commands", "relink": "plumb.commands",
    "repin": "plumb.commands", "stale": "plumb.commands",
    "validate": "plumb.commands",
    "loops": "plumb.understand.loops",   # SR-390: every loop of the project in one list
    "debug": "plumb.debug",   # SR-220, SR-300: the debug workflow, standalone
    "check": "plumb.commands",
    # approve, confirm, relay, revoke: refused as gone, listed in no help line (SR-210)
    "approve": "plumb.commands", "confirm": "plumb.commands", "relay": "plumb.commands",
    "revoke": "plumb.commands",
    # PRESENT (sub-project 5): the owner's commands, plain words accepted
    "status": "plumb.present.cli", "brief": "plumb.present.cli", "drift": "plumb.present.cli",
    "show": "plumb.present.cli", "explain": "plumb.present.cli", "why": "plumb.present.cli",
    "impact": "plumb.present.cli", "resolve": "plumb.present.cli",
    "review": "plumb.present.cli", "context": "plumb.present.cli",
    "align": "plumb.present.cli",
    # VERIFY
    "tests": "plumb.verify.cli", "map": "plumb.verify.cli", "verify": "plumb.verify.cli",
    # HOST
    "hook": "plumb.hosts.claude_code.cli", "hooks": "plumb.hosts.claude_code.cli",
    "install": "plumb.hosts.claude_code.cli", "statusline": "plumb.hosts.claude_code.cli",
    # BRIDGE (trailers and claims, judgment, importer)
    "trailers": "plumb.claims", "claims": "plumb.claims",
    "fidelity": "plumb.judgment.cli",
    "judge": "plumb.judgment.cli", "judgment": "plumb.judgment.cli",
    # CAPTURE (sub-project 2)
    "capture": "plumb.capture.cli", "new": "plumb.capture.cli",
    "intent": "plumb.understand.cli",   # open|gate|done|status: the loop; else the INT capture
    "example": "plumb.capture.cli", "decide": "plumb.capture.cli",
    "escalate": "plumb.capture.cli", "spec": "plumb.capture.cli",
    "config": "plumb.capture.cli", "jev": "plumb.capture.cli",
    "clarify": "plumb.understand.cli",
    "question": "plumb.understand.cli",   # SR-362: reword judge questions
    "proof": "plumb.capture.proof",  # SR-127: a requirement's proof plan and evidence
    # SP8 UNDERSTAND: the model-backed layer (a thin router; listed only when importable)
    "understand": "plumb.understand.cli",
    "quotes": "plumb.understand.cli",
    # MERGE (sub-project 3)
    "merge-check": "plumb.boundary.cli",
    # SP6 LOGS: one file per log entry; the migration of the legacy JSONL lines
    "log": "plumb.logcmd",
    # IDS (sub-project 6)
    "merge-fix": "plumb.ids.cli", "ids": "plumb.ids.cli",
    # MERGEDRIVER (sub-project 6): record files merge field by field; intent conflicts
    "merge-driver": "plumb.mergedriver.cli", "conflict": "plumb.mergedriver.cli",
    "conflicts": "plumb.mergedriver.cli",
    # AWARENESS (sub-project 6, R17): intent other branches have in flight
    "inflight": "plumb.awareness.cli",
    # HOSTS (sub-project 4)
    "hosts": "plumb.hosts.cli", "turn": "plumb.hosts.cli",
    # PLUGIN (sub-project 7): the owner's "not here" list and the move from the old install
    "plugin": "plumb.plugin.cli",
    # SP7 MOD: the commands only plumb's panel runs (hello, draw, press; key on stdin)
    "mod": "plumb.mod.cli",
    "ui": "plumb.browser.cli",
    # INT-090: studies the owner reads in the room, and the understanding picture
    "study": "plumb.study.cli",
    "evaluate": "plumb.evaluate.cli",   # INT-105: the benchmark
}

_HELP = """usage: plumb <command> [options]

Keep agent work aligned with the owner's intent.

  ui           open the local browser issue workspace (--demo for an isolated example)

records and integrity:
  init         adopt this repository (.plumb/)
  show         print records in full (read-back, examples, assumptions, alternatives)
  link         add a hash-pinned link between a record and a record, file or test
  unlink       remove a link (--note why); the links after it move down by one
  relink       point a link at a new target (--note why), keeping its number and example
  repin        refresh link pins (never confirms); --after-tests: only when the linked tests
               pass and a model judges the meaning unchanged
  stale        card: bring a stale link to the owner as a card; cards: list them in full
               (--incomplete: those lacking something)
  debug        the debug workflow: rerun each stale link once through tests and the
               meaning cascade, say what it did and what is missing (--dry-run)
  validate     check records, links and logs (--merge BASE: the merge boundary); alias check
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
  config       auto-approve on|off and show (owner's terminal only)
  jev          status, setup (the credential variable's name only), calibrate
  study        propose | add | list | candidates | mark: at most one study idea per
               intent-loop step, written once the owner accepts it, read in the browser
               room; the understanding picture it corrects
  quotes       recover: find older records' words in past session transcripts (shown on
               the card as found, not verified; it confirms nothing)

development:
  evaluate     the benchmark: a cheap model works through a task with plumb
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
  merge-driver  git's merge driver for record files (git calls it; see plumb hooks install)

parallel work:
  merge-fix    renumber an ID a merge brought twice: the incoming record gets a new ID and
               every reference the incoming side added follows; history is never rewritten
  ids          the IDs reserved in refs/plumb/ids (sync rescans every local branch)
in flight:     inflight (what other branches are changing, from refs/plumb/claims; check
               a request for an early intent conflict; drop; sync)

Run `plumb <command> --help` for a command's options. Exit codes: 0 ok, 1 findings,
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
    print(f"plumb: '{command}' is not available in this build", file=sys.stderr)
    return 2


def utf8_output() -> None:
    """Make stdout and stderr UTF-8 (errors replaced), whatever the console or pipe encoding.

    The one choke point that lets every verb print plumb's glyphs (the card's ●, ▸, ✓):
    Python encodes a pipe in the locale code page (cp1252 on Windows) unless PYTHONUTF8 or
    PYTHONIOENCODING says otherwise, which is how an agent's shell tool runs plumb. Hooks and
    ``plumb turn`` set their own (strict) UTF-8 stdout on top of this."""
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
    """`plumb <command> ...`: import ROUTES[command] lazily and return its run()."""
    utf8_output()
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        sys.stdout.write(help_text())
        return 0
    if args[0] == "--version":
        print(f"plumb {__version__}")
        return 0
    command = args[0]
    module_name = ROUTES.get(command)
    if module_name is None:
        print(f"plumb: unknown command '{command}' (see plumb --help)", file=sys.stderr)
        return 2
    import importlib

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
