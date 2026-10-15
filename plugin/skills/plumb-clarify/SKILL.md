---
name: plumb-clarify
description: Clarifies the owner's intent before building, scaled to the request. Use on every owner request, to act on what `clarify --wait` answers (ready, a card, a spec session offered, couldn't check, waiting), and to choose the depth and the questions whenever a request creates or changes intent (a new feature, a changed behaviour, an ambiguous ask). Not for choosing questions on tidy-ups or on intent the owner already confirmed; the --wait step still comes first there.
---
# plumb-clarify

Make what gets built match what the owner means, with the fewest questions.

Your first action on every owner request is `plumb clarify --wait`. Run it before you read
code, plan or edit anything: edits are refused until it has answered, and do not build
until the owner has answered any card it returns. It collects the check plumb started on the
owner's message and says which of five things happened:

- ready (nothing blocks the request, or it was only a question or an answer): go ahead. When
  it lists what it assumed, build on that and tell the owner in one line what you assumed;
  they flip an assumption by saying so.
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
  their request has not finished, and stop.

With `--json` the answer is `{state, message_digest, card, lines}`; `state` is `ready`,
`card`, `escalation`, `couldnt_check` or `waiting`. `message_digest` is the sha256 of the
owner's message: the `<digest>` that `--prompt` takes (12 or more hex digits are enough).

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
  up-front spec: `plumb spec show INT-###`. Write no code for it until the owner approves
  the set.

Discipline:

- Never ask what the repository, the records or a sensible default already answers.
- YAGNI: drop features the owner did not ask for; list them under won't.
- Speak in the owner's terms (behaviours, examples), never in code terms.
- One question at a time, grill-style: the recommended answer comes first. A question you can
  recommend on is an "I assume" line, never a card.
- Two card shapes only: a read-back of the request (the owner's ok confirms its records, a
  correction changes them) and a choice (one question, each option with what it does, the
  recommended one first). Nothing else is a card.
- Once the owner says "go" or "ok", stop asking: remaining unknowns become labelled
  assumptions, which never block.
- Outside an accepted spec session, never ask in your own words about the owner's intent;
  the cards ask.
- Any other quick question (which of two files, a name, now or later) goes to the owner with
  Claude Code's question tool by default. A card only when the answer must change the
  owner's records (confirm, conflict, stale link, a decision that matters) or the question
  needs context, consequences or a diagram to answer. The question tool's answer is logged
  as the owner's words but confirms nothing.

Output: the records (INT, SR with examples, DEC), all proposed until the owner confirms the
request's read-back on its card. Paste nothing of what capture prints into your reply.
