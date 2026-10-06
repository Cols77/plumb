---
description: plumb in plain words - status, explain anything, review, confirm, what a change would reach, the Obsidian view
argument-hint: "status | explain <anything> | review [<anything>] | confirm [<anything>] | impact <anything> | view"
allowed-tools: Bash({plumb} status:*), Bash({plumb} brief:*), Bash({plumb} explain:*), Bash({plumb} why:*), Bash({plumb} review:*), Bash({plumb} confirm:*), Bash({plumb} impact:*), Bash({plumb} view:*), Bash({plumb} show:*), Bash({plumb} resolve:*), Bash({plumb} align:*), Bash({plumb} conflicts:*), Bash({plumb} conflict relay:*), Bash({plumb} conflict propose:*), Bash({plumb} merge-check:*)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When plumb lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

- No argument, or `status`: run `{plumb} status --card` and give the card, what awaits
  them and drift in one or two lines.
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

- `conflicts` (or "what conflicts?"): run `{plumb} conflicts [<their words>]`. A merge left
  two versions of the same intent; the cards reach the owner at the end of your turn. Say
  in their terms what each side wants. Their next words choose: relay "keep feat-x's",
  "keep mine" or "ok, the combined one" with `{plumb} conflict relay <IC> --take
  <ours|theirs|combined> --prompt <digest> --quote "<exact words>"`. When they describe a
  combination, write it with `{plumb} conflict propose <IC> --file <fields.yaml>` (shown as
  a third version; it applies nothing). Never run `conflict choose`: it is the owner's own
  terminal.
- `merge-check`: run `{plumb} merge-check` and say what holds the merge in their terms. A
  merge held by the quick merge check (no test run) is finished when they say "finish the
  merge": run `{plumb} merge-check --hook pre-merge-commit`; when it passes, `git commit
  -m "Merge <branch>"` with the `SR:` trailers of the merged work. "check merges before they
  are recorded": `{plumb} merge-check --install-pre-merge-commit`; "call plumb from my merge
  hook": add the `hook_line` of `{plumb} merge-check --install-pre-merge-commit --json` to
  their own hook. For a record file left in text-merge form, "keep mine" / "keep theirs" is
  `git checkout --ours` / `--theirs` on it then `git add`; for one changed on one side and
  removed on the other, "keep the changed one" is `git add`, "keep it removed" is `git rm`;
  then `{plumb} validate`.

Change nothing else.
