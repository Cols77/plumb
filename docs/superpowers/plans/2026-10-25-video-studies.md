# Video studies that teach (INT-093 + INT-111)

Builds INT-093 (video depth, Manim render, committed files, room player) and INT-111
(storyboard first, subtitle track, independent frame check). Nothing of INT-093 exists yet.

## Files of a video study `<slug>` in `.plumb/studies/`

| file | written by | committed |
|---|---|---|
| `<slug>.md` | `plumb study add` (text, as today) | yes |
| `<slug>.storyboard.json` | `plumb study storyboard` | yes (DEC-349) |
| `<slug>.py` | `plumb study render` (the agent's scene) | yes (SR-318) |
| `<slug>.mp4` | the render job | yes (SR-318) |
| `<slug>.vtt` | the render job, from the storyboard | yes (SR-365) |
| `<slug>.check.json` | `plumb study check` (the reviewer's verdict) | yes (SR-366) |

Frames for the reviewer go to `.plumb/cache/studies/<slug>/` (not committed).

The study's frontmatter gains `video`: `""` | `rendering` | `checking` | `ready` | `failed`,
`video_reason`, `revisions` (0 or 1).

## Storyboard (SR-364)

JSON: `question`, `goals` (2-3 strings), `context` (where it sits in plumb; the records it
comes from), `beats` (3-6), each `{shows, subtitle, seconds}`. Validation, before any
render: question, goals and context present; every beat has a subtitle; 3 to 6 beats; total
seconds at most 90; each beat's seconds at least max(1.5, words/3); the last beat's subtitle
names the goals' recap (flag `recap: true` on the last beat). A refusal names what is missing.

## Render (SR-316, SR-317, SR-318)

- `study.OFFERED` gains `video`; `choose()` accepts it.
- `plumb study render <slug> --scene <file.py>`: refuses without a valid storyboard or with a
  scene importing `manimlib`; copies the scene to `<slug>.py`, sets `video: rendering`, starts
  `python -m plumb study render-job <slug>` with `background.popen_options` and returns at once.
- The job runs `manim -ql --disable_caching` in a temp media dir, moves the mp4 to
  `<slug>.mp4` (replacing an older one), writes `<slug>.vtt` from the beats' cumulative
  seconds, extracts one frame per beat midpoint and the last frame (PyAV, a Manim
  dependency) to the cache, sets `video: checking`. A scene error sets `video: failed` with the
  last error line; nothing retries.
- `pyproject.toml` gains `manim>=0.19`. Without LaTeX the vendored rules say Text and shapes.
- Vendor `adithya-s-k/manim_skill` at `cef045011722` (manimce-best-practices and the
  manim-composer planning notes only, with LICENSE and the commit named) under
  `src/plumb/hosts/claude_code/templates/skills/plumb-study-video/vendor/`.

## Check (SR-366)

- `accepted_lines()` gains: "plumb: the video of '<title>' rendered: have an independent
  reviewer agent check it: plumb study frames <slug>, then plumb study check <slug>
  --pass|--fail --reason ...".
- `plumb study frames <slug> --json`: the storyboard, the vtt cues and the frame paths.
- `plumb study check <slug> --pass|--fail --reason <text> --reviewer <agent>`: writes
  `<slug>.check.json`; pass sets `video: ready`; fail sets `video: failed` with the reason;
  a second fail after one revision is final (`revisions` 1, `render` refused).
- The skill tells the agent to run the reviewer with the Agent tool, a fresh agent that did not
  write the scene, given the storyboard, the frame PNGs and the cues.

## Room (SR-319, SR-365)

- `GET /api/studies/<slug>/media/video|subtitles`: serves only `folder()/<slug>.mp4|.vtt`,
  only when `video: ready`, never a path read from the study; 404 otherwise.
- `Studies.svelte`: `ready` fetches both with the capability header into blob URLs and shows
  `<video controls>` above the text with `<track kind="subtitles" default>`; `rendering` /
  `checking` shows "video rendering…"; `failed` shows the reason; a failed fetch shows "the
  video is unavailable" (or "subtitles unavailable") and the text stays.
- Rebuild `src/plumb/browser/static/` with `npm run build` in `ui/`.

## Agent guidance

New template skill `plumb-study-video` (storyboard → scene by the vendored rules → render →
independent reviewer → check), referenced from the `study` branch of the plumb command
template; rebuild `plugin/` with `scripts/build_plugin.py`.

## Tests (one per example)

`tests/study/test_video.py` (SR-316 EX-1..5, SR-318 EX-1..3, SR-364 EX-1..4, SR-365 EX-1,3,
SR-366 EX-1..4; renders through a fake `manim` except one real render of a 2-beat scene),
`tests/study/test_vendor.py` (SR-317 EX-1..3), `tests/browser/test_study_media.py` (SR-319
EX-1..3, SR-365 EX-2,4 on the server side), `ui/src/test/Studies.test.ts` (player, track
default, fallback lines).

## Proof (live-session, SR-316..319, SR-364..366)

Live loop: idea 'How the judge cascade runs' proposed recommending video, owner accepts at
video; storyboard shown; render; reviewer verdict shown; video plays in the room with
subtitles; a copy with its mp4 removed shows the fallback; PNGs opened on the owner's screen.
