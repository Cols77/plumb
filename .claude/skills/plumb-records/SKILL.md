---
name: plumb-records
description: Grounds work in this repository's plumb records (the owner's intent, requirements with examples, decisions, tests). Use on every owner request, before changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears. Not for answering the owner's typed /plumb command (the command does that) or for choosing which questions to ask (plumb-clarify).
---
Run plumb as `.venv/Scripts/python.exe -m plumb`. The owner's intent lives in files; read it before acting.

- First, on every owner request, run `.venv/Scripts/python.exe -m plumb clarify --wait`, before reading code or planning:
  edits are refused until it answers. plumb-clarify says what to do with each answer.
- `.plumb/` holds INT (the owner's words), SR (given/when/then examples), DEC, FEAT and NC:
  `.venv/Scripts/python.exe -m plumb brief` (intent now), `show <ID>` (examples, tests), `explain <words>` (why it is).
- Before editing a file, grep `.plumb/test_map.txt` for it (no map: run `.venv/Scripts/python.exe -m plumb tests map`);
  the tests listed cover it. Never rewrite a confirmed example's acceptance test to make it
  pass. When the stop hook asks, run the command it names (`.venv/Scripts/python.exe -m plumb tests run --changed`).
- Read back each request in the owner's terms and record it in one call:
  `.venv/Scripts/python.exe -m plumb capture --prompt <digest> --file <doc.json>` (references/capture-doc.md); put the
  intent card it prints in your reply. All proposed; it never blocks. Two readings fit:
  `.venv/Scripts/python.exe -m plumb decide --question Q --chosen A --alt B [--matters]`. `<digest>` is the sha256 of the
  owner's message: `message_digest` in `.venv/Scripts/python.exe -m plumb clarify --wait --json` (12+ hex digits do).
- Plan each requirement's proof, how the owner sees it working, and show it before done:
  `.venv/Scripts/python.exe -m plumb proof SR-### --plan ... --kind live-session|hook|command|other`, then `--evidence`.
- Ask the owner only on a contradiction of a confirmed record, a decision that matters, or a
  regression; one question per message.
- Never decide that the owner approved: only their typed `/plumb approve <IDs>` or plumb's own
  reader of their next message confirms; `.venv/Scripts/python.exe -m plumb relay` is refused whatever the words.
- Never run `.venv/Scripts/python.exe -m plumb approve`, `revoke`, `tests waive`, `.venv/Scripts/python.exe -m plumb triage --approve`,
  `spec approve`, `config auto-approve`, `config show`, `conflict choose`, `turn start`,
  `hook prompt` or `mod`: they are the owner's or plumb's own. `settle`, `undo`, `owner`
  and `go` need `--prompt <digest>` of the owner's typed command; refused: tell the owner.
- Merges and conflict cards: references/merge.md and references/conflicts.md.
- Commits carry an `SR: SR-###` trailer naming the requirements they serve.
