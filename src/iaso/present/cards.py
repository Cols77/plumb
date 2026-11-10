"""What the records say about themselves, for the surfaces that show a record: how a confirmed
record is labelled (``confirmed_label``), an example's text, the state of a test end, the early
conflict's answer words, and the intent a session works on (sp5 4.1; SR-061).
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

BY = {"owner": "you", "agent-relayed": "you (relayed)", "auto-jev": "JEV", "import": "import",
      "owner-words": "you", "auto-model": "the judge model"}
INTENT_FILE = "intent.json"


def _flat(value: Any) -> str:
    if isinstance(value, list):
        value = " / ".join(map(str, value))
    return " ".join(str(value or "").split())


def _items(raw: Any) -> tuple[str, ...]:
    if raw is None:
        return ()
    if not isinstance(raw, list):
        raw = [raw]
    out = []
    for item in raw:
        text = (item.get("text") or item.get("statement")) if isinstance(item, Mapping) \
            else item
        if _flat(text):
            out.append(_flat(text))
    return tuple(out)


def example_text(example: Any) -> str:
    if example.given or example.when or example.then:
        return f"given {_flat(example.given)}, when {_flat(example.when)}, then " \
               f"{_flat(example.then)}"
    return _flat(example.criterion)


def evidence_state(items: Iterable[Any]) -> str:
    """``passing``, ``regression``, ``not yet passing`` or ``not run`` for one test end."""
    states = [(e.state, bool(getattr(e, "regression", False))) for e in items]
    if not states:
        return "not run"
    if any(regression for _, regression in states):
        return "regression"
    if any(state == "fresh-fail" for state, _ in states):
        return "not yet passing"
    if all(state in ("fresh-pass", "flaky-pass") for state, _ in states):
        return "passing"
    return "not run"


def test_states(core: Any, ends: Sequence[str], *, evidence: Mapping[str, Any] | None = None,
                verify: Any = None) -> dict[str, str]:
    """``{test end: state}``: from ``evidence`` (the stop hook's selection) when given, else
    from VERIFY when it is built; ``not run`` when nothing is known."""
    out = dict.fromkeys(ends, "not run")
    if not ends:
        return out
    if evidence is not None:
        for end in ends:
            out[end] = evidence_state(e for node, e in evidence.items()
                                      if node == end or node.startswith(end + "::"))
        return out
    if verify is None:
        try:
            from iaso.verify import open_verify

            verify = open_verify(core)
        except Exception:  # noqa: BLE001 - VERIFY is optional for a card
            return out
    try:
        nodes = verify.tests_for(list(ends))
        flat = sorted({n for found in nodes.values() for n in found})
        found_evidence = verify.evidence(flat) if flat else {}
    except Exception:  # noqa: BLE001
        return out
    for end in ends:
        out[end] = evidence_state(found_evidence[n] for n in nodes.get(end, ())
                                  if n in found_evidence)
    return out


def _label(core: Any, record_id: str) -> str:
    """"self-recorded message" and the like, from CAPTURE when built (R13 Q4)."""
    try:
        from iaso.capture.api import confirmation_label
    except ImportError:
        return ""
    try:
        label = str(confirmation_label(core, record_id) or "")
    except Exception:  # noqa: BLE001
        return ""
    # CAPTURE's label repeats "confirmed by ..."; the card keeps only the extra words
    return label.split(", ", 1)[1] if label.startswith("confirmed by") and ", " in label \
        else ("" if label.startswith("confirmed by") else label)


def judge_label(status: Any) -> str | None:
    """SR-251: a judge approval with its judge, model and score, "judge-approved (auto-jev,
    jev-1.13, 0.96)" or "judge-approved (auto-model, haiku, 0.8)"; None for any other."""
    by = str(getattr(status, "approved_by", "") or "")
    if by not in ("auto-jev", "auto-model"):
        return None
    auto = getattr(status, "auto", None) or {}
    jev = by == "auto-jev"
    model = auto.get("model_version" if jev else "model")
    score = auto.get("score" if jev else "confidence")
    parts = [by] + ([str(model)] if model else []) + (
        [f"{round(float(score), 2):g}"] if isinstance(score, (int, float)) else [])
    return f"judge-approved ({', '.join(parts)})"


def confirmed_label(core: Any, record_id: str, status: Any) -> str | None:
    """Who confirmed a confirmed record, in the owner's terms: "confirmed by you", "confirmed
    by you (relayed)", a judge approval's ``judge_label`` (SR-251), with CAPTURE's extra words
    such as "self-recorded message" (R8 B, R13 Q4); None for a record that is not confirmed.
    The one label every surface that states a record's confirmation uses: the cards, ``iaso
    show``, ``iaso explain`` and the vault."""
    if status is None or status.confirmation != "confirmed" or not status.approved_by:
        return None
    judged = judge_label(status)
    who = BY.get(str(status.approved_by), str(status.approved_by))
    extra = _label(core, record_id)
    carried_from = getattr(status, "carried_from", None)
    if carried_from:  # R17: an ok carried across a renumber, words unchanged
        from iaso.present.owner_text import carried

        extra = ", ".join(x for x in (extra, carried(carried_from, record_id)) if x)
    return (judged or f"confirmed by {who}") + (f", {extra}" if extra else "")


def judge_lines(core: Any, statuses: Mapping[str, Any], cap: int = 5) -> list[str]:
    """SR-251: each judge-approved record by title with its ``judge_label``, at most ``cap``
    of them and a count of the rest."""
    index = core.index()
    rows = [f"{index[i].title}: {label}" for i, s in sorted(statuses.items())
            if i in index and (label := judge_label(s))]
    more = [f"  +{len(rows) - cap} more judge-approved"] if len(rows) > cap else []
    return [f"  {r}" for r in rows[:cap]] + more


def awaiting_lines(core: Any, statuses: Mapping[str, Any]) -> list[str]:
    """What awaits the owner, counted and with no id (SR-267): the judge's open questions with
    the request they came from, then how many records wait on a judge; never an approve hint."""
    from iaso.present import owner_text

    asked: list[Mapping[str, Any]] = []
    sessions = Path(core.root) / ".iaso" / "session"
    # judge.QUESTIONS_FILE, named here so the session start never imports the judge
    for path in sorted(sessions.glob("*/judge_questions.json")):
        try:
            from iaso.understand import judge

            asked += judge.open_questions(core, path.parent.name)
        except Exception:  # noqa: BLE001 - a status line never fails the command
            continue
    lines = []
    if asked:
        said = str(asked[0].get("question") or "").rsplit("\n\n", 1)[-1]
        lines.append(owner_text.AWAITS_QUESTIONS.format(
            n=len(asked), s="s" if len(asked) > 1 else "", said=said))
    from iaso.query import retired_ids

    retired = retired_ids(core.index())      # SR-380: a frozen record is not waiting on a judge
    waiting = sum(s.confirmation != "confirmed" for i, s in statuses.items() if i not in retired)
    if waiting:
        lines.append(owner_text.AWAITS_JUDGE.format(n=waiting, s="s" if waiting > 1 else ""))
    return lines or [owner_text.AWAITS_NOTHING]


def early_say(core: Any, record: Any) -> str:
    """The answer words of an early-conflict decision's card (R17), from this session's
    branch; "" for any other record."""
    try:
        from iaso.awareness.answer import _current, early_of, say_line

        early = early_of(record)
        if early is None:
            return ""
        return say_line(early, _current(core)).replace("Say:", "say", 1)
    except Exception:  # noqa: BLE001 - the card falls back to its plain state
        return ""


# --------------------------------------------------------------------------- the session


def session_intent(core: Any, index: Mapping[str, Any], touched: Sequence[str],
                   session_path: Path) -> str:
    """The intent this session works on in plain words (sp5 4.1): the most recent INT touched
    this turn, else the INT a touched record derives from, else the last one named in this
    session. Remembered in ``<session>/intent.json``."""
    intents = [i for i in touched if i in index and index[i].kind == "intent"]
    if not intents:
        for record_id in touched:
            record = index.get(record_id)
            for link in getattr(record, "links", ()):
                target = link.target.record
                if link.kind == "derives_from" and target in index \
                        and index[target].kind == "intent":
                    intents.append(target)
    path = Path(session_path) / INTENT_FILE
    if intents:
        chosen = max(intents, key=lambda i: int(i.rsplit("-", 1)[-1]))
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"id": chosen}), encoding="utf-8")
        except OSError:
            pass
    else:
        try:
            chosen = str(json.loads(path.read_text(encoding="utf-8")).get("id") or "")
        except (OSError, ValueError, AttributeError):
            return ""
    record = index.get(chosen)
    if record is None:
        return ""
    title = _flat(record.title) or _flat(record.fields.get("readback")).split(",")[0]
    return title
