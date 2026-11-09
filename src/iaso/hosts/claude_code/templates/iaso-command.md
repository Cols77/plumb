---
description: iaso in plain words - status, intent, explain, review, debug, impact, study, loops, go, undo, conflicts, merges, the JEV judge
argument-hint: "status | intent <words> | clarify <words> | debug | explain <anything> | review [<anything>] | impact <anything> | study <topic> | loops | init | go | undo <ID> | conflicts | merge-check | inflight | jev status | jev setup <provider> | jev calibrate"
allowed-tools: Bash({iaso} status:*), Bash({iaso} brief:*), Bash({iaso} explain:*), Bash({iaso} why:*), Bash({iaso} review:*), Bash({iaso} impact:*), Bash({iaso} debug:*), Bash({iaso} study propose:*), Bash({iaso} study gather:*), Bash({iaso} study add:*), Bash({iaso} study storyboard:*), Bash({iaso} study render:*), Bash({iaso} study frames:*), Bash({iaso} study check:*), Bash({iaso} show:*), Bash({iaso} resolve:*), Bash({iaso} align:*), Bash({iaso} init:*), Bash({iaso} plugin migrate:*), Bash({iaso} clarify --wait:*), Bash({iaso} question:*), Bash({iaso} intent:*), Bash({iaso} validate:*), Bash({iaso} conflicts:*), Bash({iaso} conflict propose:*), Bash({iaso} merge-check:*), Bash({iaso} inflight:*), Bash({iaso} loops:*), Bash({iaso} jev status:*), Bash({iaso} jev setup:*), Bash({iaso} jev calibrate:*), Bash(git add .iaso:*), Bash(git reset --keep ORIG_HEAD), Bash(git rebase --continue), Bash(git cherry-pick --continue), Bash(git revert --continue)
---
The owner asked: `/iaso $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When iaso lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

Pick the branch by the first word of the arguments, ignoring case (`Status` is `status`),
except for the typed commands (`go`, `undo <ID>`, `auto-approve`): iaso acts on those only
typed in lower case as the whole message.
Typed otherwise (`/iaso Go`), iaso acted on nothing: undo, release or switch nothing
yourself, and tell them to type it again in lower case.
`<digest>` below is the sha256 of the owner's message: `message_digest` in
`{iaso} clarify --wait --json` (12 or more hex digits are enough; on an ordinary message it
checks nothing of the request and answers `ask` with iaso's judge's questions, or `ready`).

- No argument, or `status`: run `{iaso} status --card` and give the status line, what awaits
  them and drift in one or two lines; when it lists records also being changed on another
  branch or worktree, name them by title and branch ("is anyone else changing X?" is the
  same request).
- `init` (the session start says "/iaso:iaso init to adopt this repository"; also "set up
  iaso here"): run `{iaso} init` and report what it printed in their terms. When it says
  iaso is set up here the old way and they say "move iaso to the plugin", run
  `{iaso} plugin migrate` and report it.
- `go`, `undo <ID>` or `auto-approve on|off`, typed as the
  whole message: iaso's prompt hook already acted on it when the message arrived (released
  the failed check, took that record back, switched
  automatic confirmation) and logged it as the owner's own. Run nothing to approve, release
  or switch: run `{iaso} status --card`
  and report the status, and for auto-approve whether it is on and, when not in effect yet,
  what is missing. The same words inside a sentence ("turn auto-approve on") change
  nothing: tell them to type the command as the whole message.
- `settle ...`: that switch no longer exists; the prompt hook said so. Change and run nothing.
- `intent <words>`: the owner opens the intent loop on those words (questions through the
  question tool until the intent is clear on its own and against the confirmed records, one
  judge gate, then the records, the plan and the build with the proof they stated). Run
  `{iaso} intent open --wait`, then follow the iaso-intent skill stage by stage. Ordinary
  messages open no loop.
- `clarify <words>`: the same as `intent <words>`; follow that branch.
- `explain <anything>` (also `why <anything>`): run `{iaso} explain <their words>` and say
  why it exists: the owner's words it comes from, the decisions, the examples and whether
  their tests pass.
- `review [<anything>]`: run `{iaso} review [<their words>]` and walk them through what
  awaits them, the approvals they did not type, drift, alignment and the merge state.
- `confirm <anything>` or `approve <anything>`: no approval command exists; iaso's judge
  approves on their behalf, from their answers. Run `{iaso} status --card` and say in one
  line what waits for their answers or for the judge. You approve nothing yourself.
- `debug` (also "what is stuck?", "what went wrong in iaso?", "is iaso fixing itself?"):
  run `{iaso} debug` (add `--dry-run` when they only want to know what it would do) and tell
  them in their terms what iaso could not settle on its own and what still needs them; the
  routine fixes iaso made quietly stay out unless they ask for them. Never a record number,
  a link or a command: those are yours, in the iaso-debug skill. A behaviour that changed
  under one of their decisions reaches them as one question through the question tool, which
  you pass on as the iaso-records skill says. You decide nothing for them. iaso reruns its
  own step once; a case it could not put right ends as a defect report, which you read to
  them in their terms.
- `impact <anything>`: run `{iaso} impact <their words>` and say in plain terms what a
  change would reach.
- `study <topic>` (also their plain words, "make me a study on how merges are held"):
  run `{iaso} study propose --asked --title <it> --topic <their topic> --why <one line>
  --depth md|diagrams|video` with the depth you recommend, any time, loop or not. The band
  offers it and they pick the depth there; write nothing before they do. Once picked, run
  `{iaso} study gather <slug> --json`, write from those records only (none: say no record
  covers it), then `{iaso} study add <slug> --records <their IDs> --file <body.md>`.
  At depth video, follow ${CLAUDE_PLUGIN_ROOT}/skills/iaso-study-video/SKILL.md before
  writing: compose text, diagrams and clips, each where it teaches, and subtitle every beat
  of a clip so it explains, not just shows. Each clip goes through `{iaso} study storyboard`,
  `{iaso} study render`, `{iaso} study frames` and `{iaso} study check` with `--clip`.
- `loops` (also "what loops are running?", "what is every session doing?"): run
  `{iaso} loops` and give each loop's goal, how far it is, what is left and what it waits
  for, the live ones first and the idle ones apart. "reopen the X loop": only on their own
  words, run `{iaso} loops reopen <their words> --session <this session>` and say the window
  opened, or give the command it printed. When it lists several loops, ask them with the
  question tool which one (each option naming its goal and branch), then run
  `{iaso} loops reopen --loop <that id> --session <this session>`. "tell the X loop to ...":
  pass their words, exactly as they typed them and never reworded, with
  `{iaso} loops send <X> --text "<their words>" --session <this session>`; the session
  working on it reads them before its next step. A refusal is said as it is; open and send
  nothing yourself.
- `inflight` ("what are the other branches working on?"): run `{iaso} inflight` and answer
  with the branches, their one-line intent and the records by title. "drop that work" (the
  owner abandoned a branch's intent): they name the branch; repeat it back ("drop the work
  of feat-x?") and only on their yes run `{iaso} inflight drop <branch>`.
- `conflicts` (or "what conflicts?"): run `{iaso} conflicts [<their words>]`, say in their
  terms what each side wants, and follow
  ${CLAUDE_PLUGIN_ROOT}/skills/iaso-records/references/conflicts.md:
  their answer to the question is taken, or iaso reads their chat reply; you choose nothing.
- `merge-check`, or "finish the merge", "merge <branch>", "continue the rebase", "undo the
  merge", "keep mine" on a record file, installing iaso's git hooks: follow
  ${CLAUDE_PLUGIN_ROOT}/skills/iaso-records/references/merge.md.
- `jev status`: run `{iaso} jev status --probe` and say whether the JEV judge is set
  up: the provider, the endpoint, where the key comes from (a label: the environment, an env
  file or the user store; never the key), whether it answered and the model version it
  resolved. One tiny call; nothing from the repository is sent.
- `jev setup [openrouter|typesafe]` (also their words, "use OpenRouter for JEV"): run
  `{iaso} jev setup --provider openrouter --env-var OPENROUTER_API_KEY` (or `--provider
  typesafe --env-var TYPESAFE_API_KEY`), adding `--env-file <path>` when they name an env
  file outside the repository that holds the key; it is read there in place and never
  copied. Then run `{iaso} jev status --probe` and report it. Never ask them to type a
  command or paste the key; never print, echo or read out the key or the env file.
- `jev calibrate` (also "measure the JEV judge", "is JEV good enough to confirm for me?"):
  run `{iaso} jev calibrate` and say in their terms whether the JEV judge, tried on their
  own past yes and no answers, can be trusted to confirm records that only restate their
  words: for each kind of record, passing or not, how many of their answers it was tried on,
  and what is missing when it does not pass. Calibrating approves nothing and turns nothing
  on; only the owner can turn automatic confirmation on.
- "install what iaso needs" (iaso said it needs Python 3.12 on this machine): say what
  you will install, then install uv (preferred) or Python 3.12 with this machine's usual
  installer; Claude Code asks them before it runs. Then run `{iaso} status --card`: the
  first run sets iaso up, which can take two minutes.
- Anything else: run `{iaso} resolve <their words>`, then ask which of the matches they
  meant, in their terms, and follow that branch.

Never run a command that is the owner's own (`config auto-approve`, `conflict choose`): iaso
refuses it from your session; `approve` and `revoke` no longer exist. Change nothing else.

Questions to the owner: follow iaso-records.
