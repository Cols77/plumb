"""``plumb capture``: a whole read-back in one call (sp2 5.1, SR-034).

The document carries the owner's verbatim words, the restatement, what will and won't be
done, labelled assumptions, requirements with given/when/then examples, decisions with
alternatives, and updates of existing records. Everything is checked before anything is
written (a failure writes nothing); every record written is ``proposed``; IDs come only from
``Store.next_id`` and links only from ``CoreAPI.add_link`` (pinned at once). The auto-approval
gate (sp2 8.2) is asked last and returns at once when auto-approval is off (the default).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Any

from plumb.capture.records import (
    CaptureError,
    example_entry,
    intent_fields,
    new_record,
    record_fields,
    rewrite,
    short_title,
)
from plumb.contracts import CaptureResult, IntentCardData, Target

if TYPE_CHECKING:
    from plumb.api import Core

UPDATABLE = {"intent": ("readback", "will", "wont", "assumptions", "title"),
             "requirement": ("statement", "title", "examples", "add_examples"),
             "decision": ("chosen", "alternatives", "rationale", "title")}


def check_quote(core: Core, prompt: str, quote: str) -> Mapping[str, Any]:
    """The logged prompt ``prompt`` names, when ``quote`` is a verbatim part of it (after
    body normalization, whole words); else ``CaptureError`` (exit 2)."""
    from plumb.approvals import Refused, find_prompt, quote_in_prompt
    from plumb.normalize import normalize_text

    try:
        entry = find_prompt(core, prompt)
    except Refused as exc:
        raise CaptureError(str(exc)) from exc
    if not quote_in_prompt(normalize_text(quote), normalize_text(str(entry["text"]))):
        raise CaptureError("the quote is not a verbatim part of that prompt; the owner's "
                           "words are never paraphrased into a quote")
    return entry


def _as_list(value: Any, name: str) -> list[Any]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise CaptureError(f"{name} must be a list")
    return value


def _examples(raw: Any, name: str, start: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for n, item in enumerate(_as_list(raw, name), start=start):
        if not isinstance(item, Mapping):
            raise CaptureError(f"{name}[{n - start}] must be a mapping")
        out.append(example_entry(str(item.get("id") or f"EX-{n}"), str(item.get("given") or ""),
                                 str(item.get("when") or ""), str(item.get("then") or ""),
                                 item.get("quote")))
    return out


def _inflight_check(core: Core, written: Sequence[str], updated: Sequence[str],
                    intent_id: str | None, backend: Any) -> dict[str, list[str]]:
    """``plumb.awareness.early.after_capture``; the DECs it raised join ``written``. An
    error never fails the capture: it is named in one line."""
    before = set(core.index())
    try:
        from plumb.awareness.early import after_capture

        lines = after_capture(core, written=written, updated=updated, intent=intent_id,
                              backend=backend)
    except Exception as exc:  # noqa: BLE001 - intent in flight is advisory
        return {"written": [], "lines": [f"plumb: intent in flight not checked ({exc})"]}
    raised = sorted(set(core.index()) - before)
    return {"written": raised, "lines": lines}


def _inflight_preview(core: Core, plan: _Plan, backend: Any) -> list[str]:
    try:
        from plumb.awareness.early import preview

        return preview(core, plan.requirements, plan.updates, backend=backend)
    except Exception as exc:  # noqa: BLE001 - advisory
        return [f"plumb: intent in flight not checked ({exc})"]


class _Plan:
    """The checked document: what will be written, before anything is."""

    def __init__(self, core: Core, doc: Mapping[str, Any]) -> None:
        if not isinstance(doc, Mapping):
            raise CaptureError("the capture document must be a mapping")
        unknown = set(doc) - {"intent", "requirements", "decisions", "updates"}
        if unknown:
            raise CaptureError("unknown keys in the capture document: "
                               + ", ".join(sorted(unknown)))
        index = core.index()
        self.intent_ref: str | None = None
        self.intent: dict[str, Any] | None = None
        raw_intent = doc.get("intent")
        if isinstance(raw_intent, str):
            if index.get(raw_intent) is None or index[raw_intent].kind != "intent":
                raise CaptureError(f"no intent {raw_intent}")
            self.intent_ref = raw_intent
        elif isinstance(raw_intent, Mapping):
            self.intent = intent_fields(
                str(raw_intent.get("quote") or ""), str(raw_intent.get("readback") or ""),
                will=raw_intent.get("will"), wont=raw_intent.get("wont"),
                assumptions=raw_intent.get("assumptions"),
                mode=str(raw_intent.get("mode") or "incremental"),
                title=str(raw_intent.get("title") or ""))
        elif raw_intent is not None:
            raise CaptureError("intent must be a mapping or an INT ID")
        self.requirements: list[dict[str, Any]] = []
        for n, item in enumerate(_as_list(doc.get("requirements"), "requirements")):
            if not isinstance(item, Mapping):
                raise CaptureError(f"requirements[{n}] must be a mapping")
            title = short_title(str(item.get("title") or item.get("statement") or ""))
            if not title:
                raise CaptureError(f"requirements[{n}] needs a title or a statement")
            feature = item.get("feature")
            if feature is not None and str(feature) not in index:
                raise CaptureError(f"requirements[{n}]: feature {feature} does not exist")
            paths = [str(p) for p in _as_list(item.get("implemented_by"), "implemented_by")]
            for path in paths:
                if core.hash_target(Target(path=path)) is None:
                    raise CaptureError(f"requirements[{n}]: implemented_by {path} does not "
                                       "exist (link it once the file exists)")
            fields: dict[str, Any] = {"title": title,
                                      "statement": " ".join(str(item.get("statement")
                                                                or title).split())}
            if feature is not None:
                fields["feature"] = str(feature)
            fields["examples"] = _examples(item.get("examples"), f"requirements[{n}].examples")
            self.requirements.append({"fields": fields, "paths": paths})
        if (self.requirements or doc.get("decisions")) and not (self.intent or self.intent_ref):
            raise CaptureError("requirements and decisions derive from an intent: give "
                               "intent (the owner's words) or an existing INT ID")
        self.decisions: list[dict[str, Any]] = []
        for n, item in enumerate(_as_list(doc.get("decisions"), "decisions")):
            if not isinstance(item, Mapping):
                raise CaptureError(f"decisions[{n}] must be a mapping")
            question = " ".join(str(item.get("question") or "").split())
            chosen = " ".join(str(item.get("chosen") or "").split())
            if not question or not chosen:
                raise CaptureError(f"decisions[{n}] needs a question and the chosen option")
            alternatives = [" ".join(str(a).split()) for a in
                            _as_list(item.get("alternatives"), "alternatives")]
            recommended = item.get("recommended")
            if recommended is not None and recommended not in [chosen, *alternatives]:
                raise CaptureError(f"decisions[{n}]: recommended must be an option")
            decides = []
            for ref in _as_list(item.get("decides"), "decides"):
                ref = str(ref)
                if ref.startswith("#") and ref[1:].isdigit():
                    if not 1 <= int(ref[1:]) <= len(self.requirements):
                        raise CaptureError(f"decisions[{n}]: no requirement {ref}")
                elif ref not in index:
                    raise CaptureError(f"decisions[{n}]: no record {ref}")
                decides.append(ref)
            fields = {"title": short_title(str(item.get("title") or question)),
                      "question": question, "chosen": chosen, "alternatives": alternatives,
                      "matters": bool(item.get("matters"))}
            if item.get("rationale"):
                fields["rationale"] = " ".join(str(item["rationale"]).split())
            if recommended is not None:
                fields["recommended"] = recommended
            self.decisions.append({"fields": fields, "decides": decides})
        self.updates: list[tuple[str, dict[str, Any]]] = []
        for n, item in enumerate(_as_list(doc.get("updates"), "updates")):
            if not isinstance(item, Mapping) or not isinstance(item.get("id"), str):
                raise CaptureError(f"updates[{n}] needs an id")
            record = index.get(item["id"])
            if record is None:
                raise CaptureError(f"updates[{n}]: no record {item['id']}")
            allowed = UPDATABLE.get(record.kind, ())
            changes = {k: v for k, v in item.items() if k != "id"}
            bad = set(changes) - set(allowed)
            if bad or not changes:
                raise CaptureError(f"updates[{n}]: {record.id} ({record.kind}) takes "
                                   + ", ".join(allowed))
            self.updates.append((record.id, self._changes(record, changes)))

    @staticmethod
    def _changes(record: Any, changes: Mapping[str, Any]) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for key, value in changes.items():
            if key == "examples":
                out["examples"] = _examples(value, f"{record.id}.examples")
            elif key == "add_examples":
                raw = [dict(e) for e in record.fields.get("examples") or []
                       if isinstance(e, Mapping)]
                from plumb.capture.records import next_example_id

                start = int(next_example_id(raw)[3:])
                out["examples"] = raw + _examples(value, f"{record.id}.add_examples", start)
            elif key in ("will", "wont", "assumptions", "alternatives"):
                out[key] = [" ".join(str(v).split()) for v in _as_list(value, key)]
            elif key == "title":
                out[key] = short_title(str(value))
            else:
                out[key] = " ".join(str(value).split())
        return out


def _preview(core: Core, plan: _Plan) -> list[IntentCardData]:
    """Card data for a dry run, from the plan alone (nothing written)."""
    from plumb.capture.card import _clip, _list, example_text
    from plumb.contracts import Example

    examples: list[tuple[str, str, str]] = []
    for n, item in enumerate(plan.requirements, start=1):
        for raw in item["fields"]["examples"]:
            example = Example(id=raw["id"], given=raw["given"], when=raw["when"],
                              then=raw["then"])
            examples.append((f"SR-new{n}", raw["id"], _clip(example_text(example))))
    if plan.intent is not None:
        fields = plan.intent
        return [IntentCardData(id="INT-new", title=fields["title"], quote=fields["quote"],
                               will=_list(fields["will"]), wont=_list(fields["wont"]),
                               assumed=_list(fields["assumptions"]),
                               examples=tuple(examples))]
    if plan.intent_ref is not None:
        from plumb.capture.card import card_data

        return list(card_data(core, [plan.intent_ref]))
    return []


UNCHECKED_NOTE = ("quote not checked (no --prompt): it is kept as the agent's quote, not as "
                  "the owner's words, and triage never rates it faithful; give --prompt "
                  "<digest> of the owner's logged prompt")


def _check_quotes(core: Core, plan: _Plan, prompt: str | None) -> bool:
    """Check every quote the document stores as the owner's words against the logged
    prompt (before anything is written), and pin each example quote to that prompt
    (``prompt`` on the example; R8 A: triage counts only verified words). Returns whether
    a quote was left unchecked: no ``--prompt`` was given."""
    examples = [e for item in plan.requirements for e in item["fields"]["examples"]
                if e.get("quote")]
    added = [e for _, changes in plan.updates for e in changes.get("examples") or []
             if e.get("quote") and not e.get("prompt")]
    if not prompt:
        return plan.intent is not None or bool(examples) or bool(added)
    from plumb.approvals import quote_in_prompt
    from plumb.normalize import normalize_text

    entry = (check_quote(core, prompt, plan.intent["quote"]) if plan.intent is not None
             else _entry(core, prompt))
    text = normalize_text(str(entry["text"]))
    prefix = str(entry["digest"]).removeprefix("sha256:")[:16]
    for example in examples:
        if not quote_in_prompt(normalize_text(str(example["quote"])), text):
            raise CaptureError(f"the quote of example {example['id']} is not a verbatim part "
                               "of that prompt; the owner's words are never paraphrased "
                               "into a quote")
        example["prompt"] = prefix
    for example in added:  # an update keeps earlier examples' quotes as they were
        if quote_in_prompt(normalize_text(str(example["quote"])), text):
            example["prompt"] = prefix
    return False


def _entry(core: Core, prompt: str) -> Mapping[str, Any]:
    from plumb.approvals import Refused, find_prompt

    try:
        return find_prompt(core, prompt)
    except Refused as exc:
        raise CaptureError(str(exc)) from exc


def capture(core: Core, doc: Mapping[str, Any], *, prompt_digest: str | None = None,
            dry_run: bool = False, backend: Any = None) -> CaptureResult:
    """Write the read-back ``doc`` as proposed records; see the module docstring."""
    from plumb.capture.card import card_data, render

    plan = _Plan(core, doc)
    unchecked = _check_quotes(core, plan, prompt_digest)
    if prompt_digest:
        from plumb.approvals import find_prompt

        prompt_digest = str(find_prompt(core, prompt_digest)["digest"])
    if dry_run:
        card = render(_preview(core, plan))
        lines = ["dry run: nothing written"]
        if plan.intent is not None:
            lines.append("INT (new) would be proposed")
        lines += [f"SR (new) would be proposed: {r['fields']['title']}"
                  for r in plan.requirements]
        lines += [f"DEC (new) would be proposed: {d['fields']['title']}" for d in plan.decisions]
        lines += [f"{rid} would be updated" for rid, _ in plan.updates]
        lines += _inflight_preview(core, plan, backend)
        return CaptureResult(card=card, lines=tuple(lines), dry_run=True)

    # one reservation per prefix for the whole read-back (sp6 4.2)
    core.store.prereserve("intent", 1 if plan.intent is not None else 0)
    core.store.prereserve("requirement", len(plan.requirements))
    core.store.prereserve("decision", len(plan.decisions))
    statuses_before = core.status([rid for rid, _ in plan.updates]) if plan.updates else {}
    written: list[str] = []
    links: list[str] = []
    intent_id = plan.intent_ref
    if plan.intent is not None:
        fields = dict(plan.intent)
        if prompt_digest:
            fields["prompt"] = prompt_digest.removeprefix("sha256:")[:16]
        intent_id = new_record(core, "intent", fields).id
        written.append(intent_id)
    sr_ids: list[str] = []
    for item in plan.requirements:
        record = new_record(core, "requirement", item["fields"])
        sr_ids.append(record.id)
        written.append(record.id)
        links.append(core.add_link(record.id, "derives_from", Target(record=intent_id)).id)
        for path in item["paths"]:
            links.append(core.add_link(record.id, "implemented_by", Target(path=path)).id)
    for item in plan.decisions:
        record = new_record(core, "decision", item["fields"])
        written.append(record.id)
        links.append(core.add_link(record.id, "derives_from", Target(record=intent_id)).id)
        decides = [sr_ids[int(r[1:]) - 1] if r.startswith("#") else r for r in item["decides"]]
        for target in decides or [intent_id]:
            links.append(core.add_link(record.id, "decides", Target(record=target)).id)
    if plan.intent is not None and plan.intent["mode"] == "escalated":
        anchor = core.index()[intent_id]
        members = [i for i in written if i != intent_id]
        rewrite(core, anchor, {"members": members})
        for member in members:  # the links just written pin the anchor before members
            repin_own_target(core, member, intent_id)
    updated: list[str] = []
    again: list[str] = []
    for record_id, changes in plan.updates:
        record = core.index()[record_id]
        merged = {**record_fields(record), **changes}
        if merged == record_fields(record):
            continue
        rewrite(core, record, changes)
        updated.append(record_id)
        before = statuses_before.get(record_id)
        if before is not None and before.confirmation == "confirmed":
            again.append(record_id)
    auto: list[str] = []
    if prompt_digest and written:
        from plumb.capture.autoapprove import gate

        auto = list(gate(core, written, prompt_digest=prompt_digest, backend=backend))
    shown = [intent_id] if intent_id else []
    shown += [i for i in written + updated if i not in shown and not i.startswith("SR-")
              and not i.startswith("DEC-")]
    if not shown:
        shown = written + updated
    card = render(card_data(core, shown))
    statuses = core.status(written + updated)
    lines = [f"{rid} {statuses[rid].confirmation}" + (" (confirmed by JEV)" if rid in auto
                                                      else "") for rid in written + updated]
    lines += [f"{rid} was confirmed; this edit needs the owner again" for rid in again]
    if unchecked:
        lines.append(UNCHECKED_NOTE)
    # R17: other branches' intent in flight, checked at capture before any implementation;
    # a contradiction is shown as an early card and asked once (a DEC)
    early = _inflight_check(core, written, updated, intent_id, backend)
    written += [i for i in early["written"] if i not in written]
    lines += early["lines"]
    if plan.intent_ref is not None and written:
        from plumb.capture.spec import set_of

        owners = set_of(core)
        joined = [i for i in written if owners.get(i) == plan.intent_ref]
        if joined:
            lines.append(f"{plan.intent_ref} is an escalated spec: {', '.join(joined)} joined "
                         "its set, which waits for the owner's set approval (plumb spec show "
                         f"{plan.intent_ref})")
    return CaptureResult(written=tuple(written), updated=tuple(updated),
                         needs_owner_again=tuple(again), links=tuple(links),
                         auto_approved=tuple(auto), card=card, lines=tuple(lines))


def repin_own_target(core: Core, source: str, target: str) -> None:
    """Repin ``source``'s links to ``target`` whose only moved end is the target (both were
    written by this capture)."""
    from plumb.links import repin

    for state in core.link_states([source]):
        if state.link.target.record == target and state.state == "stale" \
                and state.moved == "target":
            repin(core, state.link.id, note="plumb capture: the escalated set's anchor")


def load_document(text: str) -> Mapping[str, Any]:
    """A capture document from JSON or YAML text."""
    import json

    try:
        data = json.loads(text)
    except ValueError:
        import yaml

        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as exc:
            raise CaptureError(f"the document is neither JSON nor YAML: {exc}") from exc
    if not isinstance(data, Mapping):
        raise CaptureError("the capture document must be a mapping")
    return data


def result_lines(result: CaptureResult) -> list[str]:
    return ([result.card] if result.card else []) + list(result.lines)


def capture_ids(result: CaptureResult) -> Sequence[str]:
    return list(result.written) + list(result.updated)
