---
name: plumb-study-video
description: Writes a study as a short explainer video with Manim (storyboard, scene, render, independent frame check). Use when the owner accepted a study idea at depth video. Not for text or diagram studies.
---
# plumb-study-video

The owner picked depth `video` for an accepted study. A video that does not teach is worse
than none: decide what the owner must understand, then show only that.

1. Text first, as for any study: `{plumb} study gather <slug> --json`, write from those
   records only, `{plumb} study add <slug> --records <IDs> --file <body.md>`.
2. Storyboard (JSON file), then `{plumb} study storyboard <slug> --file <storyboard.json>`:
   - `question`: the one question the video answers.
   - `goals`: 2 to 3 things the viewer understands afterwards.
   - `context`: where this sits in plumb and which records it comes from, so it is not floating.
   - `beats`: 3 to 6, each `{shows, subtitle, seconds}`. `shows` is what is on screen;
     `subtitle` explains it in plain words; the last beat has `recap: true` and restates the goals.
   - At most 90 s in all; each beat at least max(1.5, words in its subtitle / 3) s.
   - Each beat must add understanding. Cut a beat that only decorates.
   - Check every claim against the code and the records before writing it: scope words
     ("every", "only", "never") hold for all cases or are narrowed. Each subtitle says why
     the step exists, not only what the picture shows.
3. Scene (a `.py` file), by the rules in `vendor/manimce-best-practices/SKILL.md` (and
   `vendor/manim-composer/SKILL.md` for planning; skip its questions to the user and its
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
     and look at each beat's midpoint frame; fix the layout there, not with the one revision.
4. `{plumb} study render <slug> --scene <scene.py>` returns at once; the video renders in the
   background. Do not wait.
5. When plumb says the video rendered: run an INDEPENDENT reviewer with the Agent tool, a
   fresh agent that did not write the scene. Give it `{plumb} study frames <slug> --json`
   (storyboard, cues, frame PNG paths; it opens the PNGs) and ask: does each frame show its
   beat, and does the video meet its goals and answer its question? It answers pass or fail
   with reasons.
6. Record it: `{plumb} study check <slug> --pass|--fail --reason "<its reasons>" --reviewer <agent>`.
7. On a fail, revise the scene once on the reviewer's reasons (step 3, then 4 to 6). A second
   fail stands: the study keeps its text and the reason.
