---
name: plumb-clarify
description: Clarify the owner's intent before building, scaled to the request. Use whenever a request creates or changes intent (a new feature, a changed behaviour, an ambiguous ask), not for tidy-ups or work on intent the owner already confirmed.
---
# plumb-clarify

Your job is to make what gets built match what the owner means, with the fewest questions.

Your first action on every owner request is `{plumb} clarify --wait`. Do it before you read
code, plan or edit anything: edits are refused until it has answered, and you do not build
until the owner has answered any card it returns. It waits for the check plumb started on the
owner's message and tells you which of four things happened:

- ready (nothing in the request is unclear, or it was only a question or an answer): go ahead.
- a card (up to three questions, the smaller gaps listed as assumptions): show the owner the
  card in your reply, as it is, and stop. Build nothing until they answer it; their answers,
  read by plumb, are what open the way. Never answer the questions yourself.
- a spec session offered (more than three things change what gets built): show the offer and
  stop; if they accept, run the escalated depth below.
- couldn't check (the check did not finish): show the card ("Build without the check?" with
  Build anyway and Wait) and stop. Only the owner can say to build anyway, with the button, by
  typing `/plumb go` themselves, or in plain words; you never do it for them. If they say wait,
  the check is tried again on their next message.

Once you are past that, `{plumb} clarify "<the request>"` says the depth, what confirmed
records already answer, and (with `--questions q.json`, each `{question, options,
recommended}`) which of your drafted questions matter, ranked.

Another branch may already have this intent in flight. When `clarify` (or `capture`) prints
a `▸ Conflict` card, that branch says one thing and this request another: show the owner
the card and ask it first ("which one, or both?"), before any other question and before any
work. `capture` records the question once as a decision, so every branch builds on the
same answer; a line saying the owner was already asked (or settled it) on another branch
means: build on that answer, ask nothing.

The owner answers in the card's own words: "keep feat-x's", "keep this one" or "both" (and
how they combine). Record that answer as it is, once `capture` has raised the decision:
`{plumb} conflict relay <the DEC, or the requirement> --prompt <digest> --quote "<their exact
words>"` (add `--take <branch>|both` when you are sure which they chose). It sets the
decision to their pick and confirms it, and every other branch hears it at once. Never relay
their pick as a plain "ok" (`relay`): an ok confirms only the option the decision already
holds, and words naming the other version are refused there. When `clarify` showed the card
before anything was written, run `capture` first, then relay the answer. When the backend
could not judge an overlap ("whether they agree could not be judged"), read both versions
yourself; if they differ, ask the owner which holds, or both, like any conflict card.

Depth:

- trivial (maps to confirmed intent, or a small unambiguous change): no questions. One line
  of read-back: "Doing X as in SR-004; nothing else changes."
- incremental (new or partly specified intent): write back your understanding, separating
  "you said" (the owner's words) from "I assume" (yours). Propose examples, edge cases
  included. Ask only questions whose answer changes what gets built, ONE per message, as
  multiple choice with your recommended option. Record each as
  `{plumb} decide --question Q --chosen <recommended> --alt B --matters --recommend <it>`.
- escalated (`clarify` names a trigger): a short structured session. Settle purpose and what
  success looks like first; then 2-3 approaches with trade-offs and your recommendation; then
  record the set (`capture` with `"mode": "escalated"`) and present it as an up-front spec:
  `{plumb} spec show INT-###`. Write no code for it until the owner approves the set.

Discipline:

- Never ask what the repository, the records or a sensible default already answers.
- YAGNI: drop features the owner did not ask for; list them under won't.
- Speak in the owner's terms (behaviours, examples), never in code terms.
- Once the owner says "go" or "ok", stop asking: remaining unknowns become labelled
  assumptions, which never block.
- Ask only when intent starts or changes, never mid-implementation unless a request
  contradicts a confirmed record.

Output: the intent card from `{plumb} capture` plus its records (INT, SR with examples,
DEC), all proposed until the owner confirms them in their own words.
