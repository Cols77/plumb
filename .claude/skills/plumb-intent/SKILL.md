---
name: plumb-intent
description: Runs the intent loop the owner opened with /plumb intent <words>, stage by stage: clarify the idea with the question tool until it is clear on its own and against the confirmed records, pass it through one judge gate, update the records and the plan, build and show the proof the owner stated. Use after `intent open --wait` answers, and at every stage until `intent done`. Not for ordinary messages (they open no loop) or for choosing questions outside a loop (plumb-clarify).
---
# plumb-intent

Make the owner's idea an intent that is coherent on its own and with what is confirmed, then
build it and show it working. Three stages, each closed by a gate the next refuses to skip.

Open: `.venv/Scripts/python.exe -m plumb intent open --wait` on the owner's words. It drafts the candidates (what will
be done, what won't, assumptions labelled) and says which check it ran; act on that answer
as plumb-clarify does (ready, a card, couldn't check, waiting).

Stage A, clarify and integrate, until `.venv/Scripts/python.exe -m plumb intent gate clarify` passes:

- Every blocking question goes through Claude Code's question tool (AskUserQuestion), one at
  a time, invariants first: the principle that settles several gaps is asked once and the
  gaps are derived from it. A question with a recommendable answer is not asked: it is an
  assumption, recorded with
  `.venv/Scripts/python.exe -m plumb decide --question Q --chosen <it> --alt B --recommend <it>`.
- Check each candidate against the confirmed records: `.venv/Scripts/python.exe -m plumb show <ID>` for the examples it
  touches, `.venv/Scripts/python.exe -m plumb inflight` for the same intent on another branch, and capture's "may
  change" and "contradicts" lines. A contradiction or an extension is a question to the
  owner, never a silent choice.
- Ask the owner how they will see this working ("how will you see this working?"); that is
  the proof, recorded on each requirement with `.venv/Scripts/python.exe -m plumb proof SR-### --plan ... --kind
  live-session|hook|command|other`.
- Capture with `.venv/Scripts/python.exe -m plumb capture --prompt <digest> --file <doc.json>` (`"mode": "escalated"`
  in the intent for a big one), naming in `supersedes` every record a new one replaces.
- Findings for the gate, in a file: open conflicts (high), unanswered blocking questions
  (high), "may change" flags with no decision and no supersedes link (medium), weak edges
  from `.venv/Scripts/python.exe -m plumb align` (low). Fix and judge again until only low remain, then
  `.venv/Scripts/python.exe -m plumb intent gate clarify --findings <file>`.

Stage B, update records and plans, until `.venv/Scripts/python.exe -m plumb intent gate plan` passes: apply the record
updates (`.venv/Scripts/python.exe -m plumb relink`, `.venv/Scripts/python.exe -m plumb unlink --note`, `.venv/Scripts/python.exe -m plumb repin --after-tests`), run
`.venv/Scripts/python.exe -m plumb stale` for what the new and reworded requirements leave uncovered, write the plan
(one acceptance test per example, the code the proof needs), review it against the intent,
the requirements and staleness, fix until only low findings remain, then
`.venv/Scripts/python.exe -m plumb intent gate plan --findings <file>`.

Stage C, build and prove: build the plan, show the proof the owner stated, record it with
`.venv/Scripts/python.exe -m plumb proof SR-### --evidence ...`, then `.venv/Scripts/python.exe -m plumb intent done`. It refuses while a proof
is missing; `.venv/Scripts/python.exe -m plumb intent status` says which gate is open.

The owner confirms records on the cards or by typing `/plumb approve <IDs>`; the loop and its
judge confirm nothing. Speak in the owner's terms; paste nothing capture prints.
