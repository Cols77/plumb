# iaso

A iaso line shows whether a wall is true. iaso does the same for software: it keeps a coding
agent's work aligned with what you intend to build.

iaso keeps your intent in small Markdown records under `.iaso/` in your repository: your own
words, the requirements and examples they become, and the checks that hold the code to them.
It works in the background, and you can inspect everything it does.

## Install

In Claude Code, add this repository as a plugin marketplace and install iaso from it:

```
/plugin marketplace add Cols77/iaso
/plugin install iaso@iaso
```

Then type `/iaso init` in a project to adopt it. iaso runs from a private copy it sets up on
first use (it needs uv, or Python 3.12 or later).

## Use

- `/iaso intent <your idea>` opens the intent loop: iaso asks what it needs to understand your
  idea, writes it down, plans it, builds it and shows you the proof you asked for.
- `/iaso status` shows where things stand: what awaits you, what drifted, what other branches
  are changing.
- `/iaso go` (typed as the whole message) lets a build go ahead when iaso's check of your
  request could not run.

Anything else, in plain words: `/iaso explain <anything>`, `/iaso review`, `/iaso debug`.

## Reference

The command reference is the help text: `iaso --help`, and `iaso <command> --help`.
