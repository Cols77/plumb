---
name: plumb-records
description: Grounds work in this repository's plumb records (the owner's intent, requirements with examples, decisions, tests). Use on every owner request, before changing code or tests, when the owner states or changes intent, or when a "plumb:" hook line appears. Not for answering the owner's typed /plumb command (the command does that) or for choosing which questions to ask (plumb-clarify).
---
Run plumb as `plumb`. The owner's intent lives in files; read it before acting.

- After `capture`, on any message, run `plumb clarify --wait --json` and act on its answer
  (rule 1 below, plumb-clarify): on an ordinary message it checks nothing of the request (read
  it back in your reply) and answers `ask` with plumb's judge's questions, or `ready`. After
  `/plumb clarify <words>`, also run it before reading code: it collects the request's check.
- `.plumb/` holds INT (the owner's words), SR (given/when/then examples), DEC, FEAT and NC:
  `plumb brief` (intent now), `show <ID>` (examples, tests), `explain <words>` (why it is).
- Before editing a file, grep `.plumb/test_map.txt` for it (no map: run `plumb tests map`);
  the tests listed cover it. Never rewrite a confirmed example's acceptance test to make it
  pass. When the stop hook asks, run the command it names (`plumb tests run --changed`).
  A workflow agent's stop is held on each stale link its work made: repin, reword or card it.
- Read back each request in the owner's terms and record it in one call: `plumb capture
  --prompt <digest> --file <doc.json>` (references/capture-doc.md). Proposed; never blocking.
  Two readings: `plumb decide --question Q --chosen A --alt B`. `<digest>` (sha256 of the
  message) is `message_digest` of `plumb clarify --wait --json`. A requirement is one
  durable, observable behaviour with examples and a proof, naming what it supersedes; a fix
  of what one states is a commit claiming it (or an NC), never a new requirement; an intent
  is one per principle. The proof, how the owner sees it working, is shown before done:
  `plumb proof SR-### --plan ... --kind live-session|hook|command|other`, then `--evidence`.
- Never run `plumb approve` or `revoke` (both gone), `tests waive`, `ui`,
  `plumb triage --approve`, `spec approve`, `config auto-approve`, `config show`,
  `conflict choose`, `turn start`, `hook prompt`, `owner` or `mod`; `undo` and `go` are typed
  by the owner and done by the hook. Merges, conflict cards: references/merge.md,
  references/conflicts.md. Commits carry an `SR: SR-###` trailer naming what they serve.

Questions and approval: plumb's judge approves on the owner's behalf; no approval command
exists, and you never decide on your own that the owner approved.
1. After `capture`, run `plumb clarify --wait --json`. On `ask`, pass each `question`,
   `header` and option `label` and `description` to AskUserQuestion verbatim, one call per
   question, in order. Never restate a question in prose.
2. Never answer, infer or default a question for the owner, never pick the recommended option
   for them, and never write or read `judge_questions.json` or any approval.
3. If the question tool is unavailable (a subagent or headless run) or the owner dismisses a
   question, stop asking, tell the owner in one plain line that the work waits for their
   answer, and do not rerun `ask` in a loop.
4. Any other question to the owner also goes through the question tool, with options and
   their consequences.
