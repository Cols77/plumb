# Intent loop visuals, studies and plumb's own colours (INT-090)

Requirements: SR-290 colours, SR-291 step strip and bar, SR-292 understanding picture,
SR-293 few on-point studies, SR-294 announcement. Decisions DEC-146..154. Built in this
order, each slice green before the next; every example gets one acceptance test named after it.

## Slice 1: plum and brass (SR-290)

- `plugin/hooks/text.ts`: `PLUMB_COLOR` becomes plum (`#B05FB0` dark / `#8E3B8E` light,
  chosen by the host's theme when the surface gives it, dark otherwise) and a new `BRASS`
  (`#C9A227`) for fills; nothing in the mod draws `cyan` any more.
- `ui/src/app.css`: one `--plumb` / `--plumb-strong` / `--brass` token set on `:root`, dark
  values under `prefers-color-scheme: dark`; every accent in the room uses them. Rebuild
  `src/plumb/browser/static`.
- Tests: `tests/plugin/mod/colours.test.tsx` (EX-1, EX-3, EX-4: no cyan, no Claude orange
  `#D77757`, no lavender `#B1B9F9` anywhere in the drawn band; light shade on light theme);
  `ui/src/lib/colours.test.ts` (EX-2: room tokens equal the mod's values).

## Slice 2: step strip and task bar (SR-291)

- `src/plumb/understand/cmd_intent.py`: the loop file gains `step` (clarify, plan, build,
  proven) derived from its stages, and `tasks: {label, done, total|null, started_at}`;
  new `plumb intent progress --task <words> [--done N --total M]` sets it; a refused gate
  writes `stopped: <what it waits for>`; `intent done` closes the loop file.
- `plugin/hooks/plumb.ts`: `readLoop` reads the session's open loop file; `PlumbStatus`
  gains `loop`.
- `plugin/hooks/register.tsx`: while a loop is open the band draws up to three lines: the
  strip (`clarify ✓  plan ●  build ○  proven ○`, plum), the bar (brass fill, `label · d/t`,
  or elapsed with no fill when total is null), the study line (slice 3). Without a loop it
  is the one line as today (SR-272 unchanged, DEC-153).
- plumb-intent skill: the agent runs `plumb intent progress` as it answers questions and
  writes plan items.
- Tests: `tests/understand/test_intent_progress.py` (EX-1, EX-2, EX-3, EX-6 data side);
  `tests/plugin/mod/loop.test.tsx` (EX-1..EX-6 drawn).

## Slice 3: understanding picture, studies, announcement (SR-292, SR-293, SR-294)

- New `src/plumb/study/` (store + CLI): studies are `.plumb/studies/<slug>.md` with
  frontmatter `title, step, loop, why, status (new|opened|known|deeper)`, body in plain
  words with an optional mermaid diagram; `.plumb/understanding.md` is the picture, plain
  lines `- knows: ...`, `- needs: ...`.
  `plumb study add --title --why --file` refuses a second study for the same loop step
  (SR-293 EX-5); `plumb study list`; `plumb study candidates` prints the context the agent
  picks from: the understanding picture, open conflicts (`plumb conflicts`), the loop's
  records and the decisions marked matters.
- Browser room (`src/plumb/browser/service.py`, `server.py`, `ui/src/App.svelte`): a
  Studies section beside the questions (DEC-151): list, study page, 'I know this' / 'Go
  deeper' (update the study status and the picture; never delivered to a session,
  DEC-152), and an editable Understanding page. The room never opens by itself.
- Mod: the band's study line `new study: <title>` (brass) while a study is `new`; a toast
  with the same words when a study first appears; the line goes once the study is opened.
- plumb-intent skill: at the end of each stage the agent runs `plumb study candidates`,
  writes at most one study when something valuable stands out (architecture, a gap in the
  picture, a need-to-know, an open conflict laid out both sides choosing nothing (DEC-154),
  or a feature labelled a suggestion), and adds it.
- Tests: `tests/study/test_store.py` (SR-292 EX-1..EX-4, SR-293 EX-3, EX-5);
  `tests/browser/test_studies.py` (SR-292 EX-3, SR-294 EX-2, EX-3); `tests/plugin/mod/
  study.test.tsx` (SR-294 EX-1, EX-3); SR-293 EX-1, EX-2, EX-4 are the agent's judgment,
  shown in the live proof.

## Proof (all `live-session`)

One live `/plumb intent` loop on a small request: screenshots of the band at clarify, plan
and build (strip + bar), the toast and band line for a new study, the room not opened by
itself, the study page in plum and brass, 'I know this' pressed and the Understanding page
changed, and the band back to one line after `intent done`; dark and light. Each PNG is
opened in a window on the owner's screen (`start "" <file>.png`) as it is shown, not only saved.

## Gates

Each slice ends on: its tests pass (`pytest -n 2` on the slice's files, `npm test` in
`ui/` and the mod tests), `plumb relink`/`repin --after-tests` for the new links, and
`plumb stale` showing nothing new uncovered for SR-290..294.

## Slice 4: the end-of-turn text goes (SR-265, SR-266, SR-295; DEC-155, DEC-156)

The owner's words (2026-10-17): the text the stop hook prints is unbearable and unread; write
in the owner's window only what is necessary, and route what matters so they act on it.

- `src/plumb/understand/summary.py` and the Claude Code stop renderer
  (`src/plumb/hosts/claude_code/`, `src/plumb/hosts/render_claude`): the owner's text carries
  at most one plumb line (SR-265, in plum where the host allows), nothing when nothing changed
  for them; every card, stale link, untraced file and warning goes to the agent's channel as
  text (SR-266), with the full/compact/off setting retired.
- What only the owner can settle (open conflict, regression on a confirmed requirement,
  drift whose meaning changed) goes to the agent tagged "ask the owner with the question
  tool" (SR-295); the plumb-records skill says to ask it at once, or offer a study for a
  conflict needing both sides read, choosing nothing.
- The band's line and the stop line agree.
- Tests: `tests/understand/test_turn_end_line.py` (SR-265 EX-1..EX-7, SR-266 EX-2..EX-6,
  SR-295 EX-1, EX-3); existing stop-hook tests that asserted cards in the owner's text are
  updated or retired with `plumb unlink --note` where their examples are superseded; SR-295
  EX-2, EX-4 shown live.

## Addendum: workflow phases feed the bar (SR-291 EX-7, EX-8; DEC-157)

The plumb-intent skill tells the workflow script to end every phase's gate agent with
`plumb intent progress --task "<phase> gate passed|failed" --done <k> --total <n>`; the band
draws that, and nothing reads Claude Code's workflow files. Tests in
`tests/understand/test_intent_progress.py` and `tests/plugin/mod/loop.test.tsx`.
