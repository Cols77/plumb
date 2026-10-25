---
name: plumb-study-video
description: Composes a study at depth video as a mix of text, mermaid diagrams and short Manim clips placed where each helps (storyboard, scene, render, independent frame check per clip). Use when the owner accepted a study idea at depth video. Not for text or diagram studies.
---
# plumb-study-video

The owner picked depth `video` for an accepted study: the ceiling of the mix, not an order to
make a film. You compose the study from three parts and place each where it teaches best. A
part that does not teach is worse than none.

1. Plan the mix first, from `{plumb} study gather <slug> --json` (write from those records
   only). Text is the spine: the why, the trade-offs, the examples. Use a part only where it
   beats text:
   - a ```mermaid diagram for structure that holds still (what sits where, what calls what);
   - a clip for what moves: a sequence, a record going through stages, a state that changes,
     where seeing it run is what makes it click. Never a clip that only restates a diagram.
   The number and length of clips are yours (DEC-366); none at all is a valid mix.
2. Write the body once, with each clip as a fenced block naming it at its place:
   ````
   ```video
   one-record
   ```
   ````
   Names: lower-case letters, digits, dashes, each once. The text around a clip says what to
   watch for, so the clip is never floating. `{plumb} study add <slug> --records <IDs>
   --file <body.md>`. The room shows 'video rendering…' at each clip's place until it passes.
3. For each clip, its storyboard (JSON file), then
   `{plumb} study storyboard <slug> --clip <name> --file <storyboard.json>`:
   - `question`: the one question the clip answers.
   - `goals`: 2 to 3 things the viewer understands afterwards.
   - `context`: where this sits in plumb and which records it comes from.
   - `beats`: each `{shows, subtitle, seconds}`. `shows` is what is on screen; `subtitle`
     explains it in plain words; the last beat has `recap: true` and restates the goals.
   - Each beat at least max(1.5, words in its subtitle / 3) s. Cut a beat that only decorates.
   - Check every claim against the code and the records before writing it: scope words
     ("every", "only", "never") hold for all cases or are narrowed. Each subtitle says why
     the step exists, not only what the picture shows.
4. Scene (a `.py` file per clip), by the rules in `vendor/manimce-best-practices/SKILL.md`
   (and `vendor/manim-composer/SKILL.md` for planning; skip its questions to the user and its
   scenes.md: the accepted idea and the storyboard take their place):
   - `from manim import *`. Never `manimlib`, never `from manimlib import *`: it is the
     other library and plumb refuses it.
   - Plain `Text` and shapes (`Rectangle`, `Arrow`, `Circle`...), no `Tex`/`MathTex` unless
     LaTeX is on the machine. No OpenGL renderer.
   - On-screen text only names things (boxes, steps); the subtitles do the explaining.
   - Each beat lasts exactly its `seconds` (`self.wait` to fill). The scene is one class.
   - Each beat's full picture is on screen by its midpoint: the reviewer sees the frame there.
   - Show the mechanism as it runs: steps passed in turn are joined by arrows, a path drawn
     on screen matches the subtitle, and no label overlaps or runs off the frame.
   - Never put the owner's private material in a committed study.
   - Before `study render`, dry-render it yourself (`python -m manim -ql` in the scratchpad)
     and look at each beat's midpoint frame; fix the layout there first.
5. `{plumb} study render <slug> --clip <name> --scene <scene.py>` returns at once; the clip
   renders in the background. Do not wait.
6. When plumb says a clip rendered: run an INDEPENDENT reviewer with the Agent tool, a fresh
   agent that did not write the scene. Give it `{plumb} study frames <slug> --clip <name>
   --json` (storyboard, cues, frame PNG paths; it opens the PNGs) and the study's body, and
   ask: does each frame show its beat, does the clip meet its goals and answer its question,
   and does it add something the text and diagrams around it do not? It returns findings,
   each tagged `critical`, `high`, `medium` or `low`, or none.
7. Record it: `{plumb} study check <slug> --clip <name> --pass --reviewer <agent>`, or
   `--fail --finding "<severity>: <text>"` once per finding (repeatable).
8. While the latest check has any critical, high or medium finding, revise that clip on the
   findings and check it again (steps 3 to 7), as many times as it takes. When only low
   findings remain, plumb accepts the clip and shows them as notes at its place: no render.
   Safety valve: after 6 revisions a still-failing clip stands failed (its place says why) and
   the rest of the study stays.

## Progress (the owner sees it in the band)

Report each step so the band shows a bar for the minutes a video takes: `{plumb} study
progress <slug> --step "<what you are doing>" --done N --total M`. Count the steps you will
take (plan the mix, write the body and add it, then per clip its storyboard, scene, render,
reviewer check) and call it at the start of each, the first with `--done 0`. `study add` keeps
the bar when the study has clips. It ends by itself when the last clip passes its check; end it
yourself with `{plumb} study progress <slug> --finish` when you stop for any other reason (a
clip that failed for good, no clip to render).
