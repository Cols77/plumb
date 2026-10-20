---
name: plumb-intent
description: Runs the intent loop the owner opened with /plumb intent <words>, stage by stage: clarify the idea with the question tool until it is clear on its own and against the confirmed records, pass it through one judge gate, update the records and the plan, build and show the proof the owner stated. Use after `intent open --wait` answers, and at every stage until `intent done`. Not for ordinary messages (they open no loop) or for choosing questions outside a loop (plumb-clarify).
---
# plumb-intent

Make the owner's idea an intent that is coherent on its own and with what is confirmed, then
build it and show it working. Three stages, each closed by a gate the next refuses to skip.
Run the stages as phases of a Workflow script; each phase ends on its stage's gate command
(`{plumb} intent gate clarify`, `{plumb} intent gate plan`, `{plumb} intent done`) and the next
phase starts only when that command exits 0.
Each phase's gate agent ends by reporting its gate to the owner's band:
`{plumb} intent progress --task "<phase> gate passed|failed" --done <k> --total <n>` (k
the phase's place among the script's n phases); the band draws only that, the workflow view
keeps the agents.

Open: `{plumb} intent open --wait` on the owner's words. It drafts the candidates (what will
be done, what won't, assumptions labelled) and says which check it ran; act on that answer
as plumb-clarify does (ready, ask, a card, couldn't check, waiting).

The owner's band shows the loop's step and the current task: as you go, run
`{plumb} intent progress --task <words> --done N --total M` in the owner's words
(`clarifying` with the questions answered of those to ask, `writing the plan` with the plan
items written of the plan's, `building` with the plan items built; leave `--total` out when
it is not known); while building, add `--left "<item>"` for each plan item not built yet, which
the owner's loop pane names. A refused gate shows on the band by itself.

Stage A, clarify and integrate, until `{plumb} intent gate clarify` passes:

- Every blocking question goes through Claude Code's question tool (AskUserQuestion), one at
  a time, invariants first: the principle that settles several gaps is asked once and the
  gaps are derived from it. A question with a recommendable answer is not asked: it is an
  assumption, recorded with
  `{plumb} decide --question Q --chosen <it> --alt B --recommend <it>`.
- Check each candidate against the confirmed records: `{plumb} show <ID>` for the examples it
  touches, `{plumb} inflight` for the same intent on another branch, and capture's "may
  change" and "contradicts" lines. A contradiction or an extension is a question to the
  owner, naming the requirement and its example, asked before the candidate is written;
  never a silent choice.
- Ask the owner how they will see this working ("how will you see this working?"); that is
  the proof, recorded on each requirement with `{plumb} proof SR-### --plan ... --kind
  live-session|hook|command|other`.
- Capture with `{plumb} capture --prompt <digest> --file <doc.json>` (`"mode": "escalated"`
  in the intent for a big one), naming in `supersedes` every record a new one replaces.
- Last, the step's study (DEC-207): run `{plumb} study candidates --json` and propose at most
  one study idea, none when nothing valuable stands out, none on a topic in `known` and never
  one in `declined`. Pick from: a key architectural choice being made or built, a gap in the
  owner's understanding (`picture`, `prompts`; a `deeper` line asks for more depth), what they
  need to know to choose well later, an open conflict in `conflicts` laid out on both sides
  choosing nothing, or a feature the work makes easy, labelled a suggestion. Propose the idea
  only, never the study: `{plumb} study propose --title <it> --topic <what it is about>
  --why <one line> --depth md|diagrams|video`, with the depth you recommend (diagrams when it
  is about structure or flow). The band shows it; the owner accepts it at a depth or says not
  now, and chooses, not you.
- Findings for the gate, in a file: open conflicts (high), unanswered blocking questions
  (high), "may change" flags with no decision and no supersedes link (medium), weak edges
  from `{plumb} align` (low). Fix and judge again until only low remain, then
  `{plumb} intent gate clarify --findings <file>`.

Stage B, update records and plans, only once `{plumb} intent status` shows clarify passed,
until `{plumb} intent gate plan` passes: apply the record updates (`{plumb} relink` moves
each link of a superseded requirement to the new one with a note;
`{plumb} repin --after-tests` pins it once the linked tests pass;
`{plumb} unlink --note` drops the test of a retired example, deleted in the same commit),
run `{plumb} stale` for what the new and reworded requirements leave uncovered, write the plan
(one acceptance test per example, the code the proof needs), review it against the intent,
the requirements and staleness, fix until only low findings remain, pick the plan step's
study as in stage A (`{plumb} study candidates --json`, then `{plumb} study propose` one
idea or none), then `{plumb} intent gate plan --findings <file>`.

Stage C, build and prove: build the plan, show the proof the owner stated, record it with
`{plumb} proof SR-### --evidence ...`, pick the build step's study as in stage A
(`{plumb} study candidates --json`, then `{plumb} study propose` one idea or none), then
`{plumb} intent done`. It refuses while a proof is missing; `{plumb} intent status` says
which gate is open. When the edit hook reports a link stale, before the turn ends: repin it
after its tests pass, relink it when the code moved, or card it when the meaning changed.

Studies: write none before the owner accepts its idea. When plumb tells you an idea was
accepted (the prompt's line, or `accepted` in the candidates), write it at that depth in plain
words with the records' examples, a mermaid diagram only at depth `diagrams` and none at
`md`, then `{plumb} study add <slug> --file <body.md>`; the band announces it and the owner
reads it in the room when they choose. Never open the room, and never take 'I know this' or
'Go deeper' as an answer: they correct the picture only.

The loop's gates approve nothing. Speak in the owner's terms; paste nothing capture prints.

Questions and approval: plumb's judge approves on the owner's behalf; no approval command
exists, and you never decide on your own that the owner approved.
1. After `capture`, run `{plumb} clarify --wait --json`. On `ask`, pass each `question`,
   `header` and option `label` and `description` to AskUserQuestion verbatim, one call per
   question, in order. Never restate a question in prose.
2. Never answer, infer or default a question for the owner, never pick the recommended option
   for them, and never write or read `judge_questions.json` or any approval.
3. If the question tool is unavailable (a subagent or headless run) or the owner dismisses a
   question, stop asking, tell the owner in one plain line that the work waits for their
   answer, and do not rerun `ask` in a loop.
4. Any other question to the owner also goes through the question tool, with options and
   their consequences.
