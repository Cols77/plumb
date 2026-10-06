---
description: plumb in plain words - the brief, explain anything (a feature, a behaviour, a file), or what a change would reach
argument-hint: "brief | explain <anything: a feature, a behaviour, a file or an ID> | impact <anything>"
allowed-tools: Bash({plumb} brief:*), Bash({plumb} explain:*), Bash({plumb} why:*), Bash({plumb} impact:*), Bash({plumb} show:*)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system.

- No argument, or `brief`: run `{plumb} brief` and summarize it in a few lines.
- `explain <anything>` (also `why <anything>`): run `{plumb} explain <their words>`. It takes
  plain words, a file path or a record ID. When the words are vague, first find the records,
  files or tests they mean (`{plumb} brief --all`, the code) and pass the best match; then
  answer in the owner's terms: the behaviour, the owner's own words it comes from, the
  decisions, the examples and whether their tests pass. Mention code paths only when asked.
- `impact <anything>`: resolve their words to a record ID or a path as above, run
  `{plumb} impact <ID|path>`, and say in plain terms what a change would reach.

Change nothing.
