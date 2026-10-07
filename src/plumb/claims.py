"""``SR:`` trailers at commit time and the claims check (spec 5.9).

Extracted and simplified from pi-agent-factory's ``coherence/register/claims.py``: the glob
matcher, exemption lookup, baseline entries and the commit check are kept; the strict policy
diffing and claim corrections are dropped. Trailer parsing itself lives in CORE's
``plumb.trailers``.

Commands: ``plumb trailers check-msg <file>``, ``plumb trailers install-hook``,
``plumb claims check [--range BASE..HEAD]``.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from plumb.trailers import TRAILER_KEY, invalid_ids, parse_sr_trailer

DEFAULT_EXEMPT: tuple[str, ...] = (".plumb/**", "docs/**", ".claude/**", "uv.lock",
                                   ".gitignore", ".gitattributes")
HOOK_MARKER = "# plumb commit-msg hook"
NOT_INITIALIZED = "plumb: not initialized here, trailer not checked"


class ForeignHookError(RuntimeError):
    """A ``commit-msg`` hook plumb did not write exists; it is left untouched."""


@dataclass(frozen=True)
class BaselineEntry:
    """One known undeclared path, accounted for by a nonconformance record."""

    commit: str
    path: str
    nc: str | None


@dataclass(frozen=True)
class ClaimsPolicy:
    """``.plumb/claims.yaml``; defaults when it is absent or unreadable."""

    require_trailer: bool = False
    exempt: tuple[str, ...] = DEFAULT_EXEMPT
    baseline: tuple[BaselineEntry, ...] = ()
    problems: tuple[str, ...] = field(default=())


# --------------------------------------------------------------------------- policy


def load_policy(root: Path) -> ClaimsPolicy:
    path = Path(root) / ".plumb" / "claims.yaml"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ClaimsPolicy()
    import yaml

    try:
        raw = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        return ClaimsPolicy(problems=(f"{path.name}: unreadable: {exc}".splitlines()[0],))
    if not isinstance(raw, Mapping):
        return ClaimsPolicy(problems=(f"{path.name}: expected a mapping",))
    problems: list[str] = []
    extra = raw.get("exempt") or []
    if not isinstance(extra, list):
        problems.append("exempt must be a list of globs")
        extra = []
    exempt = DEFAULT_EXEMPT + tuple(str(g) for g in extra if isinstance(g, str) and g.strip()
                                    and g not in DEFAULT_EXEMPT)
    baseline_raw = raw.get("baseline") or []
    baseline: list[BaselineEntry] = []
    if not isinstance(baseline_raw, list):
        problems.append("baseline must be a list of {commit, path, nc}")
        baseline_raw = []
    for item in baseline_raw:
        if not isinstance(item, Mapping):
            problems.append(f"baseline entry {item!r} is not a mapping")
            continue
        nc = item.get("nc")
        entry = BaselineEntry(commit=str(item.get("commit") or "").strip(),
                              path=str(item.get("path") or "").strip(),
                              nc=str(nc).strip() if isinstance(nc, str) and nc.strip() else None)
        if not entry.commit or not entry.path:
            problems.append(f"baseline entry {dict(item)!r} needs a commit and a path")
        elif entry.nc is None or not re.match(r"^NC-\d{4,}$", entry.nc):
            problems.append(f"baseline entry {entry.commit} {entry.path} names no NC record")
        baseline.append(entry)
    return ClaimsPolicy(require_trailer=raw.get("require_trailer") is True, exempt=exempt,
                        baseline=tuple(baseline), problems=tuple(problems))


def glob_match(pattern: str, path: str) -> bool:
    """Match a repo-relative POSIX path; ``**`` crosses separators, ``*`` and ``?`` do not."""
    out: list[str] = ["^"]
    i = 0
    while i < len(pattern):
        char = pattern[i]
        if pattern.startswith("**", i):
            out.append(".*")
            i += 2
            if pattern.startswith("/", i):
                i += 1
        elif char == "*":
            out.append("[^/]*")
            i += 1
        elif char == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(char))
            i += 1
    out.append("$")
    return re.match("".join(out), path) is not None


def exempting_glob(policy: ClaimsPolicy, path: str) -> str | None:
    """The first exempt glob that matches ``path``, else None."""
    for pattern in policy.exempt:
        if glob_match(pattern, path):
            return pattern
    return None


# --------------------------------------------------------------------------- check-msg


def check_msg(root: Path, message: str) -> tuple[int, list[str]]:
    """``(exit code, lines)`` for one commit message (spec 5.9)."""
    root = Path(root)
    if not (root / ".plumb").is_dir():
        return 0, [NOT_INITIALIZED]
    policy = load_policy(root)
    ids = parse_sr_trailer(message)
    if not ids:
        if policy.require_trailer and not _generated_over_exempt(root, policy, message):
            return 1, [f"plumb: this commit declares no '{TRAILER_KEY}:' trailer; add a line "
                       f"'{TRAILER_KEY}: SR-0xx' naming the requirements it serves"]
        return 0, []
    malformed = invalid_ids(ids)
    if malformed:
        return 1, [f"plumb: malformed record id(s) in the {TRAILER_KEY}: trailer: "
                   + ", ".join(malformed)]
    from plumb.api import open_core

    core = open_core(root)
    index = core.index()
    unknown = [i for i in ids if i not in index]
    if unknown:
        return 1, [f"plumb: the {TRAILER_KEY}: trailer names unknown record(s): "
                   + ", ".join(unknown) + " (see .plumb/requirements/)"]
    return 0, _serves_warnings(core, ids, staged_paths(root))


# git writes these messages itself (revert, merge, fixup/squash/amend for autosquash)
_GENERATED = re.compile(r"^(?:Revert \"|Merge (?:branch|remote-tracking branch|tag|pull "
                        r"request|commit|[0-9a-f]{7,})|(?:fixup|squash|amend)! )")


def staged_paths(root: Path) -> list[str]:
    """The paths the commit being written changes (``git diff --cached``), or []."""
    result = subprocess.run(["git", "diff", "--cached", "--name-only", "--no-renames", "-z"],
                            cwd=root, capture_output=True)
    if result.returncode != 0:
        return []
    return [p for p in result.stdout.decode("utf-8", "replace").split("\0") if p]


def _generated_over_exempt(root: Path, policy: ClaimsPolicy, message: str) -> bool:
    """A git-generated revert, merge or fixup message whose staged paths are all exempt
    needs no trailer: like ``plumb claims check``, it claims nothing that needs a claim."""
    first = message.lstrip().splitlines()[0] if message.strip() else ""
    if not _GENERATED.match(first):
        return False
    paths = staged_paths(root)
    return bool(paths) and all(exempting_glob(policy, p) is not None for p in paths)


def _serves_warnings(core: Any, ids: list[str], paths: list[str]) -> list[str]:
    """Non-blocking "does this diff serve its claimed SRs?" warnings (R12.3, sp2 10.1) from
    the capture lane's ``diff_serves``; nothing when it is absent or fails. The exit code
    and the claims result never depend on it."""
    if not paths:
        return []
    try:
        from plumb.capture.api import diff_serves
    except ImportError:
        return []
    try:
        return [str(line) for line in diff_serves(core, ids, paths) or ()]
    except Exception:
        return []


# --------------------------------------------------------------------------- install-hook


def _git_path(root: Path, rel: str) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-path", rel], cwd=root,
                         capture_output=True, text=True, check=True, encoding="utf-8")
    path = Path(out.stdout.strip())
    return path if path.is_absolute() else (Path(root) / path)


def hook_text(interpreter: str) -> str:
    exe = interpreter.replace("\\", "/")
    return (f"#!/bin/sh\n{HOOK_MARKER} (written by `plumb trailers install-hook`)\n"
            f'exec "{exe}" -m plumb trailers check-msg "$1"\n')


def install_commit_msg_hook(root: Path, interpreter: str) -> Path:
    """Write the git ``commit-msg`` hook (spec 12.2); a foreign hook is left untouched.

    The path comes from ``git rev-parse --git-path hooks/commit-msg``, which is the shared
    hooks directory of every worktree (and honours ``core.hooksPath``).
    """
    path = _git_path(Path(root), "hooks/commit-msg")
    if path.exists():
        try:
            current = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise ForeignHookError(f"cannot read the existing hook {path}: {exc}") from exc
        if HOOK_MARKER not in current:
            raise ForeignHookError(f"a foreign commit-msg hook exists at {path}; left "
                                   "untouched (call `plumb trailers check-msg \"$1\"` from it)")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(hook_text(interpreter).encode("utf-8"))
    try:
        path.chmod(0o755)
    except OSError:
        pass
    return path


# --------------------------------------------------------------------------- claims check


@dataclass(frozen=True)
class Undeclared:
    commit: str
    path: str
    claims: tuple[str, ...]


def read_range(root: Path, rng: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """``[(sha, message, paths)]`` of a range, with one ``git log`` call."""
    out = subprocess.run(
        ["git", "log", "--no-merges", "--no-renames", "--format=%x1e%H%x1f%B%x1f",
         "--name-only", "-z", rng],
        cwd=root, capture_output=True, check=True)
    commits: list[tuple[str, str, tuple[str, ...]]] = []
    for chunk in out.stdout.decode("utf-8", errors="replace").split("\x1e"):
        if not chunk.strip("\x00\n"):
            continue
        sha, _, rest = chunk.partition("\x1f")
        message, _, names = rest.partition("\x1f")
        paths = tuple(p.strip("\n") for p in names.split("\x00") if p.strip("\n"))
        commits.append((sha.strip(), message, paths))
    return commits


def _declared_paths(index: Mapping[str, Any], record_id: str) -> set[str]:
    from plumb.hashing import target_path

    record = index.get(record_id)
    if record is None:
        return set()
    out = {record.path}
    for link in record.links:
        if link.kind in ("implemented_by", "verified_by"):
            path = target_path(link.target)
            if path:
                out.add(path)
    return out


def claims_check(root: Path, rng: str | None = None) -> dict[str, Any]:
    """Undeclared paths over a range (default: the commits not on ``main``)."""
    from plumb.api import open_core

    root = Path(root)
    policy = load_policy(root)
    core = open_core(root)
    index = core.index()
    aliases = _trailer_aliases(core)
    rng = rng or _default_range(root)
    commits = read_range(root, rng)
    baseline = {(b.commit, b.path) for b in policy.baseline if b.nc}
    undeclared: list[Undeclared] = []
    waived: list[dict[str, str]] = []
    unclaimed: list[str] = []
    for sha, message, paths in commits:
        ids = claimed_ids(aliases, sha, message)
        if not ids:
            if any(exempting_glob(policy, p) is None for p in paths):
                unclaimed.append(sha)
            continue
        declared: set[str] = set()
        for record_id in ids:
            declared |= _declared_paths(index, record_id)
        for path in paths:
            if path in declared or exempting_glob(policy, path) is not None:
                continue
            if any(sha.startswith(c) and p == path for c, p in baseline):
                waived.append({"commit": sha, "path": path})
                continue
            undeclared.append(Undeclared(sha, path, ids))
    return {"range": rng, "commits": len(commits),
            "undeclared": [{"commit": u.commit, "path": u.path, "claims": list(u.claims)}
                           for u in undeclared],
            "baseline": waived, "unclaimed_commits": unclaimed,
            "problems": list(policy.problems)}


def _trailer_aliases(core: Any) -> Any:
    """``{(sha, old id): new id}``: in the incoming commits a ``renumber`` lists, the old
    ID means the new one (sp6 5.5); history keeps its trailers. Empty without renumbers."""
    if not any(e.kind == "renumber" for e in core.events()):
        return {}
    from plumb import ids

    return ids.trailer_aliases(core)


def trailer_aliases(core: Any) -> Any:
    """The renumber map every reader of past ``SR:`` trailers uses (``claimed_ids``)."""
    return _trailer_aliases(core)


def claimed_ids(aliases: Any, sha: str, message: str) -> tuple[str, ...]:
    """The IDs commit ``sha``'s ``SR:`` trailer claims, read through every ``renumber``
    (sp6 5.5): the one reader of a past commit's trailers (``claims_check``, the merge
    boundary's touched requirements)."""
    return _mapped(aliases, sha, parse_sr_trailer(message))


def _mapped(aliases: Any, sha: str, claimed: tuple[str, ...]) -> tuple[str, ...]:
    if not aliases:
        return claimed
    from plumb.ids.aliases import map_trailer

    return map_trailer(aliases, sha, claimed)


def _default_range(root: Path) -> str:
    for base in ("main", "master"):
        probe = subprocess.run(["git", "rev-parse", "--verify", "-q", base], cwd=root,
                               capture_output=True, text=True)
        if probe.returncode == 0:
            return f"{base}..HEAD"
    return "HEAD"


# --------------------------------------------------------------------------- commands


def _parser(prog: str, description: str) -> Any:
    import argparse

    from plumb.cliutil import add_common

    parser = argparse.ArgumentParser(prog=prog, description=description)
    add_common(parser)
    return parser


def _cmd_check_msg(argv: list[str]) -> int:
    from plumb.cliutil import resolve_root

    parser = _parser("plumb trailers check-msg", "Check a commit message's SR: trailer.")
    parser.add_argument("file", help="the commit message file (git passes it as $1)")
    args = parser.parse_args(argv)
    try:
        message = Path(args.file).read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        print(f"plumb: cannot read the commit message: {exc}", file=sys.stderr)
        return 2
    code, lines = check_msg(resolve_root(args.root), message)
    for line in lines:
        print(line, file=sys.stderr if code else sys.stdout)
    return code


def _cmd_install_hook(argv: list[str]) -> int:
    from plumb.cliutil import resolve_root

    parser = _parser("plumb trailers install-hook",
                     "Write the git commit-msg hook that runs `plumb trailers check-msg`.")
    parser.add_argument("--interpreter", default=sys.executable,
                        help="Python that runs the hook (default: this one)")
    args = parser.parse_args(argv)
    try:
        path = install_commit_msg_hook(resolve_root(args.root), args.interpreter)
    except ForeignHookError as exc:
        print(f"plumb: {exc}", file=sys.stderr)
        return 1
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"plumb: commit-msg hook not installed: {exc}", file=sys.stderr)
        return 1
    print(f"plumb: commit-msg hook installed ({path})")
    return 0


def _cmd_claims_check(argv: list[str]) -> int:
    from plumb.cliutil import emit, resolve_root

    parser = _parser("plumb claims check",
                     "Report paths changed by commits that claim SRs but declare no link to "
                     "them.")
    parser.add_argument("--range", dest="rng", default=None,
                        help="git range BASE..HEAD (default: main..HEAD)")
    args = parser.parse_args(argv)
    try:
        result = claims_check(resolve_root(args.root), args.rng)
    except subprocess.CalledProcessError as exc:
        print(f"plumb: cannot read the range: {(exc.stderr or b'').decode(errors='replace')}",
              file=sys.stderr)
        return 2
    if args.as_json:
        emit(result, True)
    else:
        lines = [f"plumb claims: {result['commits']} commit(s) in {result['range']}"]
        for row in result["undeclared"]:
            lines.append(f"undeclared: {row['commit'][:12]} {row['path']} "
                         f"(claims {', '.join(row['claims'])})")
        for row in result["baseline"]:
            lines.append(f"baseline: {row['commit'][:12]} {row['path']}")
        for sha in result["unclaimed_commits"]:
            lines.append(f"no {TRAILER_KEY}: trailer: {sha[:12]}")
        for problem in result["problems"]:
            lines.append(f"claims.yaml: {problem}")
        if not result["undeclared"]:
            lines.append("no undeclared paths")
        emit(lines, False)
    return 1 if result["undeclared"] else 0


_TRAILER_SUBS = {"check-msg": _cmd_check_msg, "install-hook": _cmd_install_hook}
_CLAIMS_SUBS = {"check": _cmd_claims_check}
_USAGE = {"trailers": "usage: plumb trailers {check-msg FILE | install-hook} [--root R]",
          "claims": "usage: plumb claims check [--range BASE..HEAD] [--json] [--root R]"}


def run(command: str, argv: list[str]) -> int:
    subs = _TRAILER_SUBS if command == "trailers" else _CLAIMS_SUBS
    if not argv or argv[0] in ("-h", "--help"):
        print(_USAGE[command])
        return 0 if argv else 2
    handler = subs.get(argv[0])
    if handler is None:
        print(f"plumb {command}: unknown subcommand '{argv[0]}'\n{_USAGE[command]}",
              file=sys.stderr)
        return 2
    try:
        return handler(argv[1:])
    except SystemExit as exc:  # argparse --help or usage error
        return int(exc.code or 0) if isinstance(exc.code, int) else 2

