---
description: plumb in plain words - status, explain anything, review, confirm, what a change would reach, the Obsidian view
argument-hint: "status | explain <anything> | review [<anything>] | confirm [<anything>] | impact <anything> | view"
allowed-tools: Bash(.venv/Scripts/python.exe -m plumb status:*), Bash(.venv/Scripts/python.exe -m plumb brief:*), Bash(.venv/Scripts/python.exe -m plumb explain:*), Bash(.venv/Scripts/python.exe -m plumb why:*), Bash(.venv/Scripts/python.exe -m plumb review:*), Bash(.venv/Scripts/python.exe -m plumb confirm:*), Bash(.venv/Scripts/python.exe -m plumb impact:*), Bash(.venv/Scripts/python.exe -m plumb view:*), Bash(.venv/Scripts/python.exe -m plumb show:*), Bash(.venv/Scripts/python.exe -m plumb resolve:*), Bash(.venv/Scripts/python.exe -m plumb align:*)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When plumb lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

- No argument, or `status`: run `.venv/Scripts/python.exe -m plumb status --card` and give the card, what awaits
  them and drift in one or two lines.
- `explain <anything>` (also `why <anything>`): run `.venv/Scripts/python.exe -m plumb explain <their words>` and say
  why it exists: the owner's words it comes from, the decisions, the examples and whether
  their tests pass.
- `review [<anything>]`: run `.venv/Scripts/python.exe -m plumb review [<their words>]` and walk them through what
  awaits them, the approvals they did not type, drift, alignment and the merge state.
- `confirm [<anything>]`: run `.venv/Scripts/python.exe -m plumb confirm [<their words>]` and show the cards it prints,
  in full. It approves nothing: their next "ok" confirms exactly what was shown (relay it
  with `.venv/Scripts/python.exe -m plumb relay`). When their words already name IDs and affirm ("/plumb confirm
  SR-034"), relay them at once with their exact words as the quote.
- `impact <anything>`: run `.venv/Scripts/python.exe -m plumb impact <their words>` and say in plain terms what a
  change would reach.
- `view`: run `.venv/Scripts/python.exe -m plumb view --open` and tell them the Obsidian vault is open (generated;
  editing a note approves nothing).

Change nothing else.
