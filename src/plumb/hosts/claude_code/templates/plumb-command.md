---
description: plumb in plain words - status, explain anything, review, confirm, what a change would reach, the Obsidian view, the JEV judge (setup, status, calibration)
argument-hint: "status | explain <anything> | review [<anything>] | confirm [<anything>] | impact <anything> | view | jev status | jev setup <provider> | jev calibrate"
allowed-tools: Bash({plumb} status:*), Bash({plumb} brief:*), Bash({plumb} explain:*), Bash({plumb} why:*), Bash({plumb} review:*), Bash({plumb} confirm:*), Bash({plumb} impact:*), Bash({plumb} view:*), Bash({plumb} show:*), Bash({plumb} resolve:*), Bash({plumb} align:*), Bash({plumb} conflicts:*), Bash({plumb} conflict relay:*), Bash({plumb} conflict propose:*), Bash({plumb} merge-check:*), Bash({plumb} inflight:*), Bash({plumb} jev status:*), Bash({plumb} jev setup:*), Bash({plumb} jev calibrate:*)
---
The owner asked: `/plumb $ARGUMENTS`.

The owner may not know the code: they name things in their own words ("the login thing",
"how totals are rounded"). You bridge their words and the system. Every command below takes
their words as they are; IDs and paths work too but are never required. When plumb lists
candidates and asks "which one do you mean?", ask the owner that question in their terms.
Answer with titles, the owner's own words, examples and test states; mention code paths
only when asked.

- No argument, or `status`: run `{plumb} status --card` and give the card, what awaits
  them and drift in one or two lines; when it lists records also being changed on another
  branch or worktree, name them by title and branch ("is anyone else changing X?" is the
  same request).
- "what are the other branches working on?": run `{plumb} inflight` and answer with the
  branches, their one-line intent and the records by title. "drop that work" (the owner
  abandoned a branch's intent): `{plumb} inflight drop <branch>`.
- `explain <anything>` (also `why <anything>`): run `{plumb} explain <their words>` and say
  why it exists: the owner's words it comes from, the decisions, the examples and whether
  their tests pass.
- `review [<anything>]`: run `{plumb} review [<their words>]` and walk them through what
  awaits them, the approvals they did not type, drift, alignment and the merge state.
- `confirm [<anything>]`: run `{plumb} confirm [<their words>]` and show the cards it prints,
  in full. It approves nothing: plumb reads their next answer itself and confirms what it
  finds; you confirm nothing and never relay their words. A typed "/plumb approve SR-034"
  naming record numbers confirms at once, without you.
- `impact <anything>`: run `{plumb} impact <their words>` and say in plain terms what a
  change would reach.
- `view`: run `{plumb} view --open` and tell them the Obsidian vault is open (generated;
  editing a note approves nothing).
- `jev status`: run `{plumb} jev status --probe` and say whether the JEV judge is set
  up: the provider, the endpoint, where the key comes from (a label: the environment, an env
  file or the user store; never the key), whether it answered and the model version it
  resolved. One tiny call; nothing from the repository is sent.
- `jev setup [openrouter|typesafe]` (also their words, "use OpenRouter for JEV"): run
  `{plumb} jev setup --provider openrouter --env-var OPENROUTER_API_KEY` (or `--provider
  typesafe --env-var TYPESAFE_API_KEY`), adding `--env-file <path>` when they name an env
  file outside the repository that holds the key; it is read there in place and never
  copied. Then run `{plumb} jev status --probe` and report it. Never ask them to type a
  command or paste the key; never print, echo or read out the key or the env file.
- `jev calibrate` (also "measure the JEV judge", "is JEV good enough to confirm for me?"):
  run `{plumb} jev calibrate` and say in their terms whether the JEV judge, tried on their
  own past yes and no answers, can be trusted to confirm records that only restate their
  words: for each kind of record, passing or not, how many of their answers it was tried on,
  and what is missing when it does not pass. Calibrating approves nothing and turns nothing
  on; only the owner can turn automatic confirmation on.
- `conflicts` (or "what conflicts?"): run `{plumb} conflicts [<their words>]`. A merge left
  two versions of the same intent; the cards reach the owner at the end of your turn. Say
  in their terms what each side wants. Their next words choose: relay "keep feat-x's",
  "keep mine" or "ok, the combined one" with `{plumb} conflict relay <IC> --take
  <ours|theirs|combined> --prompt <digest> --quote "<exact words>"`. When they describe a
  combination, write it with `{plumb} conflict propose <IC> --file <fields.yaml>` (shown as
  a third version; it applies nothing). Never run `conflict choose`: it is the owner's own
  terminal. The same command lists the intent conflicts caught before any work (another
  branch has a different version of the same intent in flight; the card says "keep
  feat-x's", "keep this one" or "both"): relay the owner's answer, in their exact words,
  with `{plumb} conflict relay <the DEC or the requirement> --prompt <digest> --quote
  "<exact words>"`; it records their pick once for every branch. A conflict the owner already
  answered that way is settled by that answer when the merge meets it ("already answered by
  you"): never ask it again; the merge then only needs "finish the merge".
- `merge-check`: run `{plumb} merge-check` and say what holds the merge in their terms. A
  merge held by the quick merge check (no test run) is finished when they say "finish the
  merge": `git add .plumb` (their choices and confirmations made during the merge), then
  `{plumb} merge-check --hook pre-merge-commit`; when it passes, `git commit -m "Merge
  <branch>"` with the `SR:` trailers of the merged work. A rebase, cherry-pick or revert
  step held the same way is continued when they say "continue the rebase" (or cherry-pick,
  revert): `git add .plumb`, the same check, then `git rebase --continue` (`git cherry-pick
  --continue`, `git revert --continue`). "merge <branch>" into the main branch is
  `git merge --no-ff <branch>` (never a fast-forward: the post-merge hook puts the main
  branch back when a fast-forward brings in what the quick check holds, and says so);
  "undo the merge of <branch>" right after one is `git reset --keep ORIG_HEAD`. "check merges before they are recorded": `{plumb}
  merge-check --install-pre-merge-commit`; "call plumb from my merge hook" (or "my commit
  hook"): add the `hook_lines` of `{plumb} merge-check --install-pre-merge-commit --json`
  to their own pre-merge-commit (or prepare-commit-msg) hook. "run the tests when I push": `{plumb} merge-check --install-pre-push`;
  "call plumb from my push hook": add `<python> -m plumb merge-check --hook pre-push` (git's
  pushed refs on its stdin) to their own pre-push hook. For a record file left in text-merge form, "keep mine" / "keep theirs" is
  `git checkout --ours` / `--theirs` on it then `git add`; for one changed on one side and
  removed on the other, "keep the changed one" is `git add`, "keep it removed" is `git rm`;
  then `{plumb} validate`.

Change nothing else.
