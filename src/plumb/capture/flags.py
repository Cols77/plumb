"""Intent-change flags scored against confirmed examples (sp2 7.1, SR-038).

Only confirmed records feed trigger 1 (a proposed record never does, concept 4.2). The
backend's ``intent_change`` gives the candidates and its ``contradiction`` labels each:
``contradicts`` (the request negates, replaces or reverses a confirmed ``then`` or the
statement) or ``extends`` (new behaviour beside a confirmed one). Everything else, a mention
with tidy-up words included, is benign and raises no flag. The agent stays the cascade's
LLM tier: a flag asks it to read the change back and ask before editing.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

from plumb.contracts import IntentFlag

if TYPE_CHECKING:
    from plumb.api import Core

INSTRUCTION = ("plumb: this may {verb} {id} (confirmed){about}. If it does, read back the "
               "change and ask before editing; if not, proceed.")


def intent_flags(core: Core, prompt: str, matched: Sequence[str],
                 backend: Any = None) -> list[IntentFlag]:
    index = core.index()
    ids = [i for i in matched if i in index] or [i for i, _ in core.relevant(prompt, 5)]
    if not ids:
        return []
    statuses = core.status(ids)
    confirmed = [index[i] for i in ids if statuses[i].confirmation == "confirmed"
                 and index[i].kind in ("requirement", "intent", "decision")]
    if not confirmed:
        return []
    if backend is None:
        from plumb.judgment import get_backend

        backend = get_backend(core, hook=True)
    flags: list[IntentFlag] = []
    candidates = {j.subject for j in backend.intent_change(prompt, confirmed)
                  if j.verdict == "change"}
    for record in confirmed:
        if record.id not in candidates:
            continue
        judgment = backend.contradiction(prompt, record)
        if judgment.verdict not in ("contradicts", "extends"):
            continue
        example = next((r.split(" ", 1)[1] for r in judgment.reasons
                        if r.startswith("example ")), None)
        reason = next((r for r in judgment.reasons if not r.startswith("example ")), "")
        flags.append(IntentFlag(record=record.id, kind=judgment.verdict,  # type: ignore[arg-type]
                                confidence=judgment.confidence, example=example,
                                reason=reason, backend=judgment.backend))
    return flags


def flag_line(flag: IntentFlag) -> str:
    verb = "contradict" if flag.kind == "contradicts" else "extend"
    about = f", {flag.example}" if flag.example else ""
    return INSTRUCTION.format(verb=verb, id=flag.record, about=about)
