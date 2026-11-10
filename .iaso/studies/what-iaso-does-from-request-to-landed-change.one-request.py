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


class OneRequest(Beats, Scene):
    def construct(self):
        names = ["Your request", "Records", "Judge", "Tests", "Merge check", "Landed"]
        xs = [-5.5 + i * 2.2 for i in range(6)]
        boxes = [node(n, size=18, w=1.9).move_to([x, 1.0, 0]) for n, x in zip(names, xs)]
        arrows = [Arrow(boxes[i].get_right(), boxes[i + 1].get_left(), buff=0.05, color=INK,
                        stroke_width=3, max_tip_length_to_length_ratio=0.3) for i in range(5)]

        # 1: the request
        quote = Text("\"add multiply next to add\"", font_size=22, color=BRASS).move_to([-3.5, 3.1, 0])
        self.beat(5, FadeIn(boxes[0]), Write(quote), run_time=1.2)

        # 2: the records
        tags = VGroup(tag("INT"), tag("SR"), tag("DEC")).arrange(RIGHT, buff=0.15).next_to(boxes[1], DOWN, buff=0.5).set_x(xs[1])
        self.beat(6, GrowArrow(arrows[0]), FadeIn(boxes[1]), FadeIn(tags), run_time=1.2)

        # 3: the judge, in the background
        bg = Text("approves for you,\nin the background", font_size=18, color=BRASS, line_spacing=0.8).next_to(boxes[2], UP, buff=0.35)
        self.beat(5, GrowArrow(arrows[1]), FadeIn(boxes[2]), FadeIn(bg), run_time=1.2)

        # 4: only you can settle
        you = node("You", color=BRASS, w=1.2, h=0.7, size=20).move_to([xs[2], -1.5, 0])
        ask = Arrow(boxes[2].get_bottom() + DOWN * 0.1, you.get_top(), buff=0.05, color=BRASS, stroke_width=3)
        q = Text("? one question", font_size=18, color=BRASS).next_to(ask, RIGHT, buff=0.15)
        grp = Text("grouped by principle", font_size=16, color=BRASS).next_to(you, DOWN, buff=0.15)
        self.beat(5, FadeIn(you), GrowArrow(ask), FadeIn(q), FadeIn(grp), run_time=1.2)

        # 5: tests tied to examples
        link = Text("each example\ntied to a test", font_size=18, color=BRASS, line_spacing=0.8).next_to(boxes[3], UP, buff=0.35)
        self.beat(6, GrowArrow(arrows[2]), FadeIn(boxes[3]), FadeIn(link), run_time=1.2)

        # 6: merge check twice
        quick = Text("quick at merge", font_size=18, color=BRASS).next_to(boxes[4], DOWN, buff=0.5)
        full = Text("full at push", font_size=18, color=BRASS).next_to(quick, DOWN, buff=0.15)
        self.beat(5, GrowArrow(arrows[3]), FadeIn(boxes[4]), FadeIn(quick), FadeIn(full), run_time=1.2)

        # 7: landed, the whole path lit
        lit = [b[0].animate.set_color(GREEN) for b in boxes]
        self.beat(6, GrowArrow(arrows[4]), FadeIn(boxes[5]), *lit, run_time=1.2)
