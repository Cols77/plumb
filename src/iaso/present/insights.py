"""SR-374: what iaso tells the coding agent, as one table: condition -> builder -> lines.

``TABLE[condition](core, ctx)`` returns ``delta.Line`` items; a hook passes them through its
once-per-session emitter (``present/delta.py``), so each fact is said once per session per
state and nothing is said when nothing applies. ``iaso context <condition> [<arg>]`` runs
the same builders with ``full`` set and no filter, for the full picture of one condition.

``ctx`` is a plain mapping: ``session``, ``text`` (a message), ``path`` (an edited file),
``node`` and ``regression`` (a failing test), ``report`` (a merge report), ``hook`` and
``step`` (a cut), ``summary`` (the session start's tests summary), ``full``. Standard
library only at import: each builder imports what it needs.
"""

from __future__ import annotations

from iaso.paths import state_dir

import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from iaso.present.delta import Line

BRIEF_SEEN = "brief_seen.json"   # .iaso/session/: record hashes at the last session brief
SHOWN = 5


def _clip(text: str, width: int = 160) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= width else text[: width - 3] + "..."


# -- (1) session start, resume, compaction ------------------------------------------------


def intent_line(core: Any, ctx: Mapping[str, Any]) -> Line | None:
    """The intent being worked on, in one line: title, the loop's step, what is left."""
    session = ctx.get("session")
    if not session:
        return None
    from iaso.understand.cmd_intent import STAGES, _passed, loops

    found = [d for _, d in loops(Path(core.root), str(session))
             if not _passed(d, "build") and not d.get("handed_to")]
    if not found:
        return None
    data = found[-1]
    intent = str(data.get("intent") or "")
    record = core.index().get(intent) if intent else None
    named = f"{intent} {record.title}" if record is not None else (intent or "an intent")
    text = str(ctx.get("text") or "")
    if intent and not ctx.get("full") and (intent in text or (
            record is not None and record.title.lower() in text.lower())):
        return None   # EX-2: the message names it
    tasks = data.get("tasks") if isinstance(data.get("tasks"), Mapping) else {}
    step = str(data.get("step") or "")
    left = [str(x) for x in tasks.get("left") or ()] or [
        s for s in STAGES if not _passed(data, s) and s != step]
    now = ""
    if tasks.get("label"):
        total = f"/{tasks['total']}" if tasks.get("total") else ""
        now = f"; now {tasks['label']} {tasks.get('done') or 0}{total}"
    line = (f"iaso: working on {named}: step {step}{now}"
            + (f"; left: {', '.join(left)}" if left else ""))
    return Line(_clip(line, 240), subject="intent-line",
                state=f"{intent}|{step}|{json.dumps(tasks, sort_keys=True)}")


def _questions_line(core: Any) -> Line | None:
    """A question waiting on a record this checkout's branch changes (SR-374, SR-361)."""
    from iaso.understand import judge

    sessions = state_dir(Path(core.root)) / "session"
    ours = None
    for path in sorted(sessions.glob("*/judge_questions.json")):
        try:
            ours = judge.work_ids(core) if ours is None else ours
            asked = [q for q in judge.open_questions(core, path.parent.name)
                     if judge._ids_of(q) & ours]
        except Exception:  # noqa: BLE001 - a brief never fails on the judge's file
            continue
        if asked:
            said = str(asked[0].get("question") or "").rsplit("\n\n", 1)[-1]
            return Line(_clip(f"iaso: a question waits for the owner: {said}"),
                        subject="questions-waiting", state=said)
    return None


def changed_lines(core: Any, *, mark: bool) -> list[Line]:
    """The records new or changed since the last session brief (``brief_seen.json``); with
    ``mark`` the current hashes become the reference. Nothing on a first brief."""
    path = state_dir(Path(core.root)) / "session" / BRIEF_SEEN
    try:
        before = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        before = None
    index = core.index()
    now = {i: r.hash for i, r in index.items()}
    if mark:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(now, sort_keys=True), encoding="utf-8")
        except OSError:
            pass
    if not isinstance(before, dict):
        return []
    changed = sorted(i for i, h in now.items() if before.get(i) != h)
    if not changed:
        return []
    shown = "; ".join(f"{i} {index[i].title}" for i in changed[:SHOWN])
    more = "; and more (iaso brief --all)" if len(changed) > SHOWN else ""
    return [Line(_clip(f"iaso: changed since you last looked: {shown}{more}", 400),
                 subject="changed-since", state=",".join(f"{i}={now[i]}" for i in changed))]


def blocks_line(summary: Mapping[str, Any] | None) -> str | None:
    """What the tests block now: regressions, then tests that never passed; no counts of
    fresh evidence (EX-9)."""
    if not summary or summary.get("background"):
        return None
    regressions, failing = list(summary.get("regressions") or ()), list(
        summary.get("not_yet") or ())
    parts = []
    if regressions:
        parts.append("regression (passed before, fails now): " + ", ".join(regressions[:3]))
    if failing:
        parts.append("not yet passing: " + ", ".join(failing[:3]))
    return "iaso: tests block now: " + " | ".join(parts) if parts else None


def session(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(1): the intent line, the questions waiting, the open known issues, the records
    changed since the agent last saw them, and what the tests block now."""
    from iaso import debug

    out = [line for line in (intent_line(core, ctx), _questions_line(core)) if line]
    try:
        out += [Line(text) for text in debug.known_lines(core.root)]
    except Exception:  # noqa: BLE001 - a broken register never costs the brief
        pass
    out += changed_lines(core, mark=not ctx.get("full"))
    blocks = blocks_line(ctx.get("summary"))
    if blocks:
        out.append(Line(blocks))
    return out


# -- (2) and (5) a message: the intent when not named, a known issue it shows --------------


def symptom(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(5): the open known issue the words show, with its cause and fix or workaround."""
    from iaso import debug

    text = str(ctx.get("text") or "")
    row = debug.known_issue(core.root, text) if text.strip() else None
    if row is None:
        return []
    cases = {r["id"]: r for r in debug.all_cases(core.root)}
    if not debug._is_open(row, cases):
        return []
    parts = [f"iaso: known issue {row['id']} {row.get('title') or row['symptom']}"]
    if row.get("cause"):
        parts.append(f"cause: {row['cause']}")
    if row.get("fix"):
        parts.append(f"fix or workaround: {row['fix']}")
    return [Line(_clip("; ".join(parts), 400), subject=f"known:{row['id']}",
                 state=str(row.get("state") or "open"))]


def prompt(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(2) and (5): the intent line when the message does not name it, a known issue."""
    line = intent_line(core, ctx)
    return [*([line] if line else []), *symptom(core, ctx)]


# -- (3) an edit ---------------------------------------------------------------------------


def edit(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(3): each requirement the file serves, with its examples and covering tests; in full,
    the examples' words, the tests' states, the links and the stale ones."""
    from iaso import stale

    rel = str(ctx.get("path") or "")
    full = bool(ctx.get("full"))
    index = core.index()
    ids = list(dict.fromkeys(end.record for end in stale.links_touching(core.root, rel)))
    out: list[Line] = []
    for rid in ids:
        record = index.get(rid)
        if record is None:
            continue
        examples = [e.id for e in record.examples]
        tests = sorted({link.target.test or link.target.path or "" for link in record.links
                        if link.kind == "verified_by"} - {""})
        if not full:
            out.append(Line(_clip(
                f"iaso: {rel} serves {rid} {record.title}; examples "
                + (", ".join(examples) or "none") + "; tests "
                + (", ".join(tests[:SHOWN]) or "none")
                + (" and more (iaso context edit " + rel + ")" if len(tests) > SHOWN else ""),
                400), subject=f"serves:{rel}:{rid}", state=record.hash, record=rid))
            continue
        from iaso.explain import _example_text, _tests

        out.append(Line(f"{rid} {record.title}"))
        out += [Line("  example " + _example_text(e)) for e in record.examples]
        out += [Line("  test " + t) for t in (_tests(core, rid) or tests)]
        out += [Line(f"  link {link.id} {link.kind} {link.target.path or link.target.record}"
                     + (f"::{link.target.symbol}" if link.target.symbol else ""))
                for link in record.links if link.target.path == rel]
    if full:
        drift = [Line("  stale: " + stale.notice(item))
                 for item in stale.stale_after_edit(core.root, rel)]
        out += drift or [Line("  no stale link on this file")]
        if not ids:
            out.insert(0, Line(f"iaso: no requirement is linked to {rel}"))
    return out


# -- (4) a failing test --------------------------------------------------------------------


def proves(core: Any, node: str) -> list[str]:
    """``SR-1/EX-2``: the examples the test node (or its file) is linked to prove."""
    file = node.split("::", 1)[0]
    out = []
    for record in core.index().values():
        for link in record.links:
            target = link.target
            if link.kind == "verified_by" and (
                    target.test == node or (target.test is None and target.path == file)):
                out.append(f"{record.id}/{link.example}" if link.example else record.id)
    return sorted(set(out))


def test(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(4): a regression on behaviour that passed before, or a test that never passed, and
    the example it proves."""
    node = str(ctx.get("node") or "")
    shown = proves(core, node)
    it = f"; it proves {', '.join(shown)}" if shown else ""
    if ctx.get("regression"):
        text = f"iaso: regression: {node} passed before and fails now{it}"
    else:
        text = f"iaso: not yet passing: {node} (it never passed){it}"
    return [Line(text, subject=f"test:{node}", state="regression" if ctx.get("regression")
                 else "not-yet")]


# -- (6) a commit or a merge ---------------------------------------------------------------

_INFO = ("full run:", "verification: no full", "confirmed but not covered",
         "acceptance tests this change can affect")


def merge(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(6): only what would hold the merge (EX-6); in full, the whole report."""
    from iaso.boundary.premerge import drift_lines, hold_lines
    from iaso.boundary.report import _verification_lines, collision_lines, render

    report = ctx["report"]
    if ctx.get("full") or report.error:
        return [Line(text) for text in render(report)]
    from iaso.merge import failing_line

    out: list[str] = []
    if report.integrity:
        out += ["log integrity: FAILED", *(f"  {p}" for p in report.integrity)]
    if report.links:
        from iaso.boundary.gates import link_line

        out += ["links of touched requirements hold the merge:",
                *(link_line(dict(row)) for row in report.links)]
    out += collision_lines(report.id_collisions)
    if report.unmerged:
        from iaso.mergedriver.unmerged import unmerged_lines

        out += unmerged_lines([dict(r) for r in report.unmerged])
    out += drift_lines(report)
    out += hold_lines(report, "the default branch")
    if report.into_default and report.exit == 5:
        out += [x for x in _verification_lines(report, failing_line) if not x.startswith(_INFO)]
    if report.intent_conflicts:
        from iaso.present.owner_text import CONFLICTS_HEADER

        out.append(CONFLICTS_HEADER)
        for conflict in report.intent_conflicts:
            out += [str(x) for x in conflict.get("card") or []]
    head = f"iaso merge-check: {report.base}..HEAD: " + (
        "nothing holds the merge" if not report.exit else
        f"held (exit {report.exit}); iaso context merge {report.base} prints the full report")
    return [Line(text) for text in (head, *out)]


# -- (8) a check cut by its budget ---------------------------------------------------------


def cut(core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """(8): the skipped step, once per session (EX-7)."""
    from iaso.hosts.claude_code.hookio import skip_line

    step = str(ctx.get("step") or "")
    return [Line(skip_line(step), subject=f"cut:{ctx.get('hook') or ''}:{step}")]


TABLE: dict[str, Callable[[Any, Mapping[str, Any]], list[Line]]] = {
    "session": session, "prompt": prompt, "edit": edit, "test": test, "symptom": symptom,
    "merge": merge, "cut": cut,
}


def lines(condition: str, core: Any, ctx: Mapping[str, Any]) -> list[Line]:
    """The insight lines of ``condition``, for a hook's emitter."""
    return TABLE[condition](core, ctx)
