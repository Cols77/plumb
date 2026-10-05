---
name: plumb
description: Ground work in this repository's plumb records (owner intent, requirements with examples, decisions, tests). Use when changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears.
---
# plumb

Run plumb as `.venv/Scripts/python.exe -m plumb`. Context lives in files; read it before acting.

- Records: `.plumb/` holds INT (the owner's words), SR (requirements with given/when/then
  examples), DEC (decisions), FEAT (features) and NC (nonconformances).
  `.venv/Scripts/python.exe -m plumb brief` prints the current intent; `.venv/Scripts/python.exe -m plumb status` lists what awaits the owner.
- Before editing a file, grep `.plumb/test_map.txt` for it: the tests listed cover it.
- When the stop hook asks, run the test command it names inside your turn
  (`.venv/Scripts/python.exe -m plumb tests run --paths <files>`, or `.venv/Scripts/python.exe -m plumb tests run --changed`).
- Read back each request in your reply (what will and won't be done, assumptions labelled)
  and record it as a proposed SR with examples, linked `implemented_by` the code it changes;
  it never blocks. "plumb: untraced change" names changed files no SR owns yet.
- When two readings fit, write a DEC record: "I assumed A; B also fits".
- Ask the owner only on: a request that contradicts or extends a confirmed record, an
  unconfirmed decision that matters, or a regression. Everything else goes in the summary.
- Only the owner's own affirming words confirm. Relay them with
  `.venv/Scripts/python.exe -m plumb relay <IDs> --prompt <digest> --quote "<owner's exact words>"`.
  A prompt that does not object is not a confirmation. A bare "ok" covers only the
  records the summary showed in full; one listed as "not shown" is relayed only when the
  owner's words name its ID (`.venv/Scripts/python.exe -m plumb show <ID>` prints it in full). Never run
  `plumb approve` or `plumb revoke`: they belong to the owner's own terminal.
- After a requirement's code changed, `.venv/Scripts/python.exe -m plumb fidelity <SR>` builds an advisory packet to
  judge it.
- Commits carry an `SR: SR-###` trailer naming the requirements they serve.
