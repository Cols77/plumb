---
name: plumb-clarify
description: Clarifies the owner's intent before building, scaled to the request. Use on every owner request, to act on what `clarify --wait` answers (ready, a card, a spec session offered, couldn't check, waiting), and to choose the depth and the questions whenever a request creates or changes intent (a new feature, a changed behaviour, an ambiguous ask). Not for choosing questions on tidy-ups or on intent the owner already confirmed; the --wait step still comes first there.
---
# plumb-clarify

Make what gets built match what the owner means, with the fewest questions.

Your first action on every owner request is `.venv/Scripts/python.exe -m plumb clarify --wait`. Run it before you read
code, plan or edit anything: edits are refused until it has answered, and do not build
until the owner has answered any card it returns. It collects the check plumb started on the
owner's message and says which of five things happened:

- ready (nothing in the request is unclear, or it was only a question or an answer): go ahead.
- a card (up to three questions, the smaller gaps listed as assumptions): show the owner the
  card in your reply, as it is, and stop. Build nothing until they answer it; their answers,
  read by plumb, are what open the way. Never answer the questions yourself.
- a spec session offered (more than three things change what gets built): show the offer and
  stop; if they accept, run the escalated depth below.
- couldn't check (the check failed or took too long): show the card ("Build without the
  check?" with Build anyway and Wait) and stop. Only the owner says to build without the
  check: the Build anyway button, `/plumb go` typed as their whole message, or plain words
  that plumb reads from their next message and accepts. You never release it for them. Wait
  builds nothing until the check runs again on their next message.
- waiting (the check is not finished yet): build nothing and run `.venv/Scripts/python.exe -m plumb clarify --wait`
  again, twice at most; still waiting after that, build nothing, tell the owner the check of
  their request has not finished, and stop.

With `--json` the answer is `{state, message_digest, card, lines}`; `state` is `ready`,
`card`, `escalation`, `couldnt_check` or `waiting`. `message_digest` is the sha256 of the
owner's message: the `<digest>` that `--prompt` takes (12 or more hex digits are enough).

Once you are past that, `.venv/Scripts/python.exe -m plumb clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, see
../plumb-records/references/capture-doc.md) which of your drafted questions matter, ranked.

Another branch may already have this intent in flight. When `clarify` (or `capture`) prints
a `▸ Conflict` card, show it to the owner and ask it first ("which one, or both?"), before
any other question and before any work; a line saying the owner was already asked (or
settled it) on another branch means: build on that answer, ask nothing. How to record their
answer: ../plumb-records/references/conflicts.md.

Depth:

- trivial (maps to confirmed intent, or a small unambiguous change): no questions. One line
  of read-back: "Doing X as in SR-004; nothing else changes."
- incremental (new or partly specified intent): write back your understanding, separating
  "you said" (the owner's words) from "I assume" (yours). Propose examples, edge cases
  included. Ask only questions whose answer changes what gets built, ONE per message, as
  multiple choice with your recommended option. Record each as
  `.venv/Scripts/python.exe -m plumb decide --question Q --chosen <recommended> --alt B --matters --recommend <it>`.
- escalated (`clarify` names a trigger): a short structured session. Settle purpose and what
  success looks like first; then 2-3 approaches with trade-offs and your recommendation; then
  record the set (`capture` with `"mode": "escalated"` in its intent) and present it as an
  up-front spec: `.venv/Scripts/python.exe -m plumb spec show INT-###`. Write no code for it until the owner approves
  the set.

Discipline:

- Never ask what the repository, the records or a sensible default already answers.
- YAGNI: drop features the owner did not ask for; list them under won't.
- Speak in the owner's terms (behaviours, examples), never in code terms.
- Once the owner says "go" or "ok", stop asking: remaining unknowns become labelled
  assumptions, which never block.
- Ask only when intent starts or changes, never mid-implementation unless a request
  contradicts a confirmed record.

Output: the intent card from `.venv/Scripts/python.exe -m plumb capture` plus its records (INT, SR with examples,
DEC), all proposed until the owner confirms them in their own words.
