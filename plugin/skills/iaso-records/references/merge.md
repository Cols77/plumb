# Merges, rebases and iaso's git hooks

What to run when the owner asks about a merge. Each step is the owner's request in their
words; say in their terms what holds the merge, never paste the hook's output as it is.

- "what holds the merge?": `iaso merge-check`, then say what it names in their terms.
- "merge <branch>" into the main branch: `git merge --no-ff <branch>`. Never a fast-forward:
  the post-merge hook puts the main branch back when a fast-forward brings in what the quick
  check holds, and says so.
- In an old repository, `git add` the old records folder wherever `git add .iaso` appears.
- "finish the merge" (a merge held by the quick merge check, no test run): `git add .iaso`
  (their choices and confirmations made during the merge), then
  `iaso merge-check --hook pre-merge-commit`; when it passes,
  `git commit -m "Merge <branch>"` with the `SR:` trailers of the merged work.
- "continue the rebase" (or the cherry-pick, the revert) held the same way: `git add .iaso`,
  the same check, then `git rebase --continue` (`git cherry-pick --continue`,
  `git revert --continue`).
- "undo the merge of <branch>", right after it: `git reset --keep ORIG_HEAD`.
- A record file left in text-merge form: "keep mine" / "keep theirs" is
  `git checkout --ours <file>` / `git checkout --theirs <file>`, then `git add .iaso` (the
  command's permissions allow `git add .iaso`, not a file named on its own). One changed on
  one side and removed on the other: "keep the changed one" is `git add .iaso`, "keep it
  removed" is `git rm <file>`. Then `iaso validate`.
- Two versions of the same intent (a `▸ Conflict` question): see conflicts.md.

Installing the hooks (only when the owner asks):

- "check merges before they are recorded": `iaso merge-check --install-pre-merge-commit`.
- "call iaso from my merge hook" (or "my commit hook"): add the `hook_lines` of
  `iaso merge-check --install-pre-merge-commit --json` to their own pre-merge-commit (or
  prepare-commit-msg) hook.
- "run the tests when I push": `iaso merge-check --install-pre-push`.
- "call iaso from my push hook": add `<python> -m iaso merge-check --hook pre-push` (git's
  pushed refs arrive on its stdin) to their own pre-push hook.
