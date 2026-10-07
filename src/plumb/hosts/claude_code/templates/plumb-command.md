---
description: plumb in plain words - status, explain anything, review, confirm, what a change would reach, the Obsidian view
argument-hint: "status | explain <anything> | review [<anything>] | confirm [<anything>] | impact <anything> | view"
allowed-tools: Bash({plumb} status:*), Bash({plumb} brief:*), Bash({plumb} explain:*), Bash({plumb} why:*), Bash({plumb} review:*), Bash({plumb} confirm:*), Bash({plumb} impact:*), Bash({plumb} view:*), Bash({plumb} show:*), Bash({plumb} resolve:*), Bash({plumb} align:*), Bash({plumb} inflight:*)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When plumb lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

- No argument, or `status`: run `{plumb} status --card` and give the card, what awaits
  them and drift in one or two lines; when it lists records also being changed on another
  branch or worktree, name them by title and branch ("is anyone else changing X?" is the
  same request).
- "what are the other branches working on?": run `{plumb} inflight` and answer with the
  branches, their one-line intent and the records by title. "drop that work" (the owner
  abandoned a branch's intent): `{plumb} inflight drop <branch>`.
- `explain <anything>` (also `why <anything>`): run `{plumb} explain <their words>` and say
  why it exists: the owner's words it comes from, the decisions, the examples and whether
  their tests pass.
- `review [<anything>]`: run `{plumb} review [<their words>]` and walk them through what
  awaits them, the approvals they did not type, drift, alignment and the merge state.
- `confirm [<anything>]`: run `{plumb} confirm [<their words>]` and show the cards it prints,
  in full. It approves nothing: their next "ok" confirms exactly what was shown (relay it
  with `{plumb} relay`). When their words already name IDs and affirm ("/plumb confirm
  SR-034"), relay them at once with their exact words as the quote.
- `impact <anything>`: run `{plumb} impact <their words>` and say in plain terms what a
  change would reach.
- `view`: run `{plumb} view --open` and tell them the Obsidian vault is open (generated;
  editing a note approves nothing).

Change nothing else.
