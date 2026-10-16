---
name: plumb-clarify
description: Clarifies the owner's intent before building, scaled to the request. Use on every owner request to read it back, and after the owner types /plumb clarify to act on what `clarify --wait` answers (ready, a card, a spec session offered, couldn't check, waiting), and to choose the depth and the questions whenever a request creates or changes intent (a new feature, a changed behaviour, an ambiguous ask). Not for choosing questions on tidy-ups or on intent the owner already confirmed; the --wait step still comes first there.
---
# plumb-clarify

Make what gets built match what the owner means, with the fewest questions.

On any message, after you record it as proposed (`capture`), run
`plumb clarify --wait --json` and act on its answer. On an ordinary message plumb checks
nothing of the request itself (read it back in your own reply, see Depth): the answer is
`ask` with plumb's judge's questions on what you recorded, or `ready` with what the judge
approved on the owner's behalf. When the owner types `/plumb clarify <words>`, your first
action is `plumb clarify --wait`. Run it before you read code, plan or edit anything: edits
are refused until it has answered, and do not build until the owner has answered any card or
question it returns. It collects the check plumb started on the owner's message and says
which of these things happened:

- ready (nothing blocks the request, or it was only a question or an answer): go ahead. When
  it lists what it assumed, build on that and tell the owner in one line what you assumed;
  they flip an assumption by saying so.
- ask (plumb's judge has questions about what the owner meant): put them to the owner as
  the rules below say, then run `plumb clarify --wait --json` again after their answers.
- a choice card (the one question that blocks, because no answer is better supported; its
  recommended option comes first): the question
  is on the card the owner sees, so say in one line that it waits there and do not restate it
  or its options. When it names a diagram file, draw it first with the
  diagram:architecture-diagram skill (a picture of the choice, for a question about structure
  or flow). Build nothing until they answer; plumb reads their answer from their next message.
  Never answer the question yourself.
- a spec session offered (more than one question has no better-supported answer): the card
  asks whether to hold a short spec session; say so in one line and stop; if they accept, run
  the escalated depth below.
- couldn't check (the check failed or took too long): show the card ("Build without the
  check?" with Build anyway and Wait) and stop. Only the owner says to build without the
  check: the Build anyway button, `/plumb go` typed as their whole message, or plain words
  that plumb reads from their next message and accepts. You never release it for them. Wait
  builds nothing until the check runs again on their next message.
- waiting (the check is not finished yet): build nothing and run `plumb clarify --wait`
  again, twice at most; still waiting after that, build nothing, tell the owner the check of
  their request has not finished, and stop. On an ordinary message `waiting` means plumb's
  judge is still reading the records: go on with the work and run it again before the turn
  ends.
- held (the request changes a record the owner confirmed and no intent loop ran for it): the
  line names the record and its examples; build nothing and run `plumb intent <the owner's
  words>` to open the loop for it, or stop and say in one line that edits are held until the
  owner types `/plumb go`.

With `--json` the answer is `{state, message_digest, card, lines}` (and `questions` on
`ask`); `state` is `ready`, `ask`, `card`, `escalation`, `couldnt_check`, `waiting` or
`held`. `message_digest` is the sha256 of the owner's message: the `<digest>` that `--prompt`
takes (12 or more hex digits are enough).

Once you are past that, `plumb clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, see
../plumb-records/references/capture-doc.md) which of your drafted questions matter, ranked.

Another branch may already have this intent in flight. When `clarify` (or `capture`) prints
a conflict, its question reaches the owner as a card: say in one line that it waits there,
do not restate it, and build nothing it touches; a line saying the owner was already asked
(or decided it) on another branch means: build on that answer, ask nothing. How their answer
is recorded: ../plumb-records/references/conflicts.md.

Depth:

- trivial (maps to confirmed intent, or a small unambiguous change): no questions. A request
  that changes what an existing requirement says is not trivial. One line
  of read-back: "Doing X, as already confirmed in <the record's title>; nothing else
  changes."
- incremental (new or partly specified intent): write back your understanding, separating
  "you said" (the owner's words) from "I assume" (yours). Propose examples, edge cases
  included. A question that has a recommended answer is not asked: write it as an "I assume"
  line and record it as
  `plumb decide --question Q --chosen <recommended> --alt B --matters --recommend <it>`.
  Outside a spec session you never ask the owner anything: the check raises blocking
  questions one at a time, as cards; everything you can recommend is an "I assume" line.
- escalated (`clarify` names a trigger, and the owner accepted the spec session): a short
  structured session, one question per message, grill-style, each with your recommended
  answer first. Agree purpose and what
  success looks like first; then 2-3 approaches with trade-offs and your recommendation; then
  record the set (`capture` with `"mode": "escalated"` in its intent) and present it as an
  up-front spec: `plumb spec show INT-###`. Write no code for it until plumb's judge
  approves the set whole, after the owner's answers.

Discipline:

- Never ask what the repository, the records or a sensible default already answers.
- YAGNI: drop features the owner did not ask for; list them under won't.
- Speak in the owner's terms (behaviours, examples), never in code terms.
- One question at a time, grill-style: the recommended answer comes first. A question you can
  recommend on is an "I assume" line, never a card.
- One card shape only, raised by plumb's check: a choice (one question, each option with
  what it does, the recommended one first). Nothing else is a card; your read-back is a line
  in your reply, never a card, and approves nothing.
- Once the owner says "go" or "ok", stop asking: remaining unknowns become labelled
  assumptions, which never block.
- Outside an accepted spec session, never ask in your own words about the owner's intent;
  plumb's judge asks, through the question tool.
- Any other quick question (which of two files, a name, now or later) goes to the owner with
  Claude Code's question tool (rule 4 below).

Output: the records (INT, SR with examples, DEC), all proposed until plumb's judge approves
them on the owner's behalf. Paste nothing of what capture prints into your reply.

Questions and approval: plumb's judge approves on the owner's behalf; no approval command
exists, and you never decide on your own that the owner approved.
1. After `capture`, run `plumb clarify --wait --json`. On `ask`, pass each `question`,
   `header` and option `label` and `description` to AskUserQuestion verbatim, one call per
   question, in order. Never restate a question in prose.
2. Never answer, infer or default a question for the owner, never pick the recommended option
   for them, and never write or read `judge_questions.json` or any approval.
3. If the question tool is unavailable (a subagent or headless run) or the owner dismisses a
   question, stop asking, tell the owner in one plain line that the work waits for their
   answer, and do not rerun `ask` in a loop. `clarify --wait` names a dismissed question once,
   then answers `waiting`.
4. Any other question to the owner also goes through the question tool, with options and
   their consequences.
