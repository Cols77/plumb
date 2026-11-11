---
name: iaso-records
description: Grounds work in this repository's iaso records (the owner's intent, requirements with examples, decisions, tests). Use on every owner request, before changing code or tests, when the owner states or changes intent, or when a "iaso:" hook line appears. Not for answering the owner's typed /iaso command (the command does that) or for choosing the depth and questions of a request that changes intent (iaso-clarify).
---
Run iaso as `iaso`. The owner's intent lives in files; read it before acting.
- Every message, after `capture`: run `iaso clarify --wait --json` and act on its answer
  (`ask` with iaso's judge's questions, or `ready`; every state:
  ../iaso-clarify/references/clarify-states.md). After `/iaso clarify <words>`, also run it
  before reading code: it collects the request's check. Terms: references/glossary.md.
- `.iaso/` holds INT (the owner's words), SR (given/when/then
  examples), DEC, FEAT and NC: `iaso brief` (intent now), `show <ID>` (examples, tests),
  `explain <words>` (why it is).
- Before editing a file, grep `.iaso/test_map.txt` for it (no map: run `iaso tests map`);
  the tests listed cover it. Never rewrite a confirmed example's acceptance test to make it
  pass. When the stop hook asks, run the command it names (`iaso tests run --changed`).
  A workflow agent's stop is held on each stale link its work made: repin, reword or ask it.
- Formalize each request that changes the system as proposed records linked to its code, for
  the judge: `iaso capture --prompt <digest> --file <doc.json>` (references/capture-doc.md).
  No read-back. Two readings: `iaso decide --question Q --chosen A --alt B`. `<digest>`
  (sha256 of the message) is `message_digest` of `iaso clarify --wait --json`. A requirement
  is one durable, observable behaviour with examples and a proof, naming what it supersedes; a
  fix of what one states is a commit claiming it (or an NC), never a new requirement; an intent
  is one per principle. The proof, how the owner sees it working, is shown before done:
  `iaso proof SR-### --plan ... --kind live-session|hook|command|other`, then `--evidence`.
- Never run `iaso approve` or `revoke` (both gone), `tests waive`, `ui`,
  `config auto-approve`, `config show`,
  `conflict choose`, `turn start`, `hook prompt`, `owner` or `mod`; `undo` and `go` are typed
  by the owner and done by the hook. Merges, conflicts: references/merge.md,
  references/conflicts.md. Commits carry an `SR: SR-###` trailer naming what they serve.
- Asked: hook limit `hooks.hard_limit_s` (<=119 s); a study, any words: references/study.md.
Questions to the owner (the only place these rules are written; every other skill and the
/iaso command point here): iaso's judge approves on the owner's behalf; no approval command
exists, and you never decide on your own that the owner approved.
1. After `capture`, run `iaso clarify --wait --json`. On `ask`, pass each
   `question`, `header` and option `label` and `description` to the question tool,
   every question at once, as soon as it is raised; never restate one in prose. Put
   each in the owner's terms with `iaso question reword`, merging those that
   hinge on one principle; never drop, answer or default one. Ask them all at once:
   every judge question is asked at the next chance, even in the middle of a task, merged
   by principle (iaso gives one per principle).
2. Never answer, infer or default a question for the owner, never pick the recommended option
   for them, and never write or read `judge_questions.json` or any approval.
3. If the question tool is unavailable (a subagent or headless run) or the owner dismisses a
   question, stop asking, tell the owner in one plain line that the work waits for their
   answer, and do not rerun `ask` in a loop.
4. Any other question to the owner also goes through the question tool, with options and
   their consequences.
5. What the stop hook hands you is for you, not the owner. One tagged "only the owner can
   settle this" (an open conflict, a regression on a confirmed requirement, a drift whose
   meaning changed): ask it at once with the question tool, plain words, options, no ids
   (or offer a study of both sides). Stale links, untraced files and warnings are yours to fix.
