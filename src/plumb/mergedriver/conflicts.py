"""Intent conflicts (sp6 8, SR-076): the ``conflict`` block the driver writes into a record.

- ``open_conflicts``: every open block, from the record index (no git, no log read);
- ``conflict_card``: one card in the intent-card format of R9, both versions in the owner's
  terms, what merged on its own, an optional advisory compatibility judgment (once per pair
  of hashes, logged, 5 s limit; "no judgment available" with none configured);
- ``propose``: the agent's combined version, shown in the card, never applied by itself;
- ``choose_owner`` and ``relay_choice``: only the owner chooses. The owner's own terminal
  (``approvals.require_owner``), or the owner's words relayed (``approvals.owner_prompt``)
  with the card in the stated set of the reply before that prompt, read like an approval
  (``read_choice``: the model that reads the owner's answers, INT-028, INT-029) as exactly
  one version kept with no change asked; ``apply_choice`` writes the chosen side's
  values for the conflicting fields, keeps everything that merged on its own, removes the
  block and appends a ``conflict-resolution`` entry.
"""

from __future__ import annotations

import json
import re
import threading
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import replace
from typing import Any

from plumb.contracts import IntentConflict
from plumb.model import record_hash
from plumb.normalize import canonical_json, normalize_text, sha256_bytes
from plumb.present import owner_text

JUDGE_TIMEOUT_S = 5.0
JUDGMENT_ACTION = "conflict-compatibility"
TAKES = ("ours", "theirs", "combined")
_FIELD_NAMES = {
    "statement": "What it says", "title": "Its name", "body": "Its notes",
    "will": "What it will do", "wont": "What it won't do", "assumptions": "Assumed",
    "quote": "Your words", "readback": "The read-back", "question": "The question",
    "chosen": "The choice", "alternatives": "The other options", "rationale": "Why",
    "matters": "Whether it matters", "description": "What it covers", "domain": "Its area",
    "requirements": "Its requirements", "members": "Its members", "status": "Its state",
    "feature": "Its feature", "mode": "How it was captured", "done_when": "Done when",
}


class ChoiceRefused(PermissionError):
    """A choice nothing of the owner's grounds (exit 3); nothing is written."""


class ConflictError(ValueError):
    """A conflict reference or a combined version that cannot be used (exit 1 or 2)."""


# --------------------------------------------------------------------------- reading


def _as_conflict(record: Any) -> IntentConflict | None:
    block = record.fields.get("conflict")
    if not isinstance(block, Mapping) or not isinstance(block.get("id"), str):
        return None
    ours = block.get("ours") if isinstance(block.get("ours"), Mapping) else {}
    theirs = block.get("theirs") if isinstance(block.get("theirs"), Mapping) else {}
    fields = block.get("fields") if isinstance(block.get("fields"), Mapping) else {}
    proposed = block.get("proposed") if isinstance(block.get("proposed"), Mapping) else None
    return IntentConflict(
        ic=str(block["id"]), record=record.id, title=record.title,
        fields={str(k): (dict(v) if isinstance(v, Mapping) else {}) for k, v in fields.items()},
        labels=(str(ours.get("label") or "ours"), str(theirs.get("label") or "theirs")),
        hashes={"base": str(block.get("base") or ""), "ours": str(ours.get("hash") or ""),
                "theirs": str(theirs.get("hash") or "")},
        merged=tuple(str(m) for m in block.get("merged") or ()),
        proposed=dict(proposed) if proposed else None, path=record.path,
        suggested=dict(block["suggested"]) if isinstance(block.get("suggested"), Mapping) else None)


def open_conflicts(core: Any) -> tuple[IntentConflict, ...]:
    """Every open intent conflict, by IC number (the record index only)."""
    found = [c for record in core.index().values() if (c := _as_conflict(record))]
    return tuple(sorted(found, key=lambda c: (c.ic, c.record)))


def find(core: Any, ref: str) -> IntentConflict:
    """The open conflict an ``IC-###``, a record ID or the owner's plain words name."""
    conflicts = open_conflicts(core)
    if not conflicts:
        raise ConflictError(owner_text.NO_CONFLICTS)
    wanted = ref.strip()
    for conflict in conflicts:
        if wanted.upper() in (conflict.ic, conflict.record):
            return conflict
    if not wanted and len(conflicts) == 1:
        return conflicts[0]
    from plumb.present.resolve import chosen, resolve

    try:
        ids = chosen(resolve(core, wanted))
    except Exception:  # noqa: BLE001 - plain words that resolve to nothing
        ids = []
    matches = [c for c in conflicts if c.record in ids]
    if len(matches) == 1:
        return matches[0]
    words = set(re.findall(r"\w+", wanted.lower()))
    matches = [c for c in conflicts if words & set(re.findall(r"\w+", c.title.lower()))]
    if len(matches) == 1:
        return matches[0]
    names = "; ".join(f'"{c.title}" ({c.ic})' for c in conflicts)
    raise ConflictError(f"plumb: which conflict do you mean? open: {names}")


def combined_hash(conflict: IntentConflict) -> str | None:
    proposed = conflict.proposed or {}
    values = proposed.get("fields")
    return _values_hash(values) if isinstance(values, Mapping) else None


def _values_hash(values: Mapping[str, Any]) -> str:
    return sha256_bytes(canonical_json(dict(values)))


def stated_key(conflict: IntentConflict) -> dict[str, Any]:
    return {"ic": conflict.ic, "record": conflict.record, "ours_hash": conflict.hashes["ours"],
            "theirs_hash": conflict.hashes["theirs"],
            "combined_hash": combined_hash(conflict)}


def stated_entries(core: Any, shown: Iterable[str]) -> list[dict[str, Any]]:
    """``[{ic, record, ours_hash, theirs_hash, combined_hash}]`` for the shown ICs."""
    wanted = set(shown)
    return [stated_key(c) for c in open_conflicts(core) if c.ic in wanted]


def is_conflict_id(word: str) -> bool:
    return re.fullmatch(r"IC-\d{3,}", word.strip().upper()) is not None


def conflict_cards(core: Any, refs: Iterable[str], *,
                   by_record: bool = False) -> tuple[list[str], list[str]]:
    """``(lines, missing)``: the cards of the open conflicts ``refs`` name (IC IDs, or with
    ``by_record`` the records carrying one; a record without a conflict is skipped)."""
    wanted = [r.strip().upper() for r in refs]
    if not wanted:
        return [], []
    conflicts = open_conflicts(core)
    lines: list[str] = []
    missing: list[str] = []
    for ref in wanted:
        found = [c for c in conflicts if (c.record if by_record else c.ic) == ref]
        if not found and not by_record:
            missing.append(ref)
        for conflict in found:
            lines.extend(conflict_card(core, conflict))
    return lines, missing


# --------------------------------------------------------------------------- the card


def field_name(name: str) -> str:
    if name.startswith("examples/"):
        return "Example " + name.split("/", 1)[1].replace("EX-", "")
    return _FIELD_NAMES.get(name, name.replace("_", " ").capitalize())


def _one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def show_value(name: str, value: Any) -> str:
    """A field's value in the owner's terms: an example as its given/when/then."""
    if value is None:
        return "(removed)" if name.startswith("examples/") or name == "body" else "(none)"
    if isinstance(value, Mapping) and ("given" in value or "then" in value):
        parts = [f"{key} {_one_line(str(value[key]))}" for key in ("given", "when", "then")
                 if value.get(key)]
        return ", ".join(parts) or _one_line(str(value.get("criterion") or ""))
    if isinstance(value, list):
        return "; ".join(_one_line(str(v.get("text") if isinstance(v, Mapping) else v))
                         for v in value) or "(none)"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return _one_line(str(value)) or "(empty)"


def _side_rows(conflict: IntentConflict, name: str, values: Mapping[str, Any],
               indent: str) -> list[str]:
    ours, theirs = conflict.labels
    width = max(len(ours), len(theirs), 8)
    rows = [f"{indent}{ours:<{width}} {show_value(name, values.get('ours'))}",
            f"{indent}{theirs:<{width}} {show_value(name, values.get('theirs'))}"]
    proposed = (conflict.proposed or {}).get("fields")
    if isinstance(proposed, Mapping) and name in proposed:
        label = "combined"
        rows.append(f"{indent}{label:<{width}} {show_value(name, proposed[name])} (proposed)")
    return rows


def _merged_text(merged: Sequence[str]) -> str:
    return ", ".join(merged)


def conflict_card(core: Any, conflict: IntentConflict, *, backend: Any = None) -> list[str]:
    """The conflict card (sp6 8.3); the judgment line is advisory and resolves nothing."""
    lines = [owner_text.CARD_HEAD.format(ic=conflict.ic, record=conflict.record,
                                         title=conflict.title)]
    names = list(conflict.fields)
    if len(names) == 1:
        lines.extend(_side_rows(conflict, names[0], conflict.fields[names[0]], "  "))
    else:
        for name in names:
            lines.append(owner_text.CARD_FIELD.format(name=field_name(name)))
            lines.extend(_side_rows(conflict, name, conflict.fields[name], "    "))
    if conflict.merged:
        lines.append(owner_text.CARD_MERGED.format(what=_merged_text(conflict.merged)))
    ours, theirs = conflict.labels
    settled = _settled(core, conflict)
    if settled is not None:  # R17: answered before work began; nothing to ask again
        side = ours if settled.take == "ours" else theirs
        lines.append(owner_text.CARD_SETTLED.format(chosen=settled.chosen, side=side))
        return lines
    sug = conflict.suggested or {}
    side = {"ours": f"keep {ours}'s version", "theirs": f"keep {theirs}'s version",
            "combined": "keep the combined version"}.get(str(sug.get("take")))
    if side:  # SR-158: the agent's suggestion and its reason
        lines.append(owner_text.CONFLICT_SUGGESTED.format(said=side, why=sug.get("why", "")))
    lines.append(judgment_line(core, conflict, backend))
    say = owner_text.CARD_SAY_COMBINED if conflict.proposed else owner_text.CARD_SAY
    lines.append(say.format(ours=ours, theirs=theirs))
    return lines


def _settled(core: Any, conflict: IntentConflict) -> Any:
    try:
        from plumb.awareness.answer import settling

        return settling(core, conflict)
    except Exception:  # noqa: BLE001 - the card still asks
        return None


def _side_text(conflict: IntentConflict, side: str) -> str:
    return " | ".join(f"{field_name(n)}: {show_value(n, v.get(side))}"
                      for n, v in conflict.fields.items())


def _cached_judgment(core: Any, conflict: IntentConflict) -> Mapping[str, Any] | None:
    pair = [conflict.hashes["ours"], conflict.hashes["theirs"]]
    found = None
    for entry in core.log_read("events", ["judgment"]):
        payload = entry.payload
        if payload.get("action") == JUDGMENT_ACTION and payload.get("subject") == conflict.ic \
                and list(payload.get("pair") or []) == pair:
            found = payload
    return found


def _judge(core: Any, conflict: IntentConflict, backend: Any) -> Mapping[str, Any] | None:
    record = core.index().get(conflict.record)
    if record is None:
        return None
    theirs_fields = dict(record.fields)
    theirs_fields.pop("conflict", None)
    for name, values in conflict.fields.items():
        if "/" not in name and name != "body":
            theirs_fields[name] = values.get("theirs")
    theirs_record = replace(record, fields=theirs_fields)
    prompt = f"{conflict.labels[0]} says: {_side_text(conflict, 'ours')}"
    box: dict[str, Any] = {}

    def call() -> None:
        try:
            box["judgment"] = backend.contradiction(prompt, theirs_record)
        except Exception as exc:  # noqa: BLE001 - advisory: a failure means no judgment
            box["error"] = exc

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(JUDGE_TIMEOUT_S)
    judgment = box.get("judgment")
    if judgment is None:
        from plumb.judgment import JudgmentUnavailable

        if isinstance(box.get("error"), JudgmentUnavailable):
            raise box["error"]
        return None
    verdict = "likely incompatible" if judgment.verdict == "contradicts" else \
        "likely compatible"
    probability = judgment.probability if judgment.probability is not None else \
        judgment.confidence
    payload = {"action": JUDGMENT_ACTION, "subject": conflict.ic, "record": conflict.record,
               "pair": [conflict.hashes["ours"], conflict.hashes["theirs"]],
               "verdict": verdict, "raw": judgment.verdict,
               "probability": float(probability), "backend": judgment.backend,
               "reasons": list(judgment.reasons[:1]), "advisory": True}
    core.log_append("events", "judgment", payload)
    return payload


def judgment_line(core: Any, conflict: IntentConflict, backend: Any = None) -> str:
    """"Compatible? JEV: ..." when a real backend judged this pair (once per pair of
    hashes, logged); otherwise "Compatible? no judgment available"."""
    from plumb.judgment import JudgmentUnavailable

    try:
        cached = _cached_judgment(core, conflict)
        if cached is None:
            if backend is None:
                from plumb.judgment import get_backend

                backend = get_backend(core, hook=False)
            name = str(getattr(backend, "name", "") or "")
            if name in ("", "cached-only", "disabled"):
                return owner_text.CARD_NO_JUDGMENT
            cached = _judge(core, conflict, backend)
    except JudgmentUnavailable as exc:  # the cause is shown, never a rule-based answer
        return owner_text.CARD_UNAVAILABLE.format(cause=exc)
    except Exception:  # noqa: BLE001 - advisory only
        cached = None
    if not cached:
        return owner_text.CARD_NO_JUDGMENT
    reasons = [str(r) for r in cached.get("reasons") or [] if str(r).strip()]
    return owner_text.CARD_JUDGED.format(
        verdict=cached.get("verdict"), probability=float(cached.get("probability") or 0.0),
        reason=f": {_one_line(reasons[0])}" if reasons else "")


# --------------------------------------------------------------------------- writing


def _read_record(core: Any, conflict: IntentConflict) -> tuple[Any, dict[str, Any], str]:
    from plumb.model import load_yaml, split_frontmatter

    record = core.index().get(conflict.record)
    if record is None:
        raise ConflictError(f"plumb: the record of {conflict.ic} is gone")
    text = (core.root / record.path).read_bytes().decode("utf-8")
    head, body = split_frontmatter(text)
    data = load_yaml(head)
    if not isinstance(data, dict):
        raise ConflictError(f"plumb: the record file of {conflict.record} is not readable")
    return record, data, body


def _write(core: Any, record: Any, data: Mapping[str, Any], body: str) -> Any:
    fields = {k: v for k, v in data.items() if k != "id"}
    return core.write_record(record.kind, fields, body, record_id=record.id)


def _set_field(data: dict[str, Any], body: str, name: str, value: Any) -> str:
    """Put ``value`` in field ``name`` (``body`` and ``examples/EX-n`` included); returns
    the body."""
    if name == "body":
        return "" if value is None else str(value)
    if name.startswith("examples/"):
        ex_id = name.split("/", 1)[1]
        examples = [e for e in data.get("examples") or [] if isinstance(e, Mapping)]
        at = next((i for i, e in enumerate(examples) if str(e.get("id")) == ex_id), None)
        if value is None:
            if at is not None:
                examples.pop(at)
        elif at is None:
            examples.append(dict(value))
        else:
            examples[at] = dict(value)
        data["examples"] = examples
        return body
    if value is None:
        data.pop(name, None)
    else:
        data[name] = value
    return body


def _check_values(conflict: IntentConflict, values: Any) -> dict[str, Any]:
    if not isinstance(values, Mapping):
        raise ConflictError("plumb: a combined version is a mapping of the conflicting fields")
    unknown = [k for k in values if k not in conflict.fields]
    missing = [k for k in conflict.fields if k not in values]
    if unknown or missing:
        raise ConflictError("plumb: a combined version gives exactly the conflicting fields ("
                            + ", ".join(conflict.fields) + ")")
    return dict(values)


def propose(core: Any, ref: str, values: Any, *, take: str | None = None,
            why: str = "") -> IntentConflict:
    """Store the agent's combined version and/or its suggestion (SR-158: ``take`` is ours,
    theirs or combined, with ``why``) in the conflict block; it changes nothing else."""
    conflict = find(core, ref)
    record, data, body = _read_record(core, conflict)
    block = dict(data["conflict"])
    if values is not None:
        values = _check_values(conflict, values)
        block["proposed"] = {"fields": values, "hash": _values_hash(values)}
    if values is None and not take:
        raise ConflictError("plumb: propose needs a combined version (--file) or a suggestion "
                            "(--take with --why)")
    if take:
        take = normalize_take(conflict, take)
        if take == "combined" and not isinstance(block.get("proposed"), Mapping):
            raise ConflictError("plumb: propose a combined version (--file) before suggesting it")
        block["suggested"] = {"take": take, "why": " ".join(why.split())}
    data["conflict"] = block
    _write(core, record, data, body)
    return find(core, conflict.ic)


def _side_values(conflict: IntentConflict, take: str,
                 values: Mapping[str, Any] | None) -> dict[str, Any]:
    if take == "combined":
        if values is None:
            proposed = (conflict.proposed or {}).get("fields")
            if not isinstance(proposed, Mapping):
                raise ConflictError("plumb: no combined version is proposed for "
                                    f"{conflict.record} \"{conflict.title}\"")
            values = proposed
        return _check_values(conflict, values)
    return {name: v.get(take) for name, v in conflict.fields.items()}


def apply_choice(core: Any, conflict: IntentConflict, take: str, *, by: str,
                 quote: str | None = None, prompt: str | None = None,
                 self_recorded: bool = False,
                 values: Mapping[str, Any] | None = None,
                 decision: str | None = None) -> dict[str, Any]:
    """Write the choice and log it. The chosen side's values for the conflicting fields,
    the merged values for every other field, links kept, the block removed. ``decision``:
    the confirmed early decision whose answer this applies (``by: owner-decision``). The
    owner's own pick also answers an unanswered early decision on the same record
    (``answer.answer_from_conflict``): one question, one answer (R17)."""
    chosen = _side_values(conflict, take, values)
    record, data, body = _read_record(core, conflict)
    data.pop("conflict", None)
    for name, value in chosen.items():
        body = _set_field(data, body, name, value)
    written = _write(core, record, data, body)
    result_hash = record_hash({k: v for k, v in data.items()}, body)
    side_hash = conflict.hashes.get(take) if take in ("ours", "theirs") else None
    payload: dict[str, Any] = {
        "ic": conflict.ic, "record": conflict.record, "take": take, "by": by,
        "quote": quote, "prompt": prompt, "base": conflict.hashes.get("base"),
        "ours_hash": conflict.hashes.get("ours"), "theirs_hash": conflict.hashes.get("theirs"),
        "labels": list(conflict.labels), "fields": list(conflict.fields),
        "result_hash": written.hash if written is not None else result_hash,
        "same_as_side": bool(side_hash) and side_hash == (written.hash if written is not None
                                                          else result_hash)}
    if take == "combined":
        payload["combined_hash"] = _values_hash(chosen)
    if self_recorded:
        payload["self_recorded"] = True
    if decision:
        payload["decision"] = decision
    core.log_append("events", "conflict-resolution", payload)
    if by in ("owner", "agent-relayed"):
        from plumb.awareness.answer import answer_from_conflict

        answered = answer_from_conflict(core, conflict, take, by=by, quote=quote,
                                        prompt=prompt, self_recorded=self_recorded)
        if answered:
            payload["answered"] = answered
    stage_choice(core, record.path)
    return payload


def stage_choice(core: Any, record_path: str) -> None:
    """While a merge, rebase, cherry-pick or revert is in progress, stage the chosen record
    and the log that records the choice, so the commit that finishes it carries them (and an
    unmerged record is resolved). Outside one, nothing is staged. The quick check
    (``premerge``) still holds a commit whose ``.plumb/`` files differ from the index."""
    import subprocess

    from plumb.mergedriver.driver import git_operation

    root = core.root
    if git_operation(root) is None:
        return
    paths = [record_path] + [rel for rel in (".plumb/log",) if (root / rel).exists()]
    try:
        subprocess.run(["git", "add", "-A", "--", *paths], cwd=root, capture_output=True,
                       timeout=30)
    except (OSError, subprocess.SubprocessError):
        pass


def chosen_line(core: Any, conflict: IntentConflict, take: str,
                payload: Mapping[str, Any]) -> str:
    side = {"ours": f"{conflict.labels[0]}'s", "theirs": f"{conflict.labels[1]}'s",
            "combined": "the combined"}[take]
    line = owner_text.CHOSEN.format(record=conflict.record, title=conflict.title, side=side)
    status = core.status([conflict.record]).get(conflict.record)
    if status is not None and getattr(status, "confirmation", "") == "confirmed":
        return line + owner_text.CHOSEN_RECONFIRMED
    return line + owner_text.CHOSEN_PROPOSED


def normalize_take(conflict: IntentConflict, take: str) -> str:
    """``ours``, ``theirs`` or ``combined`` from a side's name, mine/ours or theirs."""
    wanted = take.strip().lower().removesuffix("'s")
    ours, theirs = (label.lower() for label in conflict.labels)
    if wanted in ("ours", "mine", ours):
        return "ours"
    if wanted in ("theirs", theirs):
        return "theirs"
    if wanted in ("combined", "combine", "both"):
        return "combined"
    raise ConflictError(f"plumb: --take is ours, theirs, combined, {conflict.labels[0]} or "
                        f"{conflict.labels[1]}")


# --------------------------------------------------------------------------- the relay


def _same(choice: str | None, said: Any) -> bool:
    return bool(choice) and (_one_line(str(choice)).casefold()
                             == _one_line(str(said or "")).casefold())


def read_choice(core: Any, conflict: IntentConflict, *, digest: str, message: str) -> str:
    """The version the owner kept, as the model that reads the owner's answers
    (``understand.read``) reads their logged ``message`` with this conflict's card shown
    (INT-028): ``ours`` or ``theirs`` for one side's version picked with no change asked,
    ``combined`` for a yes to the combined version the card offers. A change asked, a
    refusal, an open or unsure reading, or no model reached refuses (INT-029: nothing reads
    the words in its place)."""
    from plumb.contracts import DispatchError, NoModel
    from plumb.understand import agents, files, read
    from plumb.understand import schema as schema_check
    from plumb.understand.cards import BOTH, KEEP_OTHER, KEEP_THIS
    from plumb.understand.cards import conflict_card as reader_card
    from plumb.understand.dispatch import configured
    from plumb.understand.threshold import reader_threshold

    card = reader_card(core.index(), conflict)
    (question,) = card.questions
    item = read.card_item_id(card, question)
    inputs = {"message": {"digest": digest, "text": message}, "shown": [], "cards": [{
        "id": item, "card": card.id, "question": question.id, "kind": card.kind,
        "text": "\n".join(conflict_card(core, conflict, backend=CACHED_ONLY)),
        "resolutions": list(question.resolutions),
        "choices": [files.choice_to_json(c) for c in question.choices],
        "record": conflict.record, "hash": ""}]}
    try:
        dispatcher = configured(core)
        reason = dispatcher.available()
        if reason:
            raise DispatchError("dispatch", reason)
        answer = dispatcher.run(
            files.make_job(read.kind, "", read.SCHEMA_ID, inputs), system=agents.load(read.kind),
            user=json.dumps(inputs, ensure_ascii=False, sort_keys=True, indent=1),
            schema=read.schema, on_step=lambda _: None)
    except (NoModel, DispatchError) as exc:
        raise ChoiceRefused(f"the owner's words could not be read ({exc}); nothing was "
                            "chosen") from exc
    if schema_check.problems(answer, read.schema):
        raise ChoiceRefused("the reading of the owner's words is outside its schema; nothing "
                            "was chosen")
    entries = [e for e in answer.get("entries") or () if isinstance(e, Mapping)
               and str(e.get("id") or "") in (item, conflict.record)]
    if len(entries) != 1:
        raise ChoiceRefused("the owner's words were not read as an answer to the card")
    said = entries[0]
    if (not read.evidence_in(str(said.get("evidence") or ""), message)
            or float(said.get("confidence") or 0.0) < reader_threshold(core)):
        raise ChoiceRefused("the reading of the owner's words is not sure they chose; the "
                            "conflict stays open")
    picked = [c for c in question.choices if c.answer == said.get("answer")
              and (c.answer == "accepted" or _same(c.change, said.get("change"))
                   or _same(c.label, said.get("change")))]
    if len(picked) != 1:
        change = f": {said['change']}" if said.get("change") else ""
        raise ChoiceRefused(f"the owner's words were read as {said.get('answer')}{change}, not "
                            "as one version kept; the conflict stays open")
    return {KEEP_THIS: "ours", KEEP_OTHER: "theirs", BOTH: "combined"}[picked[0].label]


def _stated_conflicts(core: Any, prompt_at: str) -> list[Mapping[str, Any]]:
    try:
        data = json.loads(core.paths.stated.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if not isinstance(data, Mapping):
        return []
    stated_at = str(data.get("at") or "")
    if stated_at and prompt_at and stated_at > prompt_at:
        return []
    return [c for c in data.get("conflicts") or [] if isinstance(c, Mapping)]


def relay_choice(core: Any, ref: str, take: str | None, *, prompt: str, quote: str,
                 values: Mapping[str, Any] | None = None) -> tuple[IntentConflict, dict]:
    """Apply the owner's choice relayed from the owner's own logged words (sp6 8.4): the
    version ``read_choice`` reads in them; ``take``, when given, must be that one."""
    from plumb.approvals import Refused, owner_prompt, quote_in_prompt

    conflict = find(core, ref)
    wanted = normalize_take(conflict, take) if take else None
    try:
        entry = owner_prompt(core, prompt)
    except Refused as exc:
        raise ChoiceRefused(str(exc)) from exc
    text = normalize_text(str(entry.get("text") or ""))
    said = normalize_text(quote)
    if not said or not quote_in_prompt(said, text):
        raise ChoiceRefused("the quote is not a verbatim part of that prompt (whole words)")
    key = stated_key(conflict)
    shown = [c for c in _stated_conflicts(core, str(entry.get("at") or ""))
             if c.get("ic") == conflict.ic]
    if not any(c.get("ours_hash") == key["ours_hash"]
               and c.get("theirs_hash") == key["theirs_hash"] for c in shown):
        raise ChoiceRefused(f"the card of {conflict.record} \"{conflict.title}\" was not shown "
                            "in the reply before that prompt; show it (/plumb conflicts) and "
                            "let the owner answer it")
    take = read_choice(core, conflict, digest=str(entry["digest"]),
                       message=str(entry.get("text") or ""))
    if wanted and wanted != take:
        raise ChoiceRefused(f"the owner's words were read as keeping {_kept(conflict, take)}, "
                            f"not {_kept(conflict, wanted)}")
    if take == "combined":
        if values is not None and _values_hash(values) != combined_hash(conflict):
            raise ChoiceRefused("the combined version given is not the one the card showed")
        if not any(c.get("combined_hash") == key["combined_hash"] and key["combined_hash"]
                   for c in shown):
            raise ChoiceRefused("the combined version was not shown in the card the owner "
                                "answered")
    digest = str(entry["digest"])
    known = {e.payload.get("digest") for e in core.log_read("events", ["prompt"])}
    if digest not in known:
        core.log_append("events", "prompt", {"digest": digest, "session": entry.get("session"),
                                             "at": entry.get("at")})
    payload = apply_choice(core, conflict, take, by="agent-relayed", quote=said, prompt=digest,
                           self_recorded=entry.get("via") != "hook", values=values)
    return conflict, payload


# --------------------------------------------------------------------------- the owner's choice


def _kept(conflict: IntentConflict, take: str) -> str:
    return {"ours": f"{conflict.labels[0]}'s version",
            "theirs": f"{conflict.labels[1]}'s version",
            "combined": "the combined version"}[take]


def choose_owner(core: Any, ref: str, take: str,
                 values: Mapping[str, Any] | None = None) -> tuple[IntentConflict, dict]:
    """The owner's own terminal (``approvals.require_owner``): refused under the session
    marker and without an interactive terminal (exit 3, nothing written)."""
    from plumb.approvals import require_owner

    conflict = find(core, ref)
    take = normalize_take(conflict, take)
    side = {"ours": f"{conflict.labels[0]}'s version", "theirs":
            f"{conflict.labels[1]}'s version", "combined": "the combined version"}[take]
    require_owner("conflict choose",
                  f"Keep {side} of {conflict.record} \"{conflict.title}\"?")
    return conflict, apply_choice(core, conflict, take, by="owner", values=values)


# --------------------------------------------------------------------------- the stop hook


class _CachedOnly:
    """A backend that never calls out: inside a hook the card shows a judgment only when
    one is already logged for this pair (the 5 s call belongs to /plumb conflicts)."""

    name = "cached-only"
    version = "none"


CACHED_ONLY = _CachedOnly()
SHOWN_FILE = "conflicts-shown.json"


def conflict_rows(core: Any, *, hook: bool) -> list[dict[str, Any]]:
    """``[{ic, record, title, card}]`` of every open conflict, for the merge boundary. The one
    place the merge-time checks build cards: inside a git hook (``hook``: pre-merge-commit,
    pre-push) the card never calls a judgment backend and never writes the log; it shows a
    judgment only when one is already logged. ``/plumb merge-check`` and ``/plumb conflicts``
    judge live."""
    backend = CACHED_ONLY if hook else None
    return [{"ic": c.ic, "record": c.record, "title": c.title,
             "card": conflict_card(core, c, backend=backend)} for c in open_conflicts(core)]
REQUESTED_FILE = "conflicts-requested.json"


def _key(conflict: IntentConflict) -> str:
    entry = stated_key(conflict)
    return "|".join(str(entry[k]) for k in ("ic", "ours_hash", "theirs_hash", "combined_hash"))
