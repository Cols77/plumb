"""The debug workflow (SR-220, SR-221, SR-300), standalone: ``plumb debug [ID ...] [--dry-run]``.

The cases plumb could not settle on its own (today: stale and dangling links) are rerun once
through the step the turn end runs, ``links.repin_after_tests`` (tests, then the meaning
cascade). What each case did and what it still needs is reported as text; a record whose
meaning changed under a decision becomes one owner question through the question tool (SR-300
EX-3), never a card. The plumb line counts the cases in debugging and the ones resolved.
Nothing here confirms anything or changes a record's meaning.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

LINE = "plumb: debug: {n} cases, {resolved} resolved, {open} still in debugging"
STORE = (".plumb", "cache", "debug")
DANGLING = "its target no longer exists, so there is nothing to repin to: relink it"
OWN_KINDS = frozenset({"landing-step", "validate"})   # DEC-316: plumb's own, at a landing
READY_REPIN = ("plumb: the repins of {branch} ({detail}) are committed, tests passed: ready to "
               "land; merge it like any branch, through the merge check")
READY = ("plumb: self-fix {branch} ({kind}: {detail}) is committed and reviewed: ready to "
         "land; merge it like any branch, through the merge check")
FIXED = ("plumb: the plumb defect you hit is fixed in main ({kind}: {detail}); retry {retry}: "
         "until that works the case reads landed, not proven (then plumb debug done {id})")
RELOAD = ("plumb: the plumb defect you hit ({kind}: {detail}) is fixed in main, reload plugins: "
          "this session runs another build ({built}); then retry {retry}")
CAME_BACK = ("plumb: the plumb defect {id} came back ({kind}: {detail}): the old case is "
             "reopened with its history ({n} earlier) and its fix runs again; plumb debug lists it")
# SR-367 (DEC-372): a known problem that changes warns the session that owns its case
PROVEN = ("plumb: the plumb defect you hit is proven fixed ({kind}: {detail}): nothing is left "
          "to retry for it")
BACK_ELSEWHERE = ("plumb: the plumb defect you hit came back in another session ({kind}: "
                  "{detail}): the case is reopened there with its history ({n} earlier); "
                  "plumb debug lists it")
LANDED = "landed, not proven"
REGISTER = (".plumb", "known-issues.json")
RECENT_DAYS = 14
RETRY = {"hook-error": "what ran the {target} hook", "landing-step": "the landing's {target} step",
         "validate": "plumb validate", "report": "what you flagged", "job-failed": "the job"}


def _case_path(root: Path | str, case_id: str) -> Path:
    return Path(root).joinpath(*STORE, re.sub(r"[^\w.-]", "_", case_id) + ".json")


def _same(text: str) -> str:
    """One cause, one id: the digest ignores the numbers (a pid, a line number)."""
    return hashlib.sha1(re.sub(r"\d+", "", text).encode()).hexdigest()[:8]


def open_case(root: Path | str, *, id: str, kind: str, target: str, detail: str,
              log: str = "", session: str | None = None) -> str | None:
    """SR-325: one case file per id, written the moment a failure happens (idempotent; a
    failure to write it is swallowed, since it runs inside the failing step). It keeps the
    session that detected it (DEC-318), told there once its fix is in main (``lines``).
    SR-356, SR-357: a case is found by its symptom too, and a known issue's symptom is that
    issue's case; a closed one seen again reopens with its history, unless its fix is in main
    and this session runs an older plugin (then the session is told to reload plugins).
    Returns the case's id."""
    try:
        from plumb import build, stale

        where = session or stale.current_session(root)
        symptom = _same(f"{kind}:{target}:{detail}")
        issue = known_issue(root, detail)
        id = issue["id"] if issue else id
        rows = all_cases(root)
        old = next((r for r in rows if r["id"] == id), None) or next(
            (r for r in rows if r.get("symptom") == symptom), None)
        fixed = bool(issue) and issue.get("state") == "fixed"
        row = old or {"id": id, "kind": kind, "target": target, "detail": detail,
                      "state": "open", "log": log, "session": where, "symptom": symptom,
                      **({"issue": issue["id"]} if issue else {})}
        if old is None and not fixed:
            return _write_case(root, row, queue=True)
        if old is not None and (old.get("state") == "open"
                                or (old.get("branch") and not old.get("landed"))):
            return str(old["id"])  # still open, or its fix waits to land: nothing new
        landed = (old or {}).get("landed") or (issue or {}).get("fix")
        if landed and build.outdated(root)[0]:   # SR-357 EX-2: fixed in main, not loaded here
            return _write_case(root, {**row, "state": "resolved", "landed": str(landed),
                                      "session": where})
        prior = old or {"state": "fixed"}   # a known issue fixed before any case of it here
        was = {**{k: prior.get(k) for k in ("state", "proven", "session", "detail")},
               "landed": landed}
        was = {k: str(v) for k, v in was.items() if v}
        kept = {k: v for k, v in row.items() if k not in ("branch", "landed", "proven")}
        return _write_case(root, {**kept, "state": "open", "session": where, "detail": detail,
                                  "came_back": where,
                                  "history": [*prior.get("history", []), was]},
                           queue=True)
    except Exception:  # noqa: BLE001 - recording a case never fails the step that failed
        return None


def _write_case(root: Path | str, row: dict[str, Any], queue: bool = False) -> str:
    path = _case_path(root, row["id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, ensure_ascii=False, indent=1), encoding="utf-8")
    if queue:
        _queue_fix(root, row["id"])
    return str(row["id"])


def known_issues(root: Path | str) -> list[dict[str, Any]]:
    """SR-357: the register of known issues (``.plumb/known-issues.json``); none when absent."""
    try:   # JSON, not YAML: the session-start hook never imports yaml (HC2)
        data = json.loads(Path(root).joinpath(*REGISTER).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    rows = data.get("issues") if isinstance(data, dict) else None
    return [r for r in rows or [] if isinstance(r, dict) and r.get("id") and r.get("symptom")]


def known_issue(root: Path | str, text: str) -> dict[str, Any] | None:
    """The known issue whose symptom (a case-insensitive pattern) ``text`` shows, if any."""
    for row in known_issues(root):
        try:
            if re.search(str(row["symptom"]), text, re.IGNORECASE):
                return row
        except re.error:
            continue
    return None


def known_lines(root: Path | str, today: datetime.date | None = None) -> list[str]:
    """SR-357 EX-1: for the session start, the open known issues and the ones fixed lately (an
    issue whose case is open again counts as open), in one or two lines."""
    issues = known_issues(root)
    cases = {r["id"]: r for r in all_cases(root)} if issues else {}
    since = (today or datetime.date.today()) - datetime.timedelta(days=RECENT_DAYS)

    def recent(row: dict[str, Any]) -> bool:
        try:
            return datetime.date.fromisoformat(str(row.get("fixed"))[:10]) >= since
        except ValueError:
            return False

    def named(rows: list[dict[str, Any]]) -> str:
        return "; ".join(f"{r['id']} {r.get('title') or r['symptom']}" for r in rows)

    out, opened = [], [r for r in issues if _is_open(r, cases)]
    fixed = [r for r in issues if not _is_open(r, cases) and recent(r)]
    if opened:
        out.append(f"plumb: known issues open: {named(opened)}")
    if fixed:
        out.append(f"plumb: known issues fixed lately: {named(fixed)}; seen again: "
                   "plumb debug report <what you saw>")
    return out


def _is_open(row: dict[str, Any], cases: dict[str, dict[str, Any]]) -> bool:
    """A known issue is open unless fixed; a fixed one whose case reopened is open again."""
    return row.get("state") != "fixed" or cases.get(row["id"], {}).get("state") == "open"


def known_pane(root: Path | str) -> dict[str, Any]:
    """SR-367: what the band's known problems line counts and its pane lists (``plumb mod
    known``): each issue's symptom, cause, fix, state and its case's history, open ones first."""
    issues = known_issues(root)
    cases = {r["id"]: r for r in all_cases(root)} if issues else {}
    rows = []
    for row in issues:
        case = cases.get(row["id"], {})
        history = [", ".join(filter(None, (h.get("state"), h.get("landed") and f"fix {h['landed']}",
                                           h.get("proven") and f"proven {h['proven']}",
                                           h.get("detail"))))
                   for h in case.get("history", []) if isinstance(h, dict)]
        if case.get("state") == "open" and case.get("history"):
            history.append(f"open again: {case.get('detail', '')}")
        rows.append({**{k: str(row.get(k) or "") for k in
                        ("id", "title", "symptom", "cause", "fix", "fixed")},
                     "state": "open" if _is_open(row, cases) else "fixed", "history": history})
    rows.sort(key=lambda r: r["state"] != "open")   # stable: the register's order within each
    return {"open": sum(r["state"] == "open" for r in rows), "issues": rows}


def _queue_fix(root: Path | str, case_id: str) -> None:
    """SR-326: in plumb's own repository the case also becomes a background self-debug job."""
    from plumb import selfdebug, stale
    from plumb.api import open_core
    from plumb.understand import queue
    from plumb.understand import selfdebug as kind

    core = open_core(Path(root))
    if selfdebug.applies(core) is None:
        queue.enqueue(core, kind.build(core, stale.current_session(core.root), case=case_id))


def all_cases(root: Path | str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(Path(root).joinpath(*STORE).glob("*.json")):
        try:
            row = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(row, dict) and row.get("id"):
            out.append(row)
    return out


def open_cases(root: Path | str) -> list[dict[str, Any]]:
    return [r for r in all_cases(root) if r.get("state") == "open"]


def state(row: dict[str, Any]) -> str:
    """SR-356: ``open``, ``landed, not proven`` (its fix is in main, not yet checked live in a
    session running that build) or ``resolved``."""
    if row.get("state") == "open":
        return "open"
    return LANDED if row.get("landed") and not row.get("proven") else "resolved"


def _update(root: Path | str, ids: list[str], **fields: Any) -> int:
    changed = 0
    for case_id in ids:
        path = _case_path(root, case_id)
        try:
            row = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            continue
        if any(row.get(k) != v for k, v in fields.items()):
            path.write_text(json.dumps({**row, **fields}, ensure_ascii=False, indent=1),
                            encoding="utf-8")
            changed += 1
    return changed


def resolve(root: Path | str, ids: list[str]) -> int:
    """Mark cases resolved; returns how many changed."""
    return _update(root, ids, state="resolved")


def report(root: Path | str, id: str, text: str) -> None:
    _update(root, [id], report=text)


def hook_error(root: Path | None, name: str, detail: str) -> None:
    """SR-325 EX-1: a hook that raised leaves one case, the same error once. The id ignores
    the numbers in the traceback (a temp file's pid, line numbers), so one cause is one case
    and one background fix, not one per process that hit it."""
    if root is None:
        return
    lines = detail.strip().splitlines()
    open_case(root, id=f"hook-{name}-{_same(detail)}",
              kind="hook-error", target=name, detail=lines[-1] if lines else name, log=detail)


def from_landing(root: Path | str, found: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """DEC-316: where self-debug runs, plumb's own defects a landing found (a failed step, a
    validate error) open real cases, queued for the background fix like hook errors; the
    cases left (stale links, judge questions, tests) stay with the agent (SR-300)."""
    from plumb import selfdebug
    from plumb.api import open_core

    try:
        if selfdebug.applies(open_core(Path(root))) is not None:
            return found
    except Exception:  # noqa: BLE001 - the landing's cases are never lost
        return found
    for c in found:
        if c["kind"] in OWN_KINDS:
            open_case(root, id=f"{c['id']}-{_same(str(c['detail']))}", kind=c["kind"],
                      target=str(c["target"]), detail=str(c["detail"]))
    return [c for c in found if c["kind"] not in OWN_KINDS]


def landed(root: Path | str, head: str) -> None:
    """DEC-318: at a landing, a fixed case whose branch is now in main is marked landed."""
    for row in all_cases(root):
        if row.get("branch") and not row.get("landed") and subprocess.run(
                ["git", "merge-base", "--is-ancestor", str(row["branch"]), head], cwd=root,
                capture_output=True).returncode == 0:
            _update(root, [row["id"]], landed=head)


def lines(root: Path | str, session: str) -> list[tuple[str, str]]:
    """``(key, text)`` for the agent's next prompt: each committed, reviewed self-fix not yet
    in main is ready to land (DEC-317: plumb never merges it); a case this session detected
    whose fix is in main is fixed, with what to retry (DEC-318: nothing held it). SR-356: it
    reads landed, not proven, or says to reload plugins when this session runs an older build;
    a case that came back in this session says so, with its history. SR-367: the session that
    owns a case is told when it is proven, or when it came back in another session."""
    from plumb import build

    out: list[tuple[str, str]] = []
    late: tuple[bool, str] | None = None
    for row in all_cases(root):
        what = {k: str(row.get(k) or "") for k in ("id", "branch", "kind", "detail", "target")}
        n = len(row.get("history") or [])
        before = (row.get("history") or [{}])[-1]
        if row.get("state") == "open" and row.get("came_back") == session:
            out.append((f"back:{row['id']}:{n}", CAME_BACK.format(n=n, **what)))
        elif row.get("state") == "open" and row.get("came_back") and isinstance(
                before, dict) and before.get("session") == session:
            out.append((f"back:{row['id']}:{n}", BACK_ELSEWHERE.format(n=n, **what)))
        elif row.get("branch") and not row.get("landed"):
            out.append((f"ready:{row['id']}",
                        (READY_REPIN if what["kind"] == "repin" else READY).format(**what)))
        elif state(row) == LANDED and row.get("session") == session:
            retry = RETRY.get(what["kind"], "what failed ({target})").format(**what)
            late = late or build.outdated(root)
            out.append((f"reload:{row['id']}", RELOAD.format(retry=retry, built=late[1], **what))
                       if late[0] else (f"fixed:{row['id']}", FIXED.format(retry=retry, **what)))
        elif row.get("proven") and row.get("session") == session:
            out.append((f"proven:{row['id']}", PROVEN.format(**what)))
    return out


def flag(root: Path | str, words: str) -> str:
    """DEC-319: what the owner or the agent noticed (a wrong result, not a crash) is a case,
    queued for the same background fix as a crash."""
    case_id = f"report-{_same(words)}"
    return open_case(root, id=case_id, kind="report", target="flagged", detail=words) or case_id


def cases(core: Any, selectors: list[str], *, dry_run: bool = False,
          session: str | None = None, **test_doubles: Any) -> list[dict[str, str]]:
    """One ``{case, state, what}`` per stale or dangling link of ``selectors`` (record IDs or
    link ids; none: every record with one). ``state`` is ``resolved``, ``would resolve`` (dry
    run) or ``open``; ``what`` says what happened or what is missing."""
    from plumb import stale
    from plumb.links import LinkError, repin_after_tests

    states = [s for s in core.link_states() if s.state in ("stale", "dangling")]
    records = selectors or sorted({s.link.source for s in states})
    where = session or stale.current_session(core.root)
    out: list[dict[str, str]] = []
    for record in records:
        wanted = record.split("#")[0]
        out += [{"case": s.link.id, "state": "open", "what": DANGLING} for s in states
                if s.state == "dangling" and s.link.source == wanted
                and (record == wanted or s.link.id == record)]
        try:
            step = repin_after_tests(core, record, session=where, dry_run=dry_run,
                                     **test_doubles)
        except LinkError as exc:
            out.append({"case": record, "state": "open", "what": str(exc)})
            continue
        out += [{"case": c["link"], "state": "resolved",
                 "what": f"repinned ({c.get('tier', 'tests pass')})"} for c in step.changes]
        out += [{"case": link, "state": "would resolve", "what": why} for link, why in step.would]
        out += [{"case": link, "state": "open", "what": why} for link, why in step.refused]
    return out


def _store_cases(root: Path | str, found: list[dict[str, str]],
                 dry_run: bool) -> list[dict[str, str]]:
    """The store's cases beside the links: a refused link whose rerun resolved it (or that is
    no longer stale) is marked resolved; the other kinds have no step to rerun yet."""
    out: list[dict[str, str]] = []
    for row in all_cases(root):
        link = str(row["target"])
        if row.get("state") == "open" and row.get("kind") == "stale-refused":
            mine = [c for c in found if c["case"] == link]
            if all(c["state"] == "resolved" for c in mine) and not dry_run:
                resolve(root, [row["id"]])
                row["state"] = "resolved"
            if mine:
                continue  # listed with the links
        out.append({"case": row["id"], "state": state(row),
                    "what": str(row.get("report") or row.get("detail") or row.get("kind"))})
    return out


def _elsewhere(core: Any, still_open: set[str]) -> None:
    """SR-327: outside plumb's own repository a case whose rerun failed again ends with a
    defect report (or, configured, a fix in the source checkout), once."""
    from plumb import selfdebug

    if selfdebug._own(Path(core.root)):
        return
    for row in open_cases(core.root):
        if row["id"] in still_open and not row.get("report"):
            if line := selfdebug.handle(core, row).line:
                print(line)


def _done(root: Path | str, ids: list[str]) -> int:
    """``plumb debug done <id>...``: cases settled by hand are resolved. SR-356 EX-1: a landed
    case is proven only from a session running main's build (where it was checked live)."""
    from plumb import build

    late, built = build.outdated(root)
    held = [r["id"] for r in all_cases(root)
            if late and r["id"] in ids and state(r) == LANDED]
    for case_id in held:
        print(f"plumb: debug: {case_id} stays {LANDED}: this session runs another build "
              f"({built}); check it again once it runs the fix, then plumb debug done {case_id}")
    done = _update(root, [i for i in ids if i not in held], state="resolved",
                   proven=datetime.date.today().isoformat())
    print(f"plumb: debug: {done} cases marked resolved")
    return 1 if held else 0


def _fix(core: Any, ids: list[str]) -> int:
    """``plumb debug fix [id]``: the self-debug workflow on demand (SR-326)."""
    from plumb import selfdebug

    if (why := selfdebug.applies(core)) is not None:
        print(f"plumb: debug fix: {why}")
        return 1
    todo = [c for c in open_cases(core.root) if not ids or c["id"] in ids]
    outcomes = [(c["id"], selfdebug.fix(core, c)) for c in todo]
    for case_id, out in outcomes:
        print(out.line or f"  {case_id}: {out.state}: {out.detail}")
    return 0 if outcomes and all(o.state == "fixed" for _, o in outcomes) else 1


def on_branch(core: Any, work: Any, *, dry_run: bool = False) -> tuple[Any, str]:
    """SR-351 (DEC-323): ``work(core)`` -> result, made in plumb's own repository in a worktree
    on ``debug/repin`` (built from main's committed head, so uncommitted or untracked work in
    main is not seen), the edits committed there with the SR trailer and announced as ready to
    land (``lines``); the checkout is left unchanged. The branch starts over from main's head
    each pass (the links are re-derived, so an unlanded earlier commit is replaced, and kept
    when this pass changes nothing). Elsewhere, ``work(core)`` runs in place. ``(result,
    error)``: error says why the commit failed (the edits are then dropped)."""
    from plumb import selfdebug
    from plumb.api import open_core

    root = Path(core.root)
    if dry_run or not (root / ".git").is_dir() or not selfdebug._own(root):
        return work(core), ""
    wt = prev = result = None
    try:
        wt, branch = selfdebug._worktree(root, "repin")
        prev = selfdebug._git(wt, "rev-parse", "HEAD").strip()
        head = selfdebug._git(root, "rev-parse", "HEAD").strip()
        selfdebug._git(wt, "reset", "-q", "--hard", head)
        wt_core = open_core(wt)
        result = work(wt_core)
        selfdebug._git(wt, "add", "-u")
        changed = selfdebug._git(wt, "diff", "--cached", "--name-only").split()
        if not changed:
            selfdebug._git(wt, "reset", "-q", "--hard", prev)
            return result, ""
        names = sorted({Path(f).stem for f in changed})
        linked = {link.target.record for n in names if n in wt_core.index()
                  for link in wt_core.index()[n].links if link.target.record}
        # only live requirements: a link may name one that left the tree (supersedes)
        srs = sorted({n for n in (*names, *linked)
                      if n.startswith("SR-") and n in wt_core.index()})
        sr_line = f"SR: {', '.join(srs)}\n\n" if srs else ""
        text = (f"Repin the stale links of {', '.join(names)}\n\n{sr_line}"
                "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>\n")
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False,
                                         encoding="utf-8") as f:
            f.write(text)
        try:
            selfdebug._git(wt, "commit", "-q", "-F", f.name)
        finally:
            Path(f.name).unlink(missing_ok=True)
    except Exception as exc:  # noqa: BLE001 - the case is reported open with the reason
        if wt is not None:
            selfdebug._git(wt, "reset", "-q", "--hard", *([prev] if prev else []), check=False)
            selfdebug._git(wt, "clean", "-fdq", check=False)
        why = str(getattr(exc, "stderr", None) or exc).strip()
        return result, f"the repin pass failed: {why}"
    for row in all_cases(root):   # one announcement: an unlanded earlier pass is replaced
        if row.get("kind") == "repin" and not row.get("landed"):
            _case_path(root, row["id"]).unlink(missing_ok=True)
    sha = selfdebug._git(wt, "rev-parse", "--short", "HEAD").strip()
    path = _case_path(root, f"repin-{sha}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"id": f"repin-{sha}", "kind": "repin", "target": branch,
                                "detail": f"repinned {', '.join(names)}", "state": "resolved",
                                "branch": branch}, indent=1), encoding="utf-8")
    return result, ""


def _pass(core: Any, selectors: list[str], dry_run: bool) -> list[dict[str, str]]:
    found, error = on_branch(core, lambda c: cases(c, selectors, dry_run=dry_run),
                             dry_run=dry_run)
    if error and found is None:
        return [{"id": "repin", "state": "open", "what": error}]
    if error:
        found = [{**c, "state": "open", "what": error} if c["state"] == "resolved" else c
                 for c in found]
    return found


def run(command: str, argv: list[str]) -> int:
    import argparse

    from plumb.api import open_core
    from plumb.cliutil import add_common, emit, resolve_root

    parser = argparse.ArgumentParser(
        prog=f"plumb {command}",
        description="Run the debug cases once (stale links through tests and the meaning "
                    "cascade) and say what each did and what it still needs. Never confirms.",
        epilog="also: plumb debug fix [<case id>...] runs the self-debug workflow on open "
               "cases; plumb debug done <case id>... closes cases settled by hand; plumb debug "
               "report <words> opens a case from a description")
    add_common(parser)
    parser.add_argument("selector", nargs="*", help="record IDs or link ids; default: all")
    parser.add_argument("--dry-run", action="store_true",
                        help="ask the models only: no tests, no repin, no owner question")
    args = parser.parse_args(argv)
    core = open_core(resolve_root(args.root))
    if args.selector[:1] == ["done"]:
        return _done(core.root, args.selector[1:])
    if args.selector[:1] == ["fix"]:
        return _fix(core, args.selector[1:])
    if args.selector[:1] == ["report"]:
        words = " ".join(args.selector[1:]).strip()
        if not words:
            print("usage: plumb debug report <what is wrong, in words>", file=sys.stderr)
            return 2
        from plumb import stale

        case_id = flag(core.root, words)   # SR-357: a known issue's symptom is that issue
        said = [text for key, text in lines(core.root, stale.current_session(core.root))
                if key.split(":")[1] == case_id]
        print("\n".join(said) or f"plumb: debug: case {case_id} opened; the fix runs in the "
              "background")
        return 0
    found = _pass(core, args.selector, args.dry_run)
    if not args.selector:
        found += _store_cases(core.root, found, args.dry_run)
        if not args.dry_run:
            _elsewhere(core, {c["case"] for c in found if c["state"] == "open"})
    resolved = sum(c["state"] not in ("open", LANDED) for c in found)
    if args.as_json:
        emit({"cases": found, "resolved": resolved}, True)
    else:
        print(LINE.format(n=len(found), resolved=resolved, open=len(found) - resolved))
        for c in found:
            print(f"  {c['case']}: {c['state']}: {c['what']}")
    return 1 if resolved < len(found) else 0


if __name__ == "__main__":
    sys.exit(run("debug", sys.argv[1:]))
