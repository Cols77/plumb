---
description: plumb brief, or why and impact for a record or path
argument-hint: "brief | why <ID|path> | impact <ID|path>"
allowed-tools: Bash(.venv/Scripts/python.exe -m plumb brief:*), Bash(.venv/Scripts/python.exe -m plumb why:*), Bash(.venv/Scripts/python.exe -m plumb impact:*)
---
Run `.venv/Scripts/python.exe -m plumb $ARGUMENTS` (run `.venv/Scripts/python.exe -m plumb brief` when no argument is given). Summarize its output
for the owner in a few lines: the intent, decisions and tests it names, and any drift. Change
nothing.
