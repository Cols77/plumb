---
name: plumb-clarify
description: Clarify the owner's intent before building, scaled to the request. Use whenever a request creates or changes intent (a new feature, a changed behaviour, an ambiguous ask), not for tidy-ups or work on intent the owner already confirmed.
---
# plumb-clarify

Your job is to make what gets built match what the owner means, with the fewest questions.
Run `{plumb} clarify "<the request>"` first: it says the depth, what confirmed records
already answer, and (with `--questions q.json`, each `{question, options, recommended}`)
which of your drafted questions matter, ranked.

Another branch may already have this intent in flight. When `clarify` (or `capture`) prints
a `▸ Conflict` card, that branch says one thing and this request another: show the owner
the card and ask it first ("which one, or both?"), before any other question and before any
work. `capture` records the question once as a decision, so every branch builds on the
same answer; a line saying the owner was already asked (or settled it) on another branch
means: build on that answer, ask nothing.

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
