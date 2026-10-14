# The owner's answer to a conflict card

Two kinds of conflict card ask the owner which version of the same intent holds. The card is
the only ask: say in one line that it waits, never restate it, and never choose for them
(`plumb conflict choose` is the owner's own terminal). Their answer
arrives by a button or by plumb's reader of their next message.

## Before any work: another branch has this intent in flight

When `clarify` showed the conflict before anything was written, run `capture` first: it
records the question once as a decision, so every branch builds on the same answer. Build
nothing the conflict touches until the owner answers on the card; every other branch hears
the answer at once.

## After a merge: two versions left in a record

`plumb conflicts` lists them; the cards reach the owner at the end of your turn, and their
button or next words choose. If they describe a combination, write it with
`plumb conflict propose <IC> --file <fields.yaml>` (a YAML mapping of the conflicting
fields). It is shown as a third version and applies nothing until they choose it.

A conflict the owner already answered before the work ("already answered by you") is decided
by that answer when the merge meets it: never ask it again; the merge then only needs
"finish the merge" (merge.md).
