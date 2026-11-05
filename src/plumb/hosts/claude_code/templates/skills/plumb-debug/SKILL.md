---
name: plumb-debug
description: Runs plumb's debug workflow. Use when the owner types /plumb debug, when a "plumb:" line says a debug case is open, or when `plumb debug` lists cases, a defect report or an owner question. Not for ordinary stale-link questions that `plumb explain` answers.
---
# plumb-debug

plumb opens a debug case the moment one of its own steps fails (a hook error, a refused
repin, a job that failed three times). This skill and `plumb debug` are the whole workflow;
nothing else is needed.

0. Cases given as text (a "plumb:" line listing open debug cases) run through plumb's shipped
   workflow `plumb:debug-cases`, with args {cases: [{id, kind, target, detail}], worktree}.
   It fixes and checks each case at the Sonnet-like level and goes a level up only after
   a failed round; `models` in its args sets the model of a level (haiku, sonnet, opus,
   fable). Its result lists resolved, open and questions. You write no workflow script.
1. Run `plumb debug`. It reruns each case once and says which are resolved, open, or landed,
   not proven (the fix is in main, not yet seen working where it failed). A case that came
   back is reopened with its history; a known issue is matched by its symptom.
2. In plumb's own repository, run `plumb debug fix [<id>]` for a case still open: plumb works
   in a worktree and a branch of its own (`debug/<case>`), never in the main checkout, and
   never merges. The evidence stage runs at the Haiku-like level, the cause, test and fix
   stages at the Sonnet-like level, and a failed round is retried one level up. Three failed
   rounds end as a defect report on the case.
3. A case with a report: read it to the owner in their terms (what failed, what is missing).
   Elsewhere, with `debug.report_issues` on and `gh` installed, plumb files one issue per case
   with no records or code in it.
4. A fix the judge reads as changing a requirement's meaning is not committed. It reaches the
   owner as one question through the question tool, with options and what each one does;
   pass their answer on and rerun `plumb debug`. Ask the owner nothing any other way.
5. `plumb debug done <id>...` closes a case you settled by hand, or a landed one once you
   retried what failed and it worked. You confirm no record. A "reload plugins" line, or
   `done` refused with exit 1, means this session runs another build than main's: tell
   the owner in one line the fix that line names; the case stays landed, not proven.

Questions to the owner: follow plumb-records.
