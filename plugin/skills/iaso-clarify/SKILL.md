---
name: iaso-clarify
description: Chooses the depth and the questions of a request that creates or changes intent (a new feature, a changed behaviour, an ambiguous ask), and runs the spec session once the owner accepts it. Not for tidy-ups, answers or intent the owner already confirmed; the per-message check is iaso-records.
---
# iaso-clarify

Make what gets built match what the owner means, with the fewest questions.

On any message, after you record it as proposed (`capture`), iaso-records has you run
`iaso clarify --wait --json`; what each answer means and does is in
references/clarify-states.md.

Once you are past that, `iaso clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, see
../iaso-records/references/capture-doc.md) which of your drafted questions matter, ranked.

Another branch may already have this intent in flight. When `clarify` (or `capture`) prints
a conflict, its question is the owner's: ask it with the question tool (iaso-records) and
build nothing it touches; a line saying the owner was already asked
(or decided it) on another branch means: build on that answer, ask nothing. How their answer
is recorded: ../iaso-records/references/conflicts.md.

Depth:

- trivial (maps to confirmed intent, or a small unambiguous change): no questions. A request
  that changes what an existing requirement says is not trivial. One line
  of read-back: "Doing X, as already confirmed in <the record's title>; nothing else
  changes."
- incremental (new or partly specified intent): write back your understanding, separating
  "you said" (the owner's words) from "I assume" (yours). Propose examples, edge cases
  included. A question that has a recommended answer is not asked: write it as an "I assume"
  line and record it as
  `iaso decide --question Q --chosen <recommended> --alt B --matters --recommend <it>`.
  Outside a spec session you never ask the owner anything: the check raises blocking
  questions, every one at once in the same turn, with the question tool, grouped by
  principle; everything you can recommend is an "I assume" line.
- escalated (`clarify` names a trigger, and the owner accepted the spec session): a short
  structured session, one question per message, grill-style, each with your recommended
  answer first. Agree purpose and what
  success looks like first; then 2-3 approaches with trade-offs and your recommendation; then
  record the set (`capture` with `"mode": "escalated"` in its intent) and present it as an
  up-front spec: `iaso spec show INT-###`. Write no code for it until iaso's judge
  approves the set whole, after the owner's answers.

Discipline:

- Never ask what the repository, the records or a sensible default already answers.
- YAGNI: drop features the owner did not ask for; list them under won't.
- Speak in the owner's terms (behaviours, examples), never in code terms.
- Questions go all at once, never one per turn: the recommended answer comes first in
  each. A question you can
  recommend on is an "I assume" line, never a question.
- One question shape only, raised by iaso's check: a choice (one question, each option with
  what it does, the recommended one first). Your read-back is a line in your reply, never a
  question, and approves nothing.
- Once the owner says "go" or "ok", stop asking: remaining unknowns become labelled
  assumptions, which never block.
- Outside an accepted spec session, never ask in your own words about the owner's intent;
  iaso's judge asks, through the question tool.
- Any other quick question (which of two files, a name, now or later) goes to the owner with
  Claude Code's question tool (iaso-records).

Output: the records (INT, SR with examples, DEC), all proposed until iaso's judge approves
them on the owner's behalf. Paste nothing of what capture prints into your reply.

Questions to the owner: follow iaso-records.
