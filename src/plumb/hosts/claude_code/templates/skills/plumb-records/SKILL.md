---
name: plumb-records
description: Grounds work in this repository's plumb records (the owner's intent, requirements with examples, decisions, tests). Use on every owner request, before changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears. Not for answering the owner's typed /plumb command (the command does that) or for choosing which questions to ask (plumb-clarify).
---
Run plumb as `{plumb}`. The owner's intent lives in files; read it before acting.

- First, on every owner request, run `{plumb} clarify --wait`, before reading code or planning:
  edits are refused until it answers. plumb-clarify says what to do with each answer.
- `.plumb/` holds INT (the owner's words), SR (given/when/then examples), DEC, FEAT and NC:
  `{plumb} brief` (intent now), `show <ID>` (examples, tests), `explain <words>` (why it is).
- Grep `.plumb/test_map.txt` before editing a file (no map: `{plumb} tests map`). Never rewrite
  a confirmed example's test to pass. If the stop hook asks, run `{plumb} tests run --changed`.
  A workflow agent's stop is held on each stale link its work made: repin, reword or card it.
- Read back each request in the owner's terms; record it in one call, all proposed, never
  blocking, output not pasted: `{plumb} capture --prompt <digest> --file <doc.json>`
  (references/capture-doc.md); `<digest>` (sha256 of the owner's message) is `message_digest`
  in `{plumb} clarify --wait --json`. Two readings: `{plumb} decide --question Q --chosen A`.
- Act on capture's "contradicts" and "may change" lines in that capture: supersede only when
  every still-tested example of the old record is covered by the new or moved via `updates`,
  else reword; never supersede a newer or proposed record by an older; undecided: card.
- Plan and show each requirement's proof before done: `{plumb} proof SR-### --plan ...
  --kind live-session|hook|command|other`, then `--evidence`.
- Ask with Claude Code's question tool by default; a card (plumb-clarify) only when the answer
  must change the owner's records or needs context, consequences or a diagram.
- Never decide the owner approved: only their typed `/plumb approve <IDs>` or plumb's reader
  of their next message confirms. Never run `{plumb} approve`, `revoke`, `tests waive`,
  `{plumb} triage --approve`, `spec approve`, `config auto-approve`, `config show`,
  `conflict choose`, `turn start`, `hook prompt`, `owner` or `mod`; `undo`, `go`, `approve`
  are typed by the owner and done by the hook. Merges, conflict cards: references/merge.md,
  references/conflicts.md. Commits carry an `SR: SR-###` trailer naming what they serve.
