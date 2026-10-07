---
name: plumb
description: Ground work in this repository's plumb records (owner intent, requirements with examples, decisions, tests). Use when changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears.
---
# plumb

Run plumb as `.venv/Scripts/python.exe -m plumb`. Context lives in files; read it before acting.

- `.plumb/` holds INT (the owner's words), SR (requirements with given/when/then examples),
  DEC (decisions), FEAT and NC. `.venv/Scripts/python.exe -m plumb brief` is the current intent; `.venv/Scripts/python.exe -m plumb show <ID>`
  a record's examples and tests; `.venv/Scripts/python.exe -m plumb explain <words>` why something exists.
- Before editing a file, grep `.plumb/test_map.txt` for it: the tests listed cover it. Never
  rewrite a confirmed example's acceptance test to make it pass. When the stop hook asks,
  run the command it names (`.venv/Scripts/python.exe -m plumb tests run --changed`).
- When a request starts or changes intent, load the plumb-clarify skill
  (`.venv/Scripts/python.exe -m plumb clarify "<request>"` gives the depth and the questions that matter).
- Read back each request in the owner's terms and record it in one call:
  `.venv/Scripts/python.exe -m plumb capture --prompt <digest> --file <doc.json>` (verbatim quote, will, won't,
  labelled assumptions, examples with edge cases, implemented_by paths); put the intent card
  it prints in your reply. All proposed; it never blocks. Two readings fit:
  `.venv/Scripts/python.exe -m plumb decide --question Q --chosen A --alt B [--matters]`.
- Ask the owner only on a contradiction or extension of a confirmed record, an unconfirmed
  decision that matters (one per message), or a regression.
- Only the owner's own affirming words confirm; silence is not a confirmation. Relay them:
  `.venv/Scripts/python.exe -m plumb relay <IDs> --prompt <digest> --quote "<exact words>"`, `--group low-risk` for
  the triage offer (`.venv/Scripts/python.exe -m plumb triage` lists it), `--set INT-###` for an escalated spec.
- Never run `plumb approve`, `revoke`, `triage --approve`, `spec approve`,
  `config auto-approve` or `conflict choose`: they belong to the owner's own terminal.
  A merge conflict's side is relayed only from the owner's words (`/plumb conflicts`).
- Commits carry an `SR: SR-###` trailer naming the requirements they serve.
