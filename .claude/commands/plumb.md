---
description: plumb in plain words - status, explain anything, review, confirm or approve records, what a change would reach, the Obsidian view, adopt this repository (init), build without a failed check (go), undo a confirmed record, typed auto-approve on or off, conflicts, merges, other branches' work, the JEV judge (setup, status, calibration), installing what plumb needs
argument-hint: "status | intent <words> | clarify <words> | explain <anything> | review [<anything>] | approve <IDs> | impact <anything> | view | init | go | undo <ID> | conflicts | merge-check | inflight | jev status | jev setup <provider> | jev calibrate"
allowed-tools: Bash(.venv/Scripts/python.exe -m plumb status:*), Bash(.venv/Scripts/python.exe -m plumb brief:*), Bash(.venv/Scripts/python.exe -m plumb explain:*), Bash(.venv/Scripts/python.exe -m plumb why:*), Bash(.venv/Scripts/python.exe -m plumb review:*), Bash(.venv/Scripts/python.exe -m plumb impact:*), Bash(.venv/Scripts/python.exe -m plumb view:*), Bash(.venv/Scripts/python.exe -m plumb show:*), Bash(.venv/Scripts/python.exe -m plumb resolve:*), Bash(.venv/Scripts/python.exe -m plumb align:*), Bash(.venv/Scripts/python.exe -m plumb init:*), Bash(.venv/Scripts/python.exe -m plumb plugin migrate:*), Bash(.venv/Scripts/python.exe -m plumb clarify --wait:*), Bash(.venv/Scripts/python.exe -m plumb intent:*), Bash(.venv/Scripts/python.exe -m plumb validate:*), Bash(.venv/Scripts/python.exe -m plumb conflicts:*), Bash(.venv/Scripts/python.exe -m plumb conflict propose:*), Bash(.venv/Scripts/python.exe -m plumb merge-check:*), Bash(.venv/Scripts/python.exe -m plumb inflight:*), Bash(.venv/Scripts/python.exe -m plumb jev status:*), Bash(.venv/Scripts/python.exe -m plumb jev setup:*), Bash(.venv/Scripts/python.exe -m plumb jev calibrate:*), Bash(git add .plumb:*), Bash(git merge --no-ff:*), Bash(git commit -m:*), Bash(git reset --keep ORIG_HEAD), Bash(git checkout --ours:*), Bash(git checkout --theirs:*), Bash(git rm:*), Bash(git rebase --continue), Bash(git cherry-pick --continue), Bash(git revert --continue)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When plumb lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

Pick the branch by the first word of the arguments, ignoring case (`Status` is `status`),
except for the typed commands (`go`, `approve <IDs>`, `undo <ID>`, `auto-approve`): plumb acts
on those only typed in lower case as the whole message.
Typed otherwise (`/plumb Approve SR-034`), plumb acted on nothing: confirm, release or switch
nothing yourself, and tell them to type it again in lower case.
`<digest>` below is the sha256 of the owner's message: `message_digest` in
`.venv/Scripts/python.exe -m plumb clarify --wait --json` (12 or more hex digits are enough; on an ordinary message it
answers ready at once and runs no check).

- No argument, or `status`: run `.venv/Scripts/python.exe -m plumb status --card` and give the card, what awaits
  them and drift in one or two lines; when it lists records also being changed on another
  branch or worktree, name them by title and branch ("is anyone else changing X?" is the
  same request).
- `init` (the session start says "/plumb:plumb init to adopt this repository"; also "set up
  plumb here"): run `.venv/Scripts/python.exe -m plumb init` and report what it printed in their terms. When it says
  plumb is set up here the old way and they say "move plumb to the plugin", run
  `.venv/Scripts/python.exe -m plumb plugin migrate` and report it.
- `go`, `approve <IDs>`, `undo <ID>` or `auto-approve on|off`, typed as the
  whole message: plumb's prompt hook already acted on it when the message arrived (released
  the failed check, confirmed those records, took that record back, switched
  automatic confirmation) and logged it as the owner's own. Run nothing to approve, release
  or switch: run `.venv/Scripts/python.exe -m plumb status --card`
  and report the card, and for auto-approve whether it is on and, when not in effect yet,
  what is missing. The same words inside a sentence ("turn auto-approve on") change
  nothing: tell them to type the command as the whole message.
- `settle ...`: that switch no longer exists; the prompt hook said so. Change and run nothing.
- `intent <words>`: the owner opens the intent loop on those words (questions through the
  question tool until the intent is clear on its own and against the confirmed records, one
  judge gate, then the records, the plan and the build with the proof they stated). Run
  `.venv/Scripts/python.exe -m plumb intent open --wait`, then follow the plumb-intent skill stage by stage. Ordinary
  messages open no loop.
- `clarify <words>`: the same as `intent <words>`; follow that branch.
- `explain <anything>` (also `why <anything>`): run `.venv/Scripts/python.exe -m plumb explain <their words>` and say
  why it exists: the owner's words it comes from, the decisions, the examples and whether
  their tests pass.
- `review [<anything>]`: run `.venv/Scripts/python.exe -m plumb review [<their words>]` and walk them through what
  awaits them, the approvals they did not type, drift, alignment and the merge state.
- `confirm <anything>` or `approve <anything>` naming things in words: run
  `.venv/Scripts/python.exe -m plumb resolve <their words>`, name the matches by title and tell them to type
  `/plumb approve` with the numbers or answer the read-back. You confirm nothing and never
  relay their words.
- `impact <anything>`: run `.venv/Scripts/python.exe -m plumb impact <their words>` and say in plain terms what a
  change would reach.
- `view`: run `.venv/Scripts/python.exe -m plumb view --open` and tell them the Obsidian vault is open (generated;
  editing a note approves nothing).
- `inflight` ("what are the other branches working on?"): run `.venv/Scripts/python.exe -m plumb inflight` and answer
  with the branches, their one-line intent and the records by title. "drop that work" (the
  owner abandoned a branch's intent): they name the branch; repeat it back ("drop the work
  of feat-x?") and only on their yes run `.venv/Scripts/python.exe -m plumb inflight drop <branch>`.
- `conflicts` (or "what conflicts?"): run `.venv/Scripts/python.exe -m plumb conflicts [<their words>]`, say in their
  terms what each side wants, and follow
  .claude/skills/plumb-records/references/conflicts.md:
  the card takes their answer, or plumb reads their chat reply; you choose nothing.
- `merge-check`, or "finish the merge", "merge <branch>", "continue the rebase", "undo the
  merge", "keep mine" on a record file, installing plumb's git hooks: follow
  .claude/skills/plumb-records/references/merge.md.
- `jev status`: run `.venv/Scripts/python.exe -m plumb jev status --probe` and say whether the JEV judge is set
  up: the provider, the endpoint, where the key comes from (a label: the environment, an env
  file or the user store; never the key), whether it answered and the model version it
  resolved. One tiny call; nothing from the repository is sent.
- `jev setup [openrouter|typesafe]` (also their words, "use OpenRouter for JEV"): run
  `.venv/Scripts/python.exe -m plumb jev setup --provider openrouter --env-var OPENROUTER_API_KEY` (or `--provider
  typesafe --env-var TYPESAFE_API_KEY`), adding `--env-file <path>` when they name an env
  file outside the repository that holds the key; it is read there in place and never
  copied. Then run `.venv/Scripts/python.exe -m plumb jev status --probe` and report it. Never ask them to type a
  command or paste the key; never print, echo or read out the key or the env file.
- `jev calibrate` (also "measure the JEV judge", "is JEV good enough to confirm for me?"):
  run `.venv/Scripts/python.exe -m plumb jev calibrate` and say in their terms whether the JEV judge, tried on their
  own past yes and no answers, can be trusted to confirm records that only restate their
  words: for each kind of record, passing or not, how many of their answers it was tried on,
  and what is missing when it does not pass. Calibrating approves nothing and turns nothing
  on; only the owner can turn automatic confirmation on.
- "install what plumb needs" (plumb said it needs Python 3.12 on this machine): say what
  you will install, then install uv (preferred) or Python 3.12 with this machine's usual
  installer; Claude Code asks them before it runs. Then run `.venv/Scripts/python.exe -m plumb status --card`: the
  first run sets plumb up, which can take two minutes.
- Anything else: run `.venv/Scripts/python.exe -m plumb resolve <their words>`, then ask which of the matches they
  meant, in their terms, and follow that branch.

Never run a command that is the owner's own (`approve`, `revoke`, `config auto-approve`,
`conflict choose`): plumb refuses it from your session. Change nothing else.
