---
name: plumb-records
description: Grounds work in this repository's plumb records (the owner's intent, requirements with examples, decisions, tests). Use on every owner request, before changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears. Not for answering the owner's typed /plumb command (the command does that) or for choosing which questions to ask (plumb-clarify).
---
Run plumb as `{plumb}`. The owner's intent lives in files; read it before acting.

- Only after the owner types `/plumb clarify <words>`, run `{plumb} clarify --wait` before
  reading code (plumb-clarify has its answers); an ordinary message is read back in your reply.
- `.plumb/` holds INT (the owner's words), SR (given/when/then examples), DEC, FEAT and NC:
  `{plumb} brief` (intent now), `show <ID>` (examples, tests), `explain <words>` (why it is).
- Before editing a file, grep `.plumb/test_map.txt` for it (no map: run `{plumb} tests map`);
  the tests listed cover it. Never rewrite a confirmed example's acceptance test to make it
  pass. When the stop hook asks, run the command it names (`{plumb} tests run --changed`).
  A workflow agent's stop is held on each stale link its work made: repin, reword or card it.
- Read back each request in the owner's terms and record it in one call: `{plumb} capture
  --prompt <digest> --file <doc.json>` (references/capture-doc.md). Proposed; never blocking.
  Two readings: `{plumb} decide --question Q --chosen A --alt B`. `<digest>` (sha256 of the
  message) is `message_digest` of `{plumb} clarify --wait --json`. A requirement is one
  durable, observable behaviour with examples and a proof, naming what it supersedes; a fix
  of what one states is a commit claiming it (or an NC), never a new requirement; an intent
  is one per principle. The proof, how the owner sees it working, is shown before done:
  `{plumb} proof SR-### --plan ... --kind live-session|hook|command|other`, then `--evidence`.
- Ask with Claude Code's question tool by default; a card (plumb-clarify) only when the answer
  must change the owner's records or needs context, consequences or a diagram.
- Never decide the owner approved: only their typed `/plumb approve <IDs>` or plumb's reader
  of their next message confirms. Never run `{plumb} approve`, `revoke`, `tests waive`,
  `{plumb} triage --approve`, `spec approve`, `config auto-approve`, `config show`,
  `conflict choose`, `turn start`, `hook prompt`, `owner` or `mod`; `undo`, `go`, `approve`
  are typed by the owner and done by the hook. Merges, conflict cards: references/merge.md,
  references/conflicts.md. Commits carry an `SR: SR-###` trailer naming what they serve.
