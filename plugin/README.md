# iaso for Claude Code

iaso keeps a coding agent's work aligned with what you asked for. It records your intent, the
requirements and given/when/then examples it becomes, and the decisions made along the way as
small Markdown files under `.iaso/` in your repository, pins each requirement to its code and
tests by content hash, and checks in the background, every turn, that the code still holds to
them. It speaks up only when something needs you: a request that contradicts what you
confirmed, a decision that matters, or a test that passed before and now fails.

## Install

In Claude Code, add iaso's repository as a plugin marketplace (its GitHub `owner/repo`, a git
URL, or a local clone's path) and install iaso from it:

```
/plugin marketplace add <iaso's repository>
/plugin install iaso@iaso
```

Then type `/iaso:iaso init` in a project to adopt it. A project iaso has not adopted sees one line
per session and nothing else.

## Requirements

- Python 3.12 or later, or [uv](https://docs.astral.sh/uv/): on first use the plugin sets up a private
  copy of iaso from the wheel it ships, in the background.
- On Windows, Git for Windows: the plugin's hooks and launcher run under its `sh`.
- git, and a pytest test suite for iaso to hold your code to.

## What it brings

- `/iaso`: iaso in plain words. `/iaso status` says what awaits you; `/iaso explain
  <anything>` says why something exists; `/iaso review` walks you through
  what to confirm; `/iaso impact <anything>` says what a change would reach; `/iaso view`
  opens the records in Obsidian.
- Skills that ground the agent's work in your records and clarify your intent before it builds.
- Background checks on session start, each prompt, each edit and each turn's end, each bounded
  by a timeout so iaso never holds your session.
- On Claude Code builds that load mods, a panel above the prompt with iaso's status and each
  card that waits for you, with buttons to confirm, ask for a change or leave it open.
  A card is either a read-back of what iaso understood or a choice between options; when the
  diagram mod is installed, a card can show a block diagram beside its question.

iaso is MIT licensed (see `LICENSE`).
