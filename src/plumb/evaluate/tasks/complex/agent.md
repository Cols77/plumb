# Task: a command-line expense tracker

You work in this repository for its owner, who sends you requests one at a time. Build what
each request asks, and only that, in Python 3.12, standard library only, in the file
`expenses.py` at the repository root, with its data files beside it. Work as plumb's skills and
hooks direct. If a request is unclear, ask the owner in your reply.

The owner runs `python expenses.py <command> ...` from the repository root and reads standard
output. They hold you to the exact commands, file names and output formats each request states.

## Reporting plumb problems

> Whenever plumb behaves wrongly (a refusal you cannot explain, an error, a command or hook line
> that contradicts plumb's skills or its own words, a question you cannot answer), append one
> JSON line to `.plumb/eval-issues.jsonl`: `{"when": ISO time, "command": the plumb command or
> hook, "expected": what you expected, "got": what plumb said, "context": what you were doing}`.
> Then go on with the work.
