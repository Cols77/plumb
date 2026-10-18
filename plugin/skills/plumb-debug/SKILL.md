---
name: plumb-debug
description: Runs plumb's debug workflow. Use when the owner types /plumb debug, when a "plumb:" line says a debug case is open, or when `plumb debug` lists cases, a defect report or an owner question. Not for ordinary stale-link questions that `plumb explain` answers.
---
# plumb-debug

plumb opens a debug case the moment one of its own steps fails (a hook error, a refused
repin, a job that failed three times). This skill and `plumb debug` are the whole workflow;
nothing else is needed.

1. Run `plumb debug`. It reruns each case once and says which are resolved and which are open.
2. In plumb's own repository, run `plumb debug fix [<id>]` for a case still open: plumb works
   in a worktree and a branch of its own (`debug/<case>`), never in the main checkout, and
   never merges. The evidence stage uses the smallest configured model, the cause, test and
   fix stages the middle one, the largest only after a failed round. Three failed rounds end
   as a defect report on the case.
3. A case with a report: read it to the owner in their terms (what failed, what is missing).
   Elsewhere, with `debug.report_issues` on and `gh` installed, plumb files one issue per case
   with no records or code in it.
4. A fix the judge reads as changing a requirement's meaning is not committed. It reaches the
   owner as one question through the question tool, with options and what each one does;
   pass their answer on and rerun `plumb debug`. Ask the owner nothing any other way.
5. `plumb debug done <id>...` closes a case you settled by hand. You confirm no record.

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
