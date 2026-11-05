"""The merge conflicts a chat reply can answer (SR-170, DEC-057), as read inputs.

The stop hook draws an open conflict each turn and never stores it; the read job rebuilds the
open conflicts the previous reply showed (``conflicts.shown_open``) as items with the choices of
keeping one side, the other or both, and ``apply`` applies a clear pick through the conflict
code, citing the owner's words. Nothing is stored and nothing else reads the words."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from plumb.contracts import Choice
from plumb.present import owner_text
from plumb.understand import files

KEEP_THIS, KEEP_OTHER, BOTH = "Keep this one", "Keep the other", "Both"
ITEM = "conflict:"


def sides(ours: str, theirs: str, *, both: str, combined: bool = False,
          first: str | None = None) -> list[Choice]:
    """SR-130 EX-3: keep this one, keep the other, or both, each saying what it means;
    ``first`` (ours, theirs, combined): the agent's suggestion goes first (SR-158)."""
    if first in ("ours", "theirs"):
        order = sides(ours, theirs, both=both, combined=combined)
        pick = order.pop(next(n for n, c in enumerate(order) if c.label == (
            KEEP_THIS if first == "ours" else KEEP_OTHER)))
        return [pick, *order]
    keep = [Choice(KEEP_THIS, "change", f"Keep {ours}'s version", (
                f"Keeps {ours}'s version as the one that holds; the other is dropped")),
            Choice(KEEP_OTHER, "change", f"Keep {theirs}'s version", (
                f"Keeps {theirs}'s version as the one that holds; the other is dropped"))]
    if combined:
        return [Choice(BOTH, "accepted", consequence=both), *keep]
    return [*keep, Choice(BOTH, "change", consequence=both)]


def item(conflict: Any) -> dict[str, Any]:
    """The read input of one open conflict: its issue and the choices."""
    ours, theirs = conflict.labels
    both = ("Keeps the combined version already proposed; what each side had that it leaves "
            "out is dropped" if conflict.proposed else
            "Writes one version from both as you say; neither holds as it reads until you "
            "see it")
    take = (getattr(conflict, "suggested", None) or {}).get("take")
    choices = sides(ours, theirs, both=both, combined=bool(conflict.proposed), first=take)
    return {"id": ITEM + conflict.ic, "question": "", "kind": "conflict",
            "text": owner_text.CONFLICT_ISSUE.format(ours=ours, theirs=theirs),
            "resolutions": [c.label for c in choices],
            "choices": [files.choice_to_json(c) for c in choices], "record": "", "hash": ""}


def items(core: Any, prompt_at: str = "") -> list[dict[str, Any]]:
    from plumb.mergedriver import conflicts

    return [item(c) for c in conflicts.shown_open(core, prompt_at)]


def take_of(choice: Mapping[str, Any]) -> str | None:
    """The side a choice keeps (``ours``, ``theirs``, or ``combined`` when one is proposed)."""
    label = choice.get("label")
    return {KEEP_THIS: "ours", KEEP_OTHER: "theirs"}.get(
        str(label), "combined" if label == BOTH and choice.get("answer") == "accepted" else None)


def apply_choice(core: Any, found_item: Mapping[str, Any], choice: Choice, evidence: str,
                 digest: str) -> None:
    """SR-170: a conflict answered in words. When they clearly keep one version (``choice``:
    the item's choice the reader named, else the answer as said), the conflict code applies it,
    citing their words; a change asked, a refusal or an unsure reading leaves the conflict open
    (INT-029: nothing else reads the words)."""
    from plumb.mergedriver import conflicts

    def same(text: Any) -> bool:
        return " ".join(str(text or "").split()).casefold() == " ".join(
            str(choice.change or "").split()).casefold()

    choices: Sequence[Mapping[str, Any]] = found_item.get("choices") or ()
    picked = [c for c in choices if c.get("answer") == choice.answer
              and (choice.answer == "accepted" or same(c.get("change")) or same(c.get("label")))]
    take = take_of(picked[0]) if len(picked) == 1 else None
    if take is None:
        return
    try:
        found = conflicts.find(core, str(found_item["id"]).removeprefix(ITEM))
        conflicts.apply_choice(core, found, take, by="owner-words", quote=evidence, prompt=digest)
    except conflicts.ConflictError:
        return
