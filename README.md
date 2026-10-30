# plumb

A plumb line shows whether a wall is true. plumb does the same for software: it keeps a coding
agent's work aligned with what you intend to build.

plumb keeps your intent in small Markdown records under `.plumb/` in your repository: your own
words, the requirements and examples they become, and the checks that hold the code to them.
It works in the background, and you can inspect everything it does.

## Install

In Claude Code, add this repository as a plugin marketplace and install plumb from it:

```
/plugin marketplace add Cols77/plumb
/plugin install plumb@plumb
```

Then type `/plumb init` in a project to adopt it. plumb runs from a private copy it sets up on
first use (it needs uv, or Python 3.12 or later).

## Use

- `/plumb intent <your idea>` opens the intent loop: plumb asks what it needs to understand your
  idea, writes it down, plans it, builds it and shows you the proof you asked for.
- `/plumb status` shows where things stand: what awaits you, what drifted, what other branches
  are changing.
- `/plumb go` (typed as the whole message) lets a build go ahead when plumb's check of your
  request could not run.

Anything else, in plain words: `/plumb explain <anything>`, `/plumb review`, `/plumb debug`.

## Reference

The command reference is the help text: `plumb --help`, and `plumb <command> --help`.
