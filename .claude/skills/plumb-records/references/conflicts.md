# Relaying the owner's answer to a conflict card

Two kinds of `▸ Conflict` card ask the owner which version of the same intent holds. Show the
card, say in their terms what each side wants, and wait for their words. Never choose for
them and never run `.venv/Scripts/python.exe -m plumb conflict choose`: it is the owner's own terminal.

`<digest>` is the sha256 of the owner's message that answers: `message_digest` in
`.venv/Scripts/python.exe -m plumb clarify --wait --json` (12 or more hex digits are enough). `--quote` is their exact
words.

## Before any work: another branch has this intent in flight

`clarify` or `capture` prints the card; it says "keep feat-x's", "keep this one" or "both"
(and how they combine). Ask it first, before any other question and before any work.

1. When `clarify` showed the card before anything was written, run `capture` first: it
   records the question once as a decision, so every branch builds on the same answer.
2. Record the answer:
   `.venv/Scripts/python.exe -m plumb conflict relay <the DEC, or the requirement> --prompt <digest> --quote "<exact
   words>"`, adding `--take <branch>|both` only when you are sure which they chose. It sets
   the decision to their pick and confirms it; every other branch hears it at once.

Never pass the pick on as a plain "ok": an ok confirms only the option the decision already
holds, and words naming the other version are refused there. When the
backend could not judge an overlap ("whether they agree could not be judged"), read both
versions yourself; if they differ, ask the owner which holds, or both, like any conflict card.

## After a merge: two versions left in a record

`.venv/Scripts/python.exe -m plumb conflicts [<their words>]` lists them; the cards reach the owner at the end of your
turn. Their next words choose:

- "keep feat-x's", "keep mine" or "ok, the combined one":
  `.venv/Scripts/python.exe -m plumb conflict relay <IC> --take ours|theirs|combined --prompt <digest> --quote "<exact
  words>"` (a side's name, such as `main` or `feat-x`, works as `--take` too).
- They describe a combination: write it with `.venv/Scripts/python.exe -m plumb conflict propose <IC> --file
  <fields.yaml>` (a YAML mapping of the conflicting fields). It is shown as a third version
  and applies nothing until they choose it.

A conflict the owner already answered before the work ("already answered by you") is settled
by that answer when the merge meets it: never ask it again; the merge then only needs
"finish the merge" (merge.md).
