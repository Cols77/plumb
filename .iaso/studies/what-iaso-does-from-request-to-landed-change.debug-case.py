from manim import *

INK = "#e8e6df"
BRASS = "#c9a227"
GREEN = "#4caf7d"
RED = "#d9534f"
BLUE = "#5b9bd5"


def node(label, color=BLUE, w=2.1, h=0.9, size=24):
    box = RoundedRectangle(corner_radius=0.15, width=w, height=h, color=color, stroke_width=3)
    box.set_fill(color, opacity=0.12)
    text = Text(label, font_size=size, color=INK).move_to(box)
    return VGroup(box, text)


def tag(label, color=BRASS):
    t = Text(label, font_size=18, color=color)
    return VGroup(SurroundingRectangle(t, buff=0.08, color=color, stroke_width=2), t)


class Beats:
    def beat(self, seconds, *anims, run_time=1.0):
        start = self.renderer.time
        if anims:
            self.play(*anims, run_time=run_time)
        left = seconds - (self.renderer.time - start)
        if left > 0:
            self.wait(left)


def tick(color=GREEN):
    t = VMobject(color=color, stroke_width=4)
    t.set_points_as_corners([[-0.1, 0.0, 0], [-0.03, -0.08, 0], [0.11, 0.1, 0]])
    return t


def side(arrow, away, gap=0.4):
    """A label spot beside an arrow's middle, `gap` off it, towards `away` (a direction)."""
    return arrow.get_center() + away * gap


class DebugCase(Beats, Scene):
    def construct(self):
        job = node("Judge job", w=2.2).move_to([-5.0, 2.2, 0])
        case = node("Debug case", color=BRASS, w=2.4).move_to([-1.6, 2.2, 0])
        work = node("Your work", color=GREEN, w=2.2).move_to([-5.0, -2.4, 0])
        a_jc = Arrow(job.get_right(), case.get_left(), buff=0.05, color=INK, stroke_width=3)
        crosses = VGroup(*[Cross(Square(0.3), stroke_color=RED, stroke_width=5).move_to(job.get_top() + UP * 0.4 + RIGHT * dx)
                           for dx in (-0.5, 0, 0.5)])

        # 1: three failures in a row
        start = self.renderer.time
        fails = Text("3 failures in a row", font_size=18, color=RED).next_to(job, DOWN, buff=0.15)
        self.play(FadeIn(job), FadeIn(fails), run_time=0.6)
        self.play(LaggedStart(*[FadeIn(c) for c in crosses], lag_ratio=0.6), run_time=1.5)
        self.wait(6 - (self.renderer.time - start))

        # 2: the case runs in the background, work goes on
        bgt = Text("in the background", font_size=18, color=BRASS).next_to(case, DOWN, buff=0.15)
        keeps = Arrow(work.get_right(), work.get_right() + RIGHT * 2.4, buff=0.05, color=GREEN, stroke_width=3)
        keeps_t = Text("keeps going", font_size=18, color=GREEN).next_to(keeps, UP, buff=0.12)
        self.beat(5, GrowArrow(a_jc), FadeIn(case), FadeIn(bgt), FadeIn(work), GrowArrow(keeps),
                  FadeIn(keeps_t), run_time=1.2)

        # 3: rerun once (the loop stays on screen)
        loop = CurvedArrow(case.get_top() + RIGHT * 0.7, case.get_top() + LEFT * 0.7, angle=TAU / 3,
                           color=BRASS, stroke_width=3, tip_length=0.18)
        rerun = Text("rerun once", font_size=18, color=BRASS).next_to(loop, UP, buff=0.08)
        self.beat(5, Create(loop), FadeIn(rerun), run_time=1.2)

        # 4: the path splits
        ok = node("Resolved", color=GREEN, w=2.0).move_to([2.0, 3.2, 0])
        fix = node("Fix on a branch", w=3.2, size=22).move_to([2.0, 0.6, 0])
        a_ok = Arrow(case.get_right(), ok.get_left(), buff=0.05, color=GREEN, stroke_width=3)
        a_fix = Arrow(case.get_right(), fix.get_left(), buff=0.05, color=INK, stroke_width=3)
        t_ok = Text("rerun passes", font_size=18, color=GREEN).move_to([1.15, 2.35, 0])
        t_fix = Text("rerun fails again", font_size=18, color=INK).move_to([-1.25, 0.95, 0])
        self.beat(6, GrowArrow(a_ok), GrowArrow(a_fix), FadeIn(ok), FadeIn(fix), FadeIn(t_ok), FadeIn(t_fix),
                  run_time=1.2)

        # 5: the fix's checklist ticks one by one
        items = ["cause", "failing test", "fix", "tests green", "nothing stale", "judge review"]
        head = Text("the fix needs", font_size=18, color=BRASS)
        rows = VGroup(*[VGroup(tick(), Text(s, font_size=18, color=INK)).arrange(RIGHT, buff=0.15) for s in items])
        rows.arrange(DOWN, aligned_edge=LEFT, buff=0.18)
        col = VGroup(head, rows).arrange(DOWN, aligned_edge=LEFT, buff=0.2).move_to([5.3, 1.9, 0])
        marks = [tk[0] for tk in rows]
        for m in marks:
            m.save_state()
        self.beat(7, FadeIn(head), LaggedStart(*[FadeIn(r, shift=RIGHT * 0.2) for r in rows], lag_ratio=0.4),
                  run_time=2.8)

        # 6: main waits for your word
        main = node("Main", color=RED, w=2.0).move_to([2.0, -1.6, 0])
        word = Text("waits for your word", font_size=18, color=BRASS).next_to(main, DOWN, buff=0.2)
        a_main = Arrow(fix.get_bottom(), main.get_top(), buff=0.05, color=INK, stroke_width=3)
        body = Rectangle(width=0.35, height=0.25, color=RED, fill_opacity=1).move_to(main.get_left() + LEFT * 0.45)
        shackle = Arc(radius=0.16, start_angle=0, angle=PI, color=RED, stroke_width=4).next_to(body, UP, buff=0)
        never = Text("the debug workflow never" + chr(10) + "approves anything and never" + chr(10) + "changes a record's meaning", font_size=16,
                     color=INK, line_spacing=0.8)
        never.next_to(a_main, RIGHT, buff=0.2)
        self.beat(6, GrowArrow(a_main), FadeIn(main), FadeIn(word), FadeIn(body), FadeIn(shackle),
                  FadeIn(never), run_time=1.2)

        # 7: recap: the path is lit, main stays behind its lock
        self.beat(6, job[0].animate.set_color(GREEN), case[0].animate.set_color(GREEN),
                  fix[0].animate.set_color(GREEN), main[0].animate.set_color(BRASS), crosses.animate.set_opacity(0.3),
                  run_time=1.2)
